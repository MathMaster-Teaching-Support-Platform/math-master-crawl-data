"""OCR pipeline driven by an externally supplied lesson→page mapping.

Phase 3 rewrite. The Java BE owns the curriculum (chapter/lesson tree) and
hands us a list of (lesson_id, page_start, page_end) tuples. We:

  1. Render the PDF pages inside the OCR window.
  2. Run Gemini OCR per page (with Mathpix fallback for low-confidence
     formula blocks and image extraction for figure blocks).
  3. Save one `lesson_pages` document per (book, lesson, page). Pages on a
     shared boundary (page_end == next.page_start) are persisted twice —
     once per lesson — so the verify wizard treats them as separate cells.

We deliberately do NOT auto-detect chapters or lessons here. TOC parsing,
the structure parser, and the legacy chapters/lessons/lesson_contents
collections are out of scope for this service.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.repositories.book_repository import book_repository
from app.repositories.lesson_page_repository import lesson_page_repository
from app.schemas.lesson_page import ContentBlock as ContentBlockSchema
from app.services.gemini_service import (
    ContentBlock as GeminiBlock,
    GeminiOCRService,
    PageAnalysis,
)
from app.services.image_service import ImageExtractor, ImageResult
from app.services.mathpix_service import (
    MathpixService,
    latex_to_readable,
    validate_latex,
)
from app.services.minio_fetch import download_template_bucket_object, minio_download_configured
from app.services.pdf_parser import PageInfo, render_pages

logger = logging.getLogger(__name__)


class OcrCancelled(Exception):
    """Raised when an admin requests POST /books/{id}/ocr-cancel during a run."""

    pass


# Keep rendered raw page images by default; set KEEP_PAGE_IMAGES=false only
# if you explicitly want cleanup to save disk.
_KEEP_PAGE_IMAGES: bool = os.getenv("KEEP_PAGE_IMAGES", "true").lower() == "true"
_GEMINI_BATCH_SIZE: int = int(os.getenv("GEMINI_BATCH_SIZE", "5"))


def _pdf_ref_for_log(pdf_path: str) -> str:
    """Short string for logs (truncate presigned query strings)."""
    parsed = urlparse(pdf_path)
    if parsed.scheme in ("http", "https"):
        q = parsed.query
        if len(q) > 48:
            q = q[:48] + "…"
        suffix = f"?{q}" if q else ""
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}{suffix}"
    return pdf_path


@dataclass(frozen=True)
class _Mapping:
    """Internal flattened mapping — uses str ids and inclusive page bounds."""

    lesson_id: str
    page_start: int
    page_end: int


def _book_data_dir(book_id: str) -> Path:
    return Path(settings.storage_path) / "books" / book_id


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_pipeline_with_mapping(
    book_id: str,
    pdf_path: str,
    ocr_page_from: int,
    ocr_page_to: int,
    mappings: list[_Mapping] | list[dict],
) -> None:
    """Background-task entry point used by the controller."""
    flat = _normalize_mappings(mappings)
    pipeline = MappingPipeline(book_id, pdf_path, ocr_page_from, ocr_page_to, flat)
    await pipeline.run()


def _normalize_mappings(mappings) -> list[_Mapping]:
    out: list[_Mapping] = []
    for m in mappings:
        if isinstance(m, _Mapping):
            out.append(m)
        elif isinstance(m, dict):
            out.append(
                _Mapping(
                    lesson_id=str(m["lesson_id"] if "lesson_id" in m else m["lessonId"]),
                    page_start=int(m["page_start"] if "page_start" in m else m["pageStart"]),
                    page_end=int(m["page_end"] if "page_end" in m else m["pageEnd"]),
                )
            )
        else:
            # Pydantic MappingItem
            out.append(
                _Mapping(
                    lesson_id=str(m.lesson_id),
                    page_start=int(m.page_start),
                    page_end=int(m.page_end),
                )
            )
    return out


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class MappingPipeline:
    """Renders → OCRs → persists per (book, lesson, page) with no structure
    parsing in between."""

    def __init__(
        self,
        book_id: str,
        pdf_path: str,
        ocr_page_from: int,
        ocr_page_to: int,
        mappings: list[_Mapping],
    ) -> None:
        self.book_id = book_id
        self.pdf_path = pdf_path
        self.ocr_page_from = ocr_page_from
        self.ocr_page_to = ocr_page_to
        self.mappings = mappings

        self.gemini = GeminiOCRService()
        self.mathpix = MathpixService()
        self.image_extractor = ImageExtractor()

        self.gemini_call_count = 0
        self.mathpix_call_count = 0
        self._pages_dir: Optional[str] = None
        self._local_pdf: Optional[str] = None
        self._downloaded_pdf = False

    async def run(self) -> None:
        try:
            uniq_lessons = len({m.lesson_id for m in self.mappings})
            logger.info(
                "[%s] OCR pipeline start | PDF pages %s–%s | mapped_lessons=%d | pdf_ref=%s",
                self.book_id,
                self.ocr_page_from,
                self.ocr_page_to,
                uniq_lessons,
                _pdf_ref_for_log(self.pdf_path),
            )
            await self._update("ingesting", 5)
            await self._abort_if_cancelled()
            self._local_pdf = await self._materialize_pdf(self.pdf_path)

            output_dir = str(_book_data_dir(self.book_id))
            os.makedirs(output_dir, exist_ok=True)

            logger.info(
                "[%s] STEP 1/3: Rendering PDF pages %d–%d…",
                self.book_id, self.ocr_page_from, self.ocr_page_to,
            )
            await self._abort_if_cancelled()
            pages_info: list[PageInfo] = render_pages(
                self._local_pdf,
                output_dir,
                page_from=self.ocr_page_from,
                page_to=self.ocr_page_to,
            )
            self._pages_dir = os.path.join(output_dir, "pages")
            total = len(pages_info)
            await book_repository.update_total_pages(self.book_id, total)
            logger.info("[%s] STEP 1/3 done: %d pages rendered.", self.book_id, total)

            if total == 0:
                # Empty window — nothing to OCR but not an error. Mark done so
                # the BE can advance the book status.
                await self._update_done()
                return

            await self._abort_if_cancelled()
            # Drop pages from a previous OCR run for the lessons we're about
            # to (re-)process. This keeps the collection consistent when an
            # admin remaps pages and re-triggers OCR.
            await self._purge_stale_pages()

            logger.info("[%s] STEP 2/3: Gemini OCR…", self.book_id)
            await self._update("analyzing", 10)
            page_analyses, image_results = await self._run_gemini_batched(pages_info, total)
            logger.info("[%s] STEP 2/3 done: %d pages analyzed.", self.book_id, total)

            await self._abort_if_cancelled()
            logger.info("[%s] STEP 3/3: Persisting lesson_pages…", self.book_id)
            await self._update("saving", 90)
            await self._persist_pages(pages_info, page_analyses, image_results)

            await self._update_done()
            logger.info(
                "[%s] Pipeline complete — gemini_calls=%d, mathpix_calls=%d",
                self.book_id, self.gemini_call_count, self.mathpix_call_count,
            )

        except OcrCancelled:
            logger.info("[%s] OCR cancelled by user.", self.book_id)
        except FileNotFoundError as e:
            err = str(e)
            logger.error("[%s] PDF missing / unreachable: %s", self.book_id, err)
            try:
                await book_repository.update_status(self.book_id, "error", error=err[:800])
            except Exception:
                pass
        except Exception:
            logger.exception("Pipeline failed for book_id=%s", self.book_id)
            try:
                await book_repository.update_status(
                    self.book_id, "error", error="Pipeline failed — see server logs"
                )
            except Exception:
                pass
        finally:
            self._cleanup_temp_pdf()

    # ------------------------------------------------------------------
    # PDF acquisition
    # ------------------------------------------------------------------

    async def _materialize_pdf(self, pdf_path: str) -> str:
        """Resolve `pdf_path` to a local file.

        Supports:
        - ``http(s)://…`` — download (e.g. presigned URL).
        - Existing filesystem path (relative or absolute).
        - MinIO object key when ``MINIO_*`` env is set (same bucket as Spring uploads).
        """
        parsed = urlparse(pdf_path)
        if parsed.scheme in ("http", "https"):
            local = _book_data_dir(self.book_id) / "original.pdf"
            local.parent.mkdir(parents=True, exist_ok=True)
            logger.info("[%s] PDF source=HTTP GET → %s", self.book_id, _pdf_ref_for_log(pdf_path))
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                resp = await client.get(pdf_path)
                resp.raise_for_status()
                local.write_bytes(resp.content)
            self._downloaded_pdf = True
            logger.info("[%s] PDF saved locally (%d bytes) → %s", self.book_id, local.stat().st_size, local)
            return str(local)

        if os.path.isfile(pdf_path):
            logger.info("[%s] PDF source=local file → %s", self.book_id, pdf_path)
            return pdf_path

        abs_try = os.path.abspath(pdf_path)
        if os.path.isfile(abs_try):
            logger.info("[%s] PDF source=local file → %s", self.book_id, abs_try)
            return abs_try

        if minio_download_configured():
            local = _book_data_dir(self.book_id) / "original.pdf"
            key = pdf_path.strip().lstrip("/")
            logger.info(
                "[%s] PDF source=MinIO bucket=%s key=%s",
                self.book_id,
                settings.minio_template_bucket,
                key,
            )
            await asyncio.to_thread(download_template_bucket_object, key, local)
            self._downloaded_pdf = True
            logger.info("[%s] PDF fetched from MinIO (%d bytes) → %s", self.book_id, local.stat().st_size, local)
            return str(local)

        raise FileNotFoundError(
            f"PDF not found: {pdf_path}. "
            "Either place the file on this machine, pass an https presigned URL, "
            "or set MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY "
            f"(and MINIO_TEMPLATE_BUCKET={settings.minio_template_bucket!r}) "
            "to match Spring Boot."
        )

    def _cleanup_temp_pdf(self) -> None:
        if self._downloaded_pdf and self._local_pdf and os.path.isfile(self._local_pdf):
            try:
                os.remove(self._local_pdf)
            except Exception:
                logger.debug("[%s] Could not remove temp PDF", self.book_id, exc_info=True)
        if not _KEEP_PAGE_IMAGES and self._pages_dir and os.path.isdir(self._pages_dir):
            try:
                shutil.rmtree(self._pages_dir)
            except Exception:
                logger.debug("[%s] Could not clean pages dir", self.book_id, exc_info=True)

    # ------------------------------------------------------------------
    # Gemini batching (mirrors the legacy pipeline; unchanged semantics)
    # ------------------------------------------------------------------

    async def _run_gemini_batched(
        self, pages_info: list[PageInfo], total: int
    ) -> tuple[list[PageAnalysis], dict[tuple[int, int], ImageResult]]:
        page_analyses: list[Optional[PageAnalysis]] = [None] * total
        image_results: dict[tuple[int, int], ImageResult] = {}

        async def _analyze_one(p: PageInfo) -> PageAnalysis:
            return await self.gemini.analyze_page(p.image_path, p.page_num)

        num_batches = (total + _GEMINI_BATCH_SIZE - 1) // _GEMINI_BATCH_SIZE
        for start_idx in range(0, total, _GEMINI_BATCH_SIZE):
            await self._abort_if_cancelled()
            batch = pages_info[start_idx:start_idx + _GEMINI_BATCH_SIZE]
            batch_idx = start_idx // _GEMINI_BATCH_SIZE + 1
            page_nums = [p.page_num for p in batch]
            logger.info(
                "[%s] Gemini OCR batch %d/%d | PDF pages %s (size=%d)",
                self.book_id,
                batch_idx,
                num_batches,
                page_nums,
                len(batch),
            )
            try:
                results = await asyncio.gather(*(_analyze_one(p) for p in batch))
            except Exception:
                logger.exception(
                    "[%s] Gemini batch %d-%d failed",
                    self.book_id, start_idx + 1, start_idx + len(batch),
                )
                raise

            for offset, (page_info, analysis) in enumerate(zip(batch, results)):
                self.gemini_call_count += 1
                analysis = await self._mathpix_full_page_fallback(page_info, analysis)
                analysis = await self._apply_mathpix_fallback(analysis, page_info)
                image_results.update(await self._extract_images(analysis, page_info))
                page_analyses[start_idx + offset] = analysis
                await book_repository.increment_processed_pages(self.book_id)

            done_count = start_idx + len(batch)
            progress = 10 + int(done_count / total * 75)
            await self._update("analyzing", progress, f"Page {done_count}/{total}")
            logger.info(
                "[%s] Gemini batch %d/%d finished | analyzed_through_page=%d/%d | gemini_calls=%d",
                self.book_id,
                batch_idx,
                num_batches,
                done_count,
                total,
                self.gemini_call_count,
            )

        # Drop raw_response to free memory before persistence.
        for a in page_analyses:
            if a is not None:
                a.raw_response = ""
        return [a for a in page_analyses if a is not None], image_results

    async def _mathpix_full_page_fallback(
        self, page_info: PageInfo, analysis: PageAnalysis
    ) -> PageAnalysis:
        """When Gemini returns no blocks (JSON parse failure / empty), OCR the whole page via Mathpix."""
        if analysis.blocks or not self.mathpix.is_enabled():
            return analysis

        logger.info(
            "[%s] PDF page %d: no Gemini blocks — full-page Mathpix retry",
            self.book_id,
            page_info.page_num,
        )
        mp_label = f"[{self.book_id}] pdf_page={page_info.page_num}"
        result = await self.mathpix.extract_full_page(
            page_info.image_path,
            log_label=mp_label,
        )
        self.mathpix_call_count += 1

        body = (result.text or "").strip() or latex_to_readable(result.latex).strip()
        latex_part = (result.latex or "").strip()

        if not result.success or not body:
            logger.warning(
                "[%s] PDF page %d: full-page Mathpix produced no usable text "
                "(success=%s conf=%.4f text_len=%d latex_len=%d)",
                self.book_id,
                page_info.page_num,
                result.success,
                result.confidence,
                len((result.text or "").strip()),
                len(latex_part),
            )
            return analysis

        logger.info(
            "[%s] PDF page %d: full-page Mathpix OK → 1 text block "
            "(conf=%.4f content_len=%d latex_kept=%s)",
            self.book_id,
            page_info.page_num,
            float(result.confidence or 0.0),
            len(body),
            bool(latex_part and validate_latex(latex_part)),
        )

        safe_latex = latex_part if validate_latex(latex_part) else ""
        fallback_blocks = [
            GeminiBlock(
                type="text",
                content=body,
                latex=safe_latex,
                order=1,
                confidence=float(result.confidence or 0.75),
                source="mathpix",
                needs_mathpix=False,
            )
        ]
        return PageAnalysis(
            page_num=analysis.page_num,
            blocks=fallback_blocks,
            raw_response="",
            processing_time_ms=analysis.processing_time_ms,
        )

    async def _apply_mathpix_fallback(
        self, analysis: PageAnalysis, page_info: PageInfo
    ) -> PageAnalysis:
        if not self.mathpix.is_enabled():
            return analysis

        mp_prefix = f"[{self.book_id}] pdf_page={page_info.page_num}"
        checked = 0
        skipped_bbox = 0
        skipped_gate = 0
        upgraded = 0

        for block in analysis.blocks:
            if block.type != "formula":
                continue
            if not (block.needs_mathpix or block.confidence < 0.6):
                skipped_gate += 1
                continue
            checked += 1
            bbox = block.image_bbox
            if not bbox or len(bbox) != 4:
                skipped_bbox += 1
                logger.info(
                    "%s Mathpix formula skip (no bbox) | block_order=%d "
                    "needs_mathpix=%s conf=%.4f",
                    mp_prefix,
                    block.order,
                    block.needs_mathpix,
                    block.confidence,
                )
                continue
            label = f"{mp_prefix} block_order={block.order}"
            logger.info(
                "%s Mathpix formula attempt | bbox=%s gemini_conf=%.4f "
                "needs_mathpix=%s latex_len=%d",
                mp_prefix,
                bbox,
                block.confidence,
                block.needs_mathpix,
                len(block.latex or ""),
            )
            result = await self.mathpix.extract_formula(
                page_info.image_path,
                tuple(bbox),
                gemini_latex=block.latex,
                log_label=label,
            )
            if result.success and result.confidence > block.confidence:
                prev_conf = block.confidence
                block.latex = result.latex
                block.source = "mathpix"
                self.mathpix_call_count += 1
                upgraded += 1
                logger.info(
                    "%s Mathpix formula upgraded | block_order=%d "
                    "conf %.4f→%.4f latex_len=%d",
                    mp_prefix,
                    block.order,
                    prev_conf,
                    result.confidence,
                    len(result.latex or ""),
                )
            else:
                logger.info(
                    "%s Mathpix formula unchanged | block_order=%d "
                    "mathpix_success=%s mathpix_conf=%.4f gemini_conf=%.4f",
                    mp_prefix,
                    block.order,
                    result.success,
                    result.confidence,
                    block.confidence,
                )

        if checked or skipped_gate:
            logger.debug(
                "[%s] pdf_page=%d Mathpix formula scan | "
                "checked=%d upgraded=%d skipped_gate=%d skipped_bbox=%d",
                self.book_id,
                page_info.page_num,
                checked,
                upgraded,
                skipped_gate,
                skipped_bbox,
            )
        return analysis


    async def _extract_images(
        self, analysis: PageAnalysis, page_info: PageInfo
    ) -> dict[tuple[int, int], ImageResult]:
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

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _purge_stale_pages(self) -> None:
        """Drop existing pages for the lessons in this run before writing
        fresh ones. This preserves pages for OTHER lessons of the same book
        — useful when an admin re-OCRs a single chapter."""
        seen: set[str] = set()
        for m in self.mappings:
            if m.lesson_id in seen:
                continue
            seen.add(m.lesson_id)
            await lesson_page_repository.delete_by_book_and_lesson(
                self.book_id, m.lesson_id
            )

    async def _persist_pages(
        self,
        pages_info: list[PageInfo],
        analyses: list[PageAnalysis],
        image_results: dict[tuple[int, int], ImageResult],
    ) -> None:
        analyses_by_page = {a.page_num: a for a in analyses}
        page_image_url_by_page = {
            p.page_num: self._page_image_url(p) for p in pages_info
        }

        total_pages = len(analyses_by_page)
        persisted_pages = 0
        persisted_docs = 0

        for i, (page_num, analysis) in enumerate(analyses_by_page.items()):
            if i % 5 == 0:
                await self._abort_if_cancelled()
            lesson_ids = self._lessons_for_page(page_num)
            if not lesson_ids:
                logger.debug(
                    "[%s] page %d has no lesson mapping — skipping",
                    self.book_id, page_num,
                )
                continue
            blocks = self._convert_blocks(page_num, analysis, image_results)
            avg_conf = self._avg_confidence(analysis)
            ocr_source = self._ocr_source_for_analysis(analysis)
            for lesson_id in lesson_ids:
                await lesson_page_repository.upsert_page(
                    book_id=self.book_id,
                    lesson_id=lesson_id,
                    page_number=page_num,
                    content_blocks=blocks,
                    raw_image_url=page_image_url_by_page.get(page_num),
                    ocr_confidence=avg_conf,
                    ocr_source=ocr_source,
                )
                persisted_docs += 1

            persisted_pages += 1
            if persisted_pages % 10 == 0 or persisted_pages == total_pages:
                logger.info(
                    "[%s] Persist progress: %d/%d pages (%d lesson-page docs)",
                    self.book_id,
                    persisted_pages,
                    total_pages,
                    persisted_docs,
                )

    def _lessons_for_page(self, page_num: int) -> list[str]:
        return [
            m.lesson_id
            for m in self.mappings
            if m.page_start <= page_num <= m.page_end
        ]

    def _page_image_url(self, page_info: PageInfo) -> str:
        # Served by the FastAPI StaticFiles mount in main.py.
        rel = os.path.relpath(page_info.image_path, settings.storage_path).replace(os.sep, "/")
        return f"/static/{rel}"

    @staticmethod
    def _ocr_source_for_analysis(analysis: PageAnalysis) -> str:
        if not analysis.blocks:
            return "gemini"
        sources = {getattr(b, "source", "gemini") or "gemini" for b in analysis.blocks}
        if sources <= {"mathpix"}:
            return "mathpix"
        if "mathpix" in sources:
            return "hybrid"
        return "gemini"

    @staticmethod
    def _avg_confidence(analysis: PageAnalysis) -> Optional[float]:
        if not analysis.blocks:
            return None
        confs = [b.confidence for b in analysis.blocks if b.confidence is not None]
        if not confs:
            return None
        return round(sum(confs) / len(confs), 4)

    @staticmethod
    def _convert_blocks(
        page_num: int,
        analysis: PageAnalysis,
        image_results: dict[tuple[int, int], ImageResult],
    ) -> list[ContentBlockSchema]:
        out: list[ContentBlockSchema] = []
        for block in analysis.blocks:
            img = image_results.get((page_num, block.order))
            out.append(
                ContentBlockSchema(
                    order=block.order,
                    type=block.type,
                    content=block.content or None,
                    latex=block.latex or None,
                    caption=block.caption or None,
                    confidence=block.confidence,
                    source=block.source,
                    image_url=img.url if img else None,
                    # Keep API-friendly path (static URL or object key), never absolute server path.
                    image_path=img.url if img else None,
                    thumbnail_url=img.thumbnail_url if img else None,
                )
            )
        return out

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    async def _abort_if_cancelled(self) -> None:
        if not await book_repository.is_cancel_requested(self.book_id):
            return
        await book_repository.clear_cancel_requested(self.book_id)
        await book_repository.update_status(
            self.book_id,
            "error",
            error="Đã hủy bởi người dùng",
        )
        raise OcrCancelled()

    async def _update(self, phase: str, progress: int, message: str = "") -> None:
        await book_repository.update_status(self.book_id, "processing", progress, phase)
        logger.info(
            "[%s] status=processing phase=%s progress=%d%%%s",
            self.book_id,
            phase,
            progress,
            f" message={message}" if message else "",
        )

    async def _update_done(self) -> None:
        await book_repository.update_status(self.book_id, "done", 100, "done")
        await book_repository.increment_api_calls(
            self.book_id, gemini=self.gemini_call_count, mathpix=self.mathpix_call_count
        )
