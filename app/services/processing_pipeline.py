# Processing pipeline — Phase 7
import asyncio
import json
import logging
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.repositories.book_repository import book_repository
from app.repositories.chapter_repository import chapter_repository
from app.repositories.lesson_repository import lesson_repository
from app.repositories.content_repository import content_repository
from app.schemas.chapter import ChapterCreate
from app.schemas.lesson import LessonCreate
from app.schemas.content import ContentBlockCreate
from app.services.gemini_service import GeminiOCRService, PageAnalysis, ContentBlock, TocAnalysis, TocEntry
from app.services.image_service import ImageExtractor, ImageResult
from app.services.mathpix_service import MathpixService
from app.services.pdf_parser import render_pages, PageInfo
from app.services.structure_parser import StructureParser, BookStructure, Chapter, Lesson

logger = logging.getLogger(__name__)

_KEEP_PAGE_IMAGES: bool = os.getenv("KEEP_PAGE_IMAGES", "false").lower() == "true"

# Number of pages analysed concurrently. The Gemini rate limiter keeps the
# global call rate within free-tier limits even when this is high.
_GEMINI_BATCH_SIZE: int = int(os.getenv("GEMINI_BATCH_SIZE", "5"))


def _book_data_dir(book_id: str) -> Path:
    """Absolute on-disk dir for cache/debug artifacts of a single book."""
    return Path(settings.storage_path) / "books" / book_id


def _cache_path(book_id: str) -> Path:
    return _book_data_dir(book_id) / "page_analyses.json"


def _toc_path(book_id: str) -> Path:
    return _book_data_dir(book_id) / "toc.json"


def _metadata_path(book_id: str) -> Path:
    return _book_data_dir(book_id) / "metadata.json"


def _structure_debug_path(book_id: str) -> Path:
    return _book_data_dir(book_id) / "structure_debug.json"


