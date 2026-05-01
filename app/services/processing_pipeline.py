# Processing pipeline — Phase 7
import asyncio
import logging
import os
import shutil
from typing import Optional

from app.core.config import settings
from app.repositories.book_repository import book_repository
from app.repositories.chapter_repository import chapter_repository
from app.repositories.lesson_repository import lesson_repository
from app.repositories.content_repository import content_repository
from app.schemas.chapter import ChapterCreate
from app.schemas.lesson import LessonCreate
from app.schemas.content import ContentBlockCreate
from app.services.gemini_service import GeminiOCRService, PageAnalysis
from app.services.image_service import ImageExtractor, ImageResult
from app.services.mathpix_service import MathpixService
from app.services.pdf_parser import render_pages, PageInfo
from app.services.structure_parser import StructureParser, BookStructure

logger = logging.getLogger(__name__)

_KEEP_PAGE_IMAGES: bool = os.getenv("KEEP_PAGE_IMAGES", "false").lower() == "true"


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

    async def run(self) -> None:
        try:
            # STEP 1: Ingest PDF → page images
            await self._update("ingesting", 5)
            output_dir = os.path.join(settings.storage_path, "books", self.book_id)
            pages_info: list[PageInfo] = render_pages(self.pdf_path, output_dir)
            self._pages_dir = os.path.join(output_dir, "pages")
            total = len(pages_info)
            await self.book_repo.update_total_pages(self.book_id, total)

            # STEP 2: Per-page: Gemini OCR + Mathpix fallback + image extraction
            await self._update("analyzing", 10)
            page_analyses: list[PageAnalysis] = []
            all_image_results: dict[tuple[int, int], ImageResult] = {}

            for i, page_info in enumerate(pages_info):
                analysis = await self.gemini.analyze_page(
                    page_info.image_path, page_info.page_num
                )
                self.gemini_call_count += 1
                analysis.raw_response = ""  # free memory after processing

                analysis = await self._apply_mathpix_fallback(
                    analysis, page_info.image_path
                )
                page_img_results = await self._extract_images(analysis, page_info)
                all_image_results.update(page_img_results)

                page_analyses.append(analysis)
                await self.book_repo.increment_processed_pages(self.book_id)

                progress = 10 + int((i + 1) / total * 70)
                await self._update("analyzing", progress, f"Page {i + 1}/{total}")

            # STEP 3: Structure parse
            await self._update("parsing", 82)
            book_doc = await self.book_repo.get_by_id(self.book_id)
            book_structure: BookStructure = self.structure_parser.parse_book(
                page_analyses,
                grade=book_doc.grade if book_doc else 0,
                title=book_doc.title if book_doc else "",
                publisher=book_doc.publisher if book_doc else "",
                image_results=all_image_results,
            )

            # STEP 4: Save to MongoDB
            await self._update("saving", 88)
            await self._save_to_db(book_structure)

            # Done
            await self._update_done(self.gemini_call_count, self.mathpix_call_count)

        except Exception as exc:
            logger.exception("Pipeline failed for book_id=%s", self.book_id)
            await self.book_repo.update_status(self.book_id, "error", error=str(exc))
            raise

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    async def _apply_mathpix_fallback(
        self, analysis: PageAnalysis, page_image_path: str
    ) -> PageAnalysis:
        """Call Mathpix for formula blocks where Gemini had low confidence."""
        for block in analysis.blocks:
            if block.type != "formula":
                continue
            needs_fallback = block.needs_mathpix or block.confidence < 0.6
            if not needs_fallback:
                continue
            # Use block's image_bbox if available; otherwise use the full page
            bbox: tuple = block.image_bbox if block.image_bbox else (0.0, 0.0, 1.0, 1.0)
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
        """Persist the parsed book structure to MongoDB."""
        for chapter in book_structure.chapters:
            ch_id = await chapter_repository.create(
                ChapterCreate(
                    book_id=self.book_id,
                    chapter_index=chapter.index,
                    roman_index=chapter.roman_index,
                    title=chapter.title,
                    page_start=chapter.page_start,
                )
            )
            for lesson in chapter.lessons:
                les_id = await lesson_repository.create(
                    LessonCreate(
                        chapter_id=ch_id,
                        lesson_index=lesson.index,
                        title=lesson.title,
                        page_start=lesson.page_start,
                    )
                )
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
    pipeline = ProcessingPipeline(book_id, pdf_path)
    await pipeline.run()
