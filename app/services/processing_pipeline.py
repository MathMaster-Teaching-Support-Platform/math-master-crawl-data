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
from app.services.mathpix_service import MathpixService
from app.services.pdf_parser import PageInfo, render_pages

logger = logging.getLogger(__name__)


_KEEP_PAGE_IMAGES: bool = os.getenv("KEEP_PAGE_IMAGES", "false").lower() == "true"
_GEMINI_BATCH_SIZE: int = int(os.getenv("GEMINI_BATCH_SIZE", "5"))


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
            await self._update("ingesting", 5)
            self._local_pdf = await self._materialize_pdf(self.pdf_path)

            output_dir = str(_book_data_dir(self.book_id))
            os.makedirs(output_dir, exist_ok=True)

            logger.info(
                "[%s] STEP 1/3: Rendering PDF pages %d–%d…",
                self.book_id, self.ocr_page_from, self.ocr_page_to,
            )
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

            # Drop pages from a previous OCR run for the lessons we're about
            # to (re-)process. This keeps the collection consistent when an
            # admin remaps pages and re-triggers OCR.
            await self._purge_stale_pages()

            logger.info("[%s] STEP 2/3: Gemini OCR…", self.book_id)
            await self._update("analyzing", 10)
            page_analyses, image_results = await self._run_gemini_batched(pages_info, total)
            logger.info("[%s] STEP 2/3 done: %d pages analyzed.", self.book_id, total)

            logger.info("[%s] STEP 3/3: Persisting lesson_pages…", self.book_id)
            await self._update("saving", 90)
            await self._persist_pages(pages_info, page_analyses, image_results)

            await self._update_done()
            logger.info(
                "[%s] Pipeline complete — gemini_calls=%d, mathpix_calls=%d",
                self.book_id, self.gemini_call_count, self.mathpix_call_count,
            )

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
        """Resolve `pdf_path` to a local file. Accepts either an existing
        local path or an http(s) URL (e.g. a presigned MinIO URL)."""
        parsed = urlparse(pdf_path)
        if parsed.scheme in ("http", "https"):
            local = _book_data_dir(self.book_id) / "original.pdf"
            local.parent.mkdir(parents=True, exist_ok=True)
            logger.info("[%s] Downloading PDF from %s", self.book_id, pdf_path)
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                resp = await client.get(pdf_path)
                resp.raise_for_status()
                local.write_bytes(resp.content)
            self._downloaded_pdf = True
            return str(local)
        if not os.path.isfile(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        return pdf_path

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

        for start_idx in range(0, total, _GEMINI_BATCH_SIZE):
            batch = pages_info[start_idx:start_idx + _GEMINI_BATCH_SIZE]
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
                analysis = await self._apply_mathpix_fallback(analysis, page_info.image_path)
                image_results.update(await self._extract_images(analysis, page_info))
                page_analyses[start_idx + offset] = analysis
                await book_repository.increment_processed_pages(self.book_id)

            done_count = start_idx + len(batch)
            progress = 10 + int(done_count / total * 75)
            await self._update("analyzing", progress, f"Page {done_count}/{total}")

        # Drop raw_response to free memory before persistence.
        for a in page_analyses:
            if a is not None:
                a.raw_response = ""
        return [a for a in page_analyses if a is not None], image_results

    async def _apply_mathpix_fallback(
        self, analysis: PageAnalysis, page_image_path: str
    ) -> PageAnalysis:
        if not self.mathpix.is_enabled():
            return analysis
        for block in analysis.blocks:
            if block.type != "formula":
                continue
            if not (block.needs_mathpix or block.confidence < 0.6):
                continue
            bbox = block.image_bbox
            if not bbox or len(bbox) != 4:
                continue
            result = await self.mathpix.extract_formula(
                page_image_path, tuple(bbox), gemini_latex=block.latex
            )
            if result.success and result.confidence > block.confidence:
                block.latex = result.latex
                block.source = "mathpix"
                self.mathpix_call_count += 1
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

        for page_num, analysis in analyses_by_page.items():
            lesson_ids = self._lessons_for_page(page_num)
            if not lesson_ids:
                logger.debug(
                    "[%s] page %d has no lesson mapping — skipping",
                    self.book_id, page_num,
                )
                continue
            blocks = self._convert_blocks(page_num, analysis, image_results)
            avg_conf = self._avg_confidence(analysis)
            for lesson_id in lesson_ids:
                await lesson_page_repository.upsert_page(
                    book_id=self.book_id,
                    lesson_id=lesson_id,
                    page_number=page_num,
                    content_blocks=blocks,
                    raw_image_url=page_image_url_by_page.get(page_num),
                    ocr_confidence=avg_conf,
                    ocr_source="gemini",
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
                    image_path=img.file_path if img else None,
                    thumbnail_url=img.thumbnail_url if img else None,
                )
            )
        return out

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    async def _update(self, phase: str, progress: int, message: str = "") -> None:
        await book_repository.update_status(self.book_id, "processing", progress, phase)

    async def _update_done(self) -> None:
        await book_repository.update_status(self.book_id, "done", 100, "done")
        await book_repository.increment_api_calls(
            self.book_id, gemini=self.gemini_call_count, mathpix=self.mathpix_call_count
        )