class ProcessingPipeline:
    """End-to-end processing pipeline: PDF → MongoDB."""

    def __init__(self, book_id: str, pdf_path: str) -> None:
        self.book_id = book_id
        self.pdf_path = pdf_path
        self.gemini = GeminiOCRService()
        self.mathpix = MathpixService()
        self.image_extractor = ImageExtractor()
        self.structure_parser = StructureParser()
        self.book_repo = book_repository
        self.gemini_call_count = 0
        self.mathpix_call_count = 0
        self._pages_dir: Optional[str] = None
        self._toc: Optional[TocAnalysis] = None

    async def run(self) -> None:
        try:
            # STEP 1: Ingest PDF → page images
            logger.info("[%s] STEP 1/4: Rendering PDF pages...", self.book_id)
            await self._update("ingesting", 5)
            output_dir = os.path.join(settings.storage_path, "books", self.book_id)
            pages_info: list[PageInfo] = render_pages(self.pdf_path, output_dir)
            self._pages_dir = os.path.join(output_dir, "pages")
            total = len(pages_info)
            await self.book_repo.update_total_pages(self.book_id, total)
            logger.info("[%s] STEP 1/4 done: %d pages rendered.", self.book_id, total)

            await self._save_metadata(total)

            # STEP 2: Gemini OCR (batched) + Mathpix fallback + image extraction
            logger.info("[%s] STEP 2/4: Analyzing pages with Gemini OCR...", self.book_id)
            await self._update("analyzing", 10)
            all_image_results: dict[tuple[int, int], ImageResult] = {}

            cache_path = _cache_path(self.book_id)
            cache_path.parent.mkdir(parents=True, exist_ok=True)

            if cache_path.exists():
                logger.info("[%s] Cache found at %s — skipping Gemini calls.", self.book_id, cache_path)
                page_analyses = self._load_cache(cache_path)
                logger.info("[%s] Loaded %d pages from cache.", self.book_id, len(page_analyses))
                for page_info in pages_info:
                    idx = page_info.page_num - 1
                    analysis = page_analyses[idx] if idx < len(page_analyses) else None
                    if analysis:
                        page_img_results = await self._extract_images(analysis, page_info)
                        all_image_results.update(page_img_results)
            else:
                page_analyses = await self._run_gemini_batched(
                    pages_info, total, cache_path, all_image_results
                )
                self._save_cache(cache_path, page_analyses)
                logger.info("[%s] Final cache saved to %s.", self.book_id, cache_path)

            # Build TOC from any pages flagged as TOC (multi-page TOC supported)
            await self._build_toc(pages_info, page_analyses, total)

            logger.info("[%s] STEP 2/4 done: %d pages analyzed.", self.book_id, total)

            # STEP 3: Structure parse
            logger.info("[%s] STEP 3/4: Parsing book structure...", self.book_id)
            await self._update("parsing", 82)
            book_doc = await self.book_repo.get_by_id(self.book_id)
            book_structure: BookStructure = self.structure_parser.parse_book(
                page_analyses,
                grade=book_doc.grade if book_doc else 0,
                title=book_doc.title if book_doc else "",
                publisher=book_doc.publisher if book_doc else "",
                image_results=all_image_results,
                toc=self._toc,
            )
            if self._toc:
                logger.info("[%s] Used TOC-based parsing (%d entries).", self.book_id, len(self._toc.entries))
            else:
                logger.info("[%s] Used inline parsing (no TOC found).", self.book_id)
            logger.info(
                "[%s] STEP 3/4 done: %d chapters, %d lessons.",
                self.book_id,
                len(book_structure.chapters),
                sum(len(c.lessons) for c in book_structure.chapters),
            )
            await self._log_structure(book_structure)

            # STEP 4: Save to MongoDB
            logger.info("[%s] STEP 4/4: Saving to MongoDB...", self.book_id)
            await self._update("saving", 88)
            await self._save_to_db(book_structure)
            logger.info("[%s] STEP 4/4 done.", self.book_id)

            # Done
            await self._update_done(self.gemini_call_count, self.mathpix_call_count)
            logger.info(
                "[%s] Pipeline complete — gemini_calls=%d, mathpix_calls=%d",
                self.book_id, self.gemini_call_count, self.mathpix_call_count,
            )

        except Exception:
            logger.exception("Pipeline failed for book_id=%s", self.book_id)
            try:
                await self.book_repo.update_status(
                    self.book_id, "error", error="Pipeline failed — see server logs"
                )
            except Exception:
                pass

    # -----------------------------------------------------------------------
    # Cache helpers
    # -----------------------------------------------------------------------

    async def _save_metadata(self, total_pages: int) -> None:
        try:
            book_doc = await self.book_repo.get_by_id(self.book_id)
            meta = {
                "book_id": self.book_id,
                "file_path": self.pdf_path,
                "total_pages": total_pages,
                "title": book_doc.title if book_doc else "",
                "grade": book_doc.grade if book_doc else 0,
                "publisher": book_doc.publisher if book_doc else "",
                "academic_year": book_doc.academic_year if book_doc else "",
            }
            meta_path = _metadata_path(self.book_id)
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("[%s] Failed to save metadata.json", self.book_id, exc_info=True)

    # -----------------------------------------------------------------------
    # Gemini batching + TOC handling
    # -----------------------------------------------------------------------

    async def _run_gemini_batched(
        self,
        pages_info: list[PageInfo],
        total: int,
        cache_path: Path,
        all_image_results: dict[tuple[int, int], ImageResult],
    ) -> list[PageAnalysis]:
        """Analyse all pages with Gemini, batching `_GEMINI_BATCH_SIZE` per round.

        Pages are processed strictly in order so that the resulting
        `page_analyses` list is index-aligned with `pages_info`. Within each
        batch the actual Gemini calls run concurrently (the rate limiter caps
        the global call rate). Mathpix fallback + image extraction run after
        the batch returns so they can't race each other on shared state.
        """
        page_analyses: list[PageAnalysis] = [None] * total  # type: ignore[list-item]

        async def _analyze_one(idx: int, page_info: PageInfo) -> PageAnalysis:
            return await self.gemini.analyze_page(page_info.image_path, page_info.page_num)

        for start_idx in range(0, total, _GEMINI_BATCH_SIZE):
            batch = pages_info[start_idx:start_idx + _GEMINI_BATCH_SIZE]
            tasks = [_analyze_one(start_idx + i, p) for i, p in enumerate(batch)]
            try:
                results = await asyncio.gather(*tasks)
            except Exception:
                logger.exception(
                    "[%s] Gemini batch %d-%d failed; saving partial cache and re-raising.",
                    self.book_id, start_idx + 1, start_idx + len(batch),
                )
                # Persist any pages we did manage to produce before the failure
                completed = [a for a in page_analyses if a is not None]
                self._save_cache(cache_path, completed)
                raise

            for offset, (page_info, analysis) in enumerate(zip(batch, results)):
                self.gemini_call_count += 1
                analysis = await self._apply_mathpix_fallback(analysis, page_info.image_path)
                page_img_results = await self._extract_images(analysis, page_info)
                all_image_results.update(page_img_results)
                page_analyses[start_idx + offset] = analysis
                await self.book_repo.increment_processed_pages(self.book_id)

            done_count = start_idx + len(batch)
            progress = 10 + int(done_count / total * 70)
            await self._update("analyzing", progress, f"Page {done_count}/{total}")
            logger.info(
                "[%s] Batch %d-%d done; progress=%d%%",
                self.book_id, start_idx + 1, done_count, progress,
            )
            # Checkpoint roughly every 10 pages (= every 2 batches at default size 5)
            if done_count % 10 == 0 or done_count == total:
                completed = [a for a in page_analyses if a is not None]
                self._save_cache(cache_path, completed)

        # Drop raw_response to free memory now that we've cached everything.
        for a in page_analyses:
            if a is not None:
                a.raw_response = ""
        # Filter out any None placeholders defensively (shouldn't happen).
        return [a for a in page_analyses if a is not None]

    async def _build_toc(
        self,
        pages_info: list[PageInfo],
        page_analyses: list[PageAnalysis],
        total: int,
    ) -> None:
        """Detect ALL TOC pages (TOC may span 2-4 pages), merge entries, and
        compute the PDF↔SGK printed-page offset.

        Sets self._toc when at least one TOC page yields entries.
        """
        toc_pages = [pa for pa in page_analyses if self._is_toc_analysis(pa)]
        if not toc_pages:
            logger.info("[%s] No TOC page detected.", self.book_id)
            return

        # Collect TocAnalysis from each TOC page (consecutive pages typically)
        toc_pages.sort(key=lambda pa: pa.page_num)
        merged: Optional[TocAnalysis] = None
        path_by_page = {p.page_num: p.image_path for p in pages_info}

        for pa in toc_pages:
            image_path = path_by_page.get(pa.page_num)
            if not image_path:
                continue
            logger.info("[%s] Extracting TOC entries from page %d.", self.book_id, pa.page_num)
            toc_result = await self.gemini.analyze_toc_page(image_path, pa.page_num)
            if toc_result is None:
                continue
            if merged is None:
                merged = toc_result
            else:
                merged.merge(toc_result)
                # Use the EARLIEST TOC page's printed page number; that's the
                # one whose offset is most reliable.
                if merged.toc_printed_page_num <= 0 and toc_result.toc_printed_page_num > 0:
                    merged.toc_printed_page_num = toc_result.toc_printed_page_num
                    merged.toc_page_num = toc_result.toc_page_num

        if merged is None or not merged.entries:
            logger.warning("[%s] TOC detected but no entries extracted.", self.book_id)
            return

        merged.pdf_page_offset = self._compute_offset(merged, page_analyses)
        merged.compute_page_ends(total)
        self._toc = merged
        self._save_toc(merged)
        logger.info(
            "[%s] TOC built: %d entries, offset=%d (toc_printed=%d).",
            self.book_id,
            len(merged.entries),
            merged.pdf_page_offset,
            merged.toc_printed_page_num,
        )

    @staticmethod
    def _compute_offset(
        toc: TocAnalysis, page_analyses: list[PageAnalysis]
    ) -> int:
        """Determine PDF→SGK page offset.

        Strategy:
        1. Prefer the offset implied by the printed page number on the TOC
           page itself (offset_a = toc_pdf_page - toc_printed_page).
        2. Cross-check by finding the first chapter_title page in the PDF and
           comparing with the first chapter entry in the TOC
           (offset_b = first_chapter_pdf - first_chapter_toc.page_start).
        3. If both available and they disagree by ≤ 2 pages, prefer offset_b
           (more reliable). If they disagree more, log a warning.
        4. Fall back to offset_a, then 0.
        """
        offset_a: Optional[int] = None
        if toc.toc_printed_page_num > 0:
            offset_a = max(toc.toc_page_num - toc.toc_printed_page_num, 0)

        offset_b: Optional[int] = None
        first_chapter_toc = next(
            (e for e in sorted(toc.entries, key=lambda e: e.page_start)
             if e.type == "chapter" and e.page_start > 0),
            None,
        )
        if first_chapter_toc is not None:
            for pa in page_analyses:
                if pa.page_num <= toc.toc_page_num:
                    continue
                if any(b.type == "chapter_title" for b in pa.blocks):
                    offset_b = max(pa.page_num - first_chapter_toc.page_start, 0)
                    break

        if offset_b is not None and offset_a is not None:
            if abs(offset_b - offset_a) > 2:
                logger.warning(
                    "TOC offset mismatch: printed-derived=%d vs chapter-derived=%d. Using chapter-derived.",
                    offset_a, offset_b,
                )
            return offset_b
        if offset_b is not None:
            return offset_b
        if offset_a is not None:
            return offset_a
        return 0

    def _save_cache(self, path: Path, analyses: list[PageAnalysis]) -> None:
        try:
            data = [asdict(a) for a in analyses]
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("[%s] Failed to save cache to %s", self.book_id, path, exc_info=True)

    async def _cleanup_old_db_data(self) -> None:
        """Delete chapters/lessons/contents for this book before a fresh insert."""
        chapters = await chapter_repository.list_by_book(self.book_id)
        chapter_ids = [c.id for c in chapters]
        if chapter_ids:
            lesson_ids = await lesson_repository.list_ids_by_chapter_ids(chapter_ids)
            if lesson_ids:
                await content_repository.delete_by_lesson_ids(lesson_ids)
            await lesson_repository.delete_by_chapter_ids(chapter_ids)
        await chapter_repository.delete_by_book(self.book_id)
        logger.info("[%s] Old DB data cleaned up.", self.book_id)

    def _load_cache(self, path: Path) -> list[PageAnalysis]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        result = []
        for item in raw:
            blocks = []
            for b in item.get("blocks", []):
                bbox = b.get("image_bbox", ())
                if isinstance(bbox, list):
                    bbox = tuple(bbox)
                blocks.append(ContentBlock(
                    type=b.get("type", "text"),
                    content=b.get("content", ""),
                    latex=b.get("latex", ""),
                    image_bbox=bbox,
                    caption=b.get("caption", ""),
                    order=b.get("order", 0),
                    confidence=b.get("confidence", 1.0),
                    needs_mathpix=b.get("needs_mathpix", False),
                    source=b.get("source", "gemini"),
                    is_continuation=b.get("is_continuation", False),
                    is_display_math=b.get("is_display_math", False),
                    column=b.get("column", 1) or 1,
                ))
            result.append(PageAnalysis(
                page_num=item["page_num"],
                blocks=blocks,
                raw_response=item.get("raw_response", ""),
            ))
        return result

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    async def _apply_mathpix_fallback(
        self, analysis: PageAnalysis, page_image_path: str
    ) -> PageAnalysis:
        """Call Mathpix for formula blocks where Gemini had low confidence.

        When Mathpix is disabled in config, this is a no-op. When enabled, we
        only call for blocks that have a usable bbox — otherwise we'd send the
        whole page to Mathpix and overwrite Gemini's per-formula latex with
        page-wide OCR garbage.
        """
        if not self.mathpix.is_enabled():
            return analysis

        for block in analysis.blocks:
            if block.type != "formula":
                continue
            needs_fallback = block.needs_mathpix or block.confidence < 0.6
            if not needs_fallback:
                continue
            # Defense-in-depth: skip when Gemini didn't return a bbox for this
            # formula. Falling back to the full page produces meaningless LaTeX.
            bbox = block.image_bbox
            if not bbox or len(bbox) != 4:
                logger.debug(
                    "Skip Mathpix for page %d block %d (no bbox)",
                    analysis.page_num, block.order,
                )
                continue
            result = await self.mathpix.extract_formula(
                page_image_path,
                tuple(bbox),
                gemini_latex=block.latex,
            )
            if result.success and result.confidence > block.confidence:
                block.latex = result.latex
                block.source = "mathpix"
                self.mathpix_call_count += 1
        return analysis

    async def _extract_images(
        self, analysis: PageAnalysis, page_info: PageInfo
    ) -> dict[tuple[int, int], ImageResult]:
        """Extract and store image blocks; return mapping (page_num, order) → ImageResult."""
        results: dict[tuple[int, int], ImageResult] = {}
        fig_index = 1
        for block in analysis.blocks:
            if block.type != "image" or not block.image_bbox:
                continue
            img_result: Optional[ImageResult] = self.image_extractor.extract_and_store(
                page_info.image_path,
                list(block.image_bbox),
                self.book_id,
                page_info.page_num,
                fig_index,
                caption=block.caption or "",
            )
            if img_result is not None:
                results[(page_info.page_num, block.order)] = img_result
                fig_index += 1
        return results

    async def _save_to_db(self, book_structure: BookStructure) -> None:
        """Persist the parsed book structure to MongoDB.

        Also rescues unassigned blocks (no TOC range matched) by parking them
        in a special ``index=-1`` lesson titled "Phần mở đầu" of the first
        chapter — otherwise they'd be silently dropped. After save, validates
        the lesson count against the TOC and logs a warning when the diff
        exceeds 5%.
        """
        await self._cleanup_old_db_data()

        # Deduplicate chapters by index: when the same chapter_index appears
        # multiple times (e.g. once in the TOC and once in the body), keep the
        # occurrence with the most lessons so we preserve real content.
        seen: dict[int, object] = {}
        for chapter in book_structure.chapters:
            if chapter.index not in seen or len(chapter.lessons) > len(seen[chapter.index].lessons):  # type: ignore[attr-defined]
                seen[chapter.index] = chapter
        deduped_chapters: list[Chapter] = sorted(seen.values(), key=lambda c: c.index)  # type: ignore[arg-type]
        if len(deduped_chapters) < len(book_structure.chapters):
            logger.warning(
                "[%s] Deduplicated %d → %d chapters (duplicate indices removed).",
                self.book_id, len(book_structure.chapters), len(deduped_chapters),
            )

        # Inject unassigned blocks as a synthetic "Phần mở đầu" lesson on the
        # first chapter so they're queryable instead of vanishing.
        if book_structure.unassigned_blocks:
            if not deduped_chapters:
                deduped_chapters = [
                    Chapter(index=0, roman_index="", title="Phần mở đầu", page_start=1)
                ]
            target_ch = deduped_chapters[0]
            special_lesson = Lesson(
                index=-1,
                title="Phần mở đầu",
                page_start=max(target_ch.page_start, 1),
                content_blocks=list(book_structure.unassigned_blocks),
            )
            target_ch.lessons.insert(0, special_lesson)
            logger.info(
                "[%s] Persisting %d unassigned blocks into chapter %d as 'Phần mở đầu' lesson.",
                self.book_id,
                len(book_structure.unassigned_blocks),
                target_ch.index,
            )

        saved_lesson_count = 0  # excludes the synthetic index=-1 rescue lesson
        for chapter in deduped_chapters:
            ch_id = await chapter_repository.create(
                ChapterCreate(
                    book_id=self.book_id,
                    chapter_index=chapter.index,
                    roman_index=chapter.roman_index,
                    title=chapter.title,
                    page_start=chapter.page_start,
                )
            )
            # Deduplicate lessons by index within this chapter (same TOC vs body issue)
            seen_lessons: dict[int, object] = {}
            for lesson in chapter.lessons:
                if lesson.index not in seen_lessons or len(lesson.content_blocks) > len(seen_lessons[lesson.index].content_blocks):  # type: ignore[attr-defined]
                    seen_lessons[lesson.index] = lesson
            deduped_lessons: list[Lesson] = sorted(seen_lessons.values(), key=lambda l: l.index)  # type: ignore[arg-type]
            if len(deduped_lessons) < len(chapter.lessons):
                logger.warning(
                    "[%s] Chapter %d: deduplicated %d → %d lessons.",
                    self.book_id, chapter.index, len(chapter.lessons), len(deduped_lessons),
                )
            for lesson in deduped_lessons:
                les_id = await lesson_repository.create(
                    LessonCreate(
                        chapter_id=ch_id,
                        lesson_index=lesson.index,
                        title=lesson.title,
                        page_start=lesson.page_start,
                    )
                )
                if lesson.index >= 0:
                    saved_lesson_count += 1
                content_docs = [
                    ContentBlockCreate(
                        lesson_id=les_id,
                        order=cb.order,
                        type=cb.type,
                        content=cb.content,
                        latex=cb.latex,
                        image_url=cb.image_url,
                        thumbnail_url=cb.thumbnail_url,
                        caption=cb.caption,
                        exercise_type=cb.exercise_type,
                        exercise_num=cb.exercise_num,
                        confidence=cb.confidence,
                        source=cb.source,
                    )
                    for cb in lesson.content_blocks
                ]
                if content_docs:
                    await content_repository.bulk_create(content_docs)

        self._validate_saved_lesson_count(saved_lesson_count)

    def _validate_saved_lesson_count(self, saved_lesson_count: int) -> None:
        """Cross-check saved lesson count vs TOC entries (warn when off >5%)."""
        if self._toc is None:
            return
        expected = sum(
            1 for e in self._toc.entries if e.type in ("lesson", "section")
        )
        if expected <= 0:
            return
        ratio = saved_lesson_count / expected
        if ratio < 0.95:
            logger.warning(
                "[%s] Lesson coverage low: TOC has %d lesson/section entries but only %d saved (%.1f%%). Check unassigned blocks and TOC offset.",
                self.book_id, expected, saved_lesson_count, ratio * 100,
            )
        else:
            logger.info(
                "[%s] Lesson coverage OK: TOC=%d, saved=%d (%.1f%%).",
                self.book_id, expected, saved_lesson_count, ratio * 100,
            )

    @staticmethod
    def _is_toc_analysis(analysis: PageAnalysis) -> bool:
        """Return True if the page analysis looks like a TOC page."""
        blocks = analysis.blocks
        if not blocks:
            return False
        # Gemini signals TOC with type="toc"
        if len(blocks) == 1 and getattr(blocks[0], "type", "") == "toc":
            return True
        # Fallback: first block content contains "MỤC LỤC"
        first_content = getattr(blocks[0], "content", "").upper()
        return "MỤC LỤC" in first_content

    def _save_toc(self, toc: TocAnalysis) -> None:
        """Persist extracted TOC for debugging/inspection."""
        try:
            toc_path = _toc_path(self.book_id)
            toc_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "toc_page_num": toc.toc_page_num,
                "toc_printed_page_num": toc.toc_printed_page_num,
                "pdf_page_offset": toc.pdf_page_offset,
                "entries": [
                    {
                        "type": e.type,
                        "chapter_index": e.chapter_index,
                        "chapter_roman": e.chapter_roman,
                        "lesson_index": e.lesson_index,
                        "title": e.title,
                        "page_start": e.page_start,
                        "page_end": e.page_end,
                    }
                    for e in toc.entries
                ],
            }
            toc_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("[%s] TOC saved → %s", self.book_id, toc_path)
        except Exception:
            logger.warning("[%s] Failed to save toc.json", self.book_id, exc_info=True)

    async def _log_structure(self, book_structure: BookStructure) -> None:
        """Log JSON context for each chapter/lesson after structure parsing."""
        try:
            data = []
            for chapter in book_structure.chapters:
                chapter_data = {
                    "chapter_index": chapter.index,
                    "roman_index": chapter.roman_index,
                    "title": chapter.title,
                    "page_start": chapter.page_start,
                    "lessons": [],
                }
                for lesson in chapter.lessons:
                    lesson_data = {
                        "lesson_index": lesson.index,
                        "title": lesson.title,
                        "page_start": lesson.page_start,
                        "num_blocks": len(lesson.content_blocks),
                        "content_blocks": [
                            {
                                "order": cb.order,
                                "type": cb.type,
                                "content": cb.content[:300] if cb.content else "",
                                "latex": cb.latex[:150] if cb.latex else "",
                                "source": cb.source,
                                "confidence": round(cb.confidence, 3),
                            }
                            for cb in lesson.content_blocks
                        ],
                    }
                    chapter_data["lessons"].append(lesson_data)
                    logger.info(
                        "[%s] Chương %s — Bài %s '%s' (trang %s): %d blocks\n%s",
                        self.book_id,
                        chapter.roman_index or chapter.index,
                        lesson.index,
                        lesson.title,
                        lesson.page_start,
                        len(lesson.content_blocks),
                        json.dumps(lesson_data, ensure_ascii=False, indent=2),
                    )
                data.append(chapter_data)

            debug_path = _structure_debug_path(self.book_id)
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("[%s] Structure debug JSON saved → %s", self.book_id, debug_path)
        except Exception:
            logger.warning("[%s] Failed to log structure", self.book_id, exc_info=True)

    async def _update(self, phase: str, progress: int, message: str = "") -> None:
        await self.book_repo.update_status(
            self.book_id, "processing", progress, phase
        )

    async def _update_done(self, gemini_calls: int, mathpix_calls: int) -> None:
        await self.book_repo.update_status(self.book_id, "done", 100, "done")
        await self.book_repo.increment_api_calls(
            self.book_id, gemini=gemini_calls, mathpix=mathpix_calls
        )
        if not _KEEP_PAGE_IMAGES and self._pages_dir:
            _cleanup_dir(self._pages_dir)


def _cleanup_dir(path: str) -> None:
    """Remove a directory tree, logging but not raising on failure."""
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
            logger.info("Cleaned up temp pages dir: %s", path)
    except Exception as exc:
        logger.warning("Failed to cleanup %s: %s", path, exc)


async def run_pipeline(book_id: str, pdf_path: str) -> None:
    """Entry-point for FastAPI BackgroundTasks."""
    try:
        pipeline = ProcessingPipeline(book_id, pdf_path)
    except Exception:
        logger.exception("Pipeline init failed for book_id=%s", book_id)
        try:
            await book_repository.update_status(book_id, "error", error="Pipeline init failed")
        except Exception:
            pass
        return
    await pipeline.run()


async def reprocess_from_cache(book_id: str, manual_meta: dict | None = None) -> None:
    """Run STEP 3+4 only, loading page_analyses from cache.
    Restores the book record from metadata.json if it was deleted from MongoDB.
    Pass manual_meta with title/grade/publisher/academic_year/file_path to override if metadata.json is missing.
    """
    logger.info("[%s] reprocess_from_cache: starting...", book_id)
    try:
        cache_path = _cache_path(book_id)
        if not cache_path.exists():
            logger.error("[%s] reprocess: cache not found at %s", book_id, cache_path)
            return

        # Ensure book record exists in MongoDB
        book_doc = await book_repository.get_by_id(book_id)
        if book_doc is None:
            meta_path = _metadata_path(book_id)
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            elif manual_meta and (manual_meta.get("title") or manual_meta.get("grade")):
                meta = manual_meta
                logger.info("[%s] reprocess: using manual metadata override.", book_id)
            else:
                logger.error("[%s] reprocess: metadata.json missing and no manual metadata provided.", book_id)
                return
            from app.schemas.book import BookCreate
            await book_repository.restore_with_id(
                book_id,
                BookCreate(
                    title=meta.get("title", ""),
                    grade=int(meta.get("grade", 1)),
                    publisher=meta.get("publisher", ""),
                    academic_year=meta.get("academic_year", ""),
                ),
                file_path=meta.get("file_path", ""),
            )
            book_doc = await book_repository.get_by_id(book_id)
            logger.info("[%s] reprocess: book record restored.", book_id)

        pipeline = ProcessingPipeline(book_id, book_doc.file_path if book_doc else "")

        # Load page analyses from cache
        page_analyses = pipeline._load_cache(cache_path)
        logger.info("[%s] reprocess: loaded %d pages from cache.", book_id, len(page_analyses))

        # Re-extract image results from storage
        pages_dir = os.path.join(settings.storage_path, "books", book_id, "pages")
        all_image_results: dict[tuple[int, int], ImageResult] = {}
        for analysis in page_analyses:
            img_path = os.path.join(pages_dir, f"page_{analysis.page_num:03d}.jpg")
            if os.path.exists(img_path):
                from app.services.pdf_parser import PageInfo
                fake_page = PageInfo(
                    page_num=analysis.page_num,
                    image_path=img_path,
                    file_size_kb=0.0,
                    width=0,
                    height=0,
                    is_grayscale=False,
                )
                img_results = await pipeline._extract_images(analysis, fake_page)
                all_image_results.update(img_results)

        # Load TOC from toc.json so structure parser uses TOC-based path
        toc_analysis: TocAnalysis | None = None
        toc_path = _toc_path(book_id)
        if toc_path.exists():
            try:
                toc_data = json.loads(toc_path.read_text(encoding="utf-8"))
                entries = [TocEntry(**e) for e in toc_data.get("entries", [])]
                toc_analysis = TocAnalysis(
                    entries=entries,
                    toc_page_num=toc_data.get("toc_page_num", 0),
                    toc_printed_page_num=toc_data.get("toc_printed_page_num", 0),
                    pdf_page_offset=toc_data.get("pdf_page_offset", 0),
                )
                pipeline._toc = toc_analysis
                logger.info(
                    "[%s] reprocess: loaded TOC with %d entries (offset=%d).",
                    book_id, len(entries), toc_analysis.pdf_page_offset,
                )
            except Exception:
                logger.warning(
                    "[%s] reprocess: failed to load toc.json — falling back to inline parsing.",
                    book_id, exc_info=True,
                )

        # STEP 3: structure parse
        await book_repository.update_status(book_id, "processing", 82, "parsing")
        book_structure = pipeline.structure_parser.parse_book(
            page_analyses,
            grade=book_doc.grade if book_doc else 0,
            title=book_doc.title if book_doc else "",
            publisher=book_doc.publisher if book_doc else "",
            image_results=all_image_results,
            toc=toc_analysis,
        )
        logger.info(
            "[%s] reprocess STEP 3 done: %d chapters, %d lessons.",
            book_id,
            len(book_structure.chapters),
            sum(len(c.lessons) for c in book_structure.chapters),
        )

        # STEP 4: save to DB (cleanup included)
        await book_repository.update_status(book_id, "processing", 88, "saving")
        await pipeline._save_to_db(book_structure)

        await book_repository.update_status(book_id, "done", 100, "done")
        logger.info("[%s] reprocess complete.", book_id)

    except Exception:
        logger.exception("[%s] reprocess_from_cache failed.", book_id)
        try:
            await book_repository.update_status(book_id, "error", error="Reprocess failed — see server logs")
        except Exception:
            pass
