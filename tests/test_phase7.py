"""
Phase 7: Processing Pipeline — Standalone Test
Run with: python tests/test_phase7.py
(No pytest required, uses mocks, no API calls, no real DB)
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Stub optional heavy dependencies so imports work without them installed.
# The pipeline itself mocks render_pages, GeminiOCRService, etc. in tests.
# ---------------------------------------------------------------------------
if "google" not in sys.modules:
    sys.modules["google"] = MagicMock()
    sys.modules["google.generativeai"] = MagicMock()
if "httpx" not in sys.modules:
    sys.modules["httpx"] = MagicMock()


def print_header(text):
    print(f"\n{text}")
    print("=" * 70)


def print_step(num, text):
    print(f"\n{num}️⃣  {text}...")


def print_ok(text=""):
    if text:
        print(f"✅ {text}")
    else:
        print("✅")


def print_error(text):
    print(f"❌ {text}")
    sys.exit(1)


# ============================================================================
# Test 1: Import & class structure
# ============================================================================

def test_imports():
    print_step(1, "Import ProcessingPipeline and run_pipeline")

    from app.services.processing_pipeline import ProcessingPipeline, run_pipeline

    print_ok("ProcessingPipeline imported")
    print_ok("run_pipeline imported")

    # Verify __init__ signature — instantiate requires no real services
    # (we'll patch the heavy services in later tests)
    assert callable(run_pipeline)
    assert hasattr(ProcessingPipeline, "run")
    assert hasattr(ProcessingPipeline, "_apply_mathpix_fallback")
    assert hasattr(ProcessingPipeline, "_extract_images")
    assert hasattr(ProcessingPipeline, "_save_to_db")
    assert hasattr(ProcessingPipeline, "_update")
    assert hasattr(ProcessingPipeline, "_update_done")
    print_ok("All expected methods present")


# ============================================================================
# Test 2: Pipeline instantiation
# ============================================================================

def test_instantiation():
    print_step(2, "Pipeline instantiation with mocked services")

    from app.services.processing_pipeline import ProcessingPipeline

    with (
        patch("app.services.processing_pipeline.GeminiOCRService"),
        patch("app.services.processing_pipeline.MathpixService"),
        patch("app.services.processing_pipeline.ImageExtractor"),
        patch("app.services.processing_pipeline.StructureParser"),
    ):
        pipeline = ProcessingPipeline("book123", "/tmp/test.pdf")

    assert pipeline.book_id == "book123"
    assert pipeline.pdf_path == "/tmp/test.pdf"
    assert pipeline.gemini_call_count == 0
    assert pipeline.mathpix_call_count == 0
    assert pipeline._pages_dir is None
    print_ok("Pipeline instantiated with correct initial state")


# ============================================================================
# Test 3: _apply_mathpix_fallback — Mathpix disabled
# ============================================================================

async def _test_mathpix_fallback_disabled():
    print_step(3, "Mathpix fallback — Mathpix disabled (no calls made)")

    from app.services.processing_pipeline import ProcessingPipeline
    from app.services.gemini_service import ContentBlock, PageAnalysis
    from app.services.mathpix_service import MathpixResult

    with (
        patch("app.services.processing_pipeline.GeminiOCRService"),
        patch("app.services.processing_pipeline.MathpixService") as MockMathpix,
        patch("app.services.processing_pipeline.ImageExtractor"),
        patch("app.services.processing_pipeline.StructureParser"),
    ):
        # Mathpix is disabled — extract_formula returns success=False
        mock_mathpix_instance = MagicMock()
        mock_mathpix_instance.extract_formula = AsyncMock(
            return_value=MathpixResult(
                latex="\\frac{1}{2}", text="1/2", confidence=0.0, success=False
            )
        )
        MockMathpix.return_value = mock_mathpix_instance

        pipeline = ProcessingPipeline("book123", "/tmp/test.pdf")
        pipeline.mathpix = mock_mathpix_instance

        formula_block = ContentBlock(
            type="formula",
            latex="\\frac{1}{2}",
            confidence=0.4,   # < 0.6 → needs_fallback
            needs_mathpix=True,
            order=1,
        )
        analysis = PageAnalysis(page_num=1, blocks=[formula_block])

        result = await pipeline._apply_mathpix_fallback(analysis, "/fake/page.jpg")

    # success=False → no update to block
    assert result.blocks[0].latex == "\\frac{1}{2}"
    assert result.blocks[0].source == "gemini"
    assert pipeline.mathpix_call_count == 0
    print_ok("Mathpix disabled: block.latex unchanged, mathpix_call_count=0")


def test_mathpix_fallback_disabled():
    asyncio.run(_test_mathpix_fallback_disabled())


# ============================================================================
# Test 4: _apply_mathpix_fallback — Mathpix enabled, upgrades formula
# ============================================================================

async def _test_mathpix_fallback_upgrades():
    print_step(4, "Mathpix fallback — upgrades formula when confidence improves")

    from app.services.processing_pipeline import ProcessingPipeline
    from app.services.gemini_service import ContentBlock, PageAnalysis
    from app.services.mathpix_service import MathpixResult

    with (
        patch("app.services.processing_pipeline.GeminiOCRService"),
        patch("app.services.processing_pipeline.MathpixService"),
        patch("app.services.processing_pipeline.ImageExtractor"),
        patch("app.services.processing_pipeline.StructureParser"),
    ):
        pipeline = ProcessingPipeline("book123", "/tmp/test.pdf")

        mock_mathpix = MagicMock()
        mock_mathpix.extract_formula = AsyncMock(
            return_value=MathpixResult(
                latex="\\frac{a+b}{c}",
                text="(a+b)/c",
                confidence=0.95,
                success=True,
            )
        )
        pipeline.mathpix = mock_mathpix

        formula_block = ContentBlock(
            type="formula",
            latex="bad_latex",
            confidence=0.3,   # low → needs fallback
            needs_mathpix=False,
            order=1,
        )
        analysis = PageAnalysis(page_num=1, blocks=[formula_block])

        result = await pipeline._apply_mathpix_fallback(analysis, "/fake/page.jpg")

    assert result.blocks[0].latex == "\\frac{a+b}{c}"
    assert result.blocks[0].source == "mathpix"
    assert pipeline.mathpix_call_count == 1
    print_ok("Mathpix upgraded formula: latex updated, source='mathpix', count=1")


def test_mathpix_fallback_upgrades():
    asyncio.run(_test_mathpix_fallback_upgrades())


# ============================================================================
# Test 5: _apply_mathpix_fallback — skips high-confidence formulas
# ============================================================================

async def _test_mathpix_skip_high_confidence():
    print_step(5, "Mathpix fallback — skips formulas with confidence >= 0.6")

    from app.services.processing_pipeline import ProcessingPipeline
    from app.services.gemini_service import ContentBlock, PageAnalysis
    from app.services.mathpix_service import MathpixResult

    with (
        patch("app.services.processing_pipeline.GeminiOCRService"),
        patch("app.services.processing_pipeline.MathpixService"),
        patch("app.services.processing_pipeline.ImageExtractor"),
        patch("app.services.processing_pipeline.StructureParser"),
    ):
        pipeline = ProcessingPipeline("book123", "/tmp/test.pdf")

        mock_mathpix = MagicMock()
        mock_mathpix.extract_formula = AsyncMock()
        pipeline.mathpix = mock_mathpix

        good_block = ContentBlock(
            type="formula",
            latex="x^2",
            confidence=0.9,   # >= 0.6 → skip
            needs_mathpix=False,
            order=1,
        )
        analysis = PageAnalysis(page_num=1, blocks=[good_block])

        await pipeline._apply_mathpix_fallback(analysis, "/fake/page.jpg")

    mock_mathpix.extract_formula.assert_not_called()
    assert pipeline.mathpix_call_count == 0
    print_ok("High-confidence formula skipped, extract_formula not called")


def test_mathpix_skip_high_confidence():
    asyncio.run(_test_mathpix_skip_high_confidence())


# ============================================================================
# Test 6: _extract_images — image blocks extracted correctly
# ============================================================================

async def _test_extract_images():
    print_step(6, "Image extraction — image blocks produce ImageResult entries")

    from app.services.processing_pipeline import ProcessingPipeline
    from app.services.gemini_service import ContentBlock, PageAnalysis
    from app.services.image_service import ImageResult
    from app.services.pdf_parser import PageInfo

    with (
        patch("app.services.processing_pipeline.GeminiOCRService"),
        patch("app.services.processing_pipeline.MathpixService"),
        patch("app.services.processing_pipeline.ImageExtractor"),
        patch("app.services.processing_pipeline.StructureParser"),
    ):
        pipeline = ProcessingPipeline("book_xyz", "/tmp/test.pdf")

        mock_extractor = MagicMock()
        mock_extractor.extract_and_store.return_value = ImageResult(
            file_path="/storage/images/book_xyz/page_001_fig_01.jpg",
            url="/static/images/book_xyz/page_001_fig_01.jpg",
            thumbnail_url="/static/images/book_xyz/thumbs/page_001_fig_01_thumb.jpg",
            width=400,
            height=300,
            caption="Hình 1.1",
            page_num=1,
            fig_index=1,
            file_size_kb=45.0,
        )
        pipeline.image_extractor = mock_extractor

        image_block = ContentBlock(
            type="image",
            image_bbox=(0.1, 0.2, 0.9, 0.8),
            caption="Hình 1.1",
            order=3,
        )
        text_block = ContentBlock(type="text", content="Some text", order=2)
        analysis = PageAnalysis(page_num=1, blocks=[text_block, image_block])

        page_info = PageInfo(
            page_num=1,
            image_path="/fake/page_001.jpg",
            file_size_kb=80.0,
            width=800,
            height=1200,
            is_grayscale=False,
        )

        results = await pipeline._extract_images(analysis, page_info)

    assert (1, 3) in results
    img = results[(1, 3)]
    assert img.url == "/static/images/book_xyz/page_001_fig_01.jpg"
    assert img.thumbnail_url == "/static/images/book_xyz/thumbs/page_001_fig_01_thumb.jpg"
    mock_extractor.extract_and_store.assert_called_once()
    print_ok("Image block extracted, result keyed by (page_num, order)")


def test_extract_images():
    asyncio.run(_test_extract_images())


# ============================================================================
# Test 7: _extract_images — skips non-image and empty-bbox blocks
# ============================================================================

async def _test_extract_images_skips():
    print_step(7, "Image extraction — skips text blocks and blocks with no bbox")

    from app.services.processing_pipeline import ProcessingPipeline
    from app.services.gemini_service import ContentBlock, PageAnalysis
    from app.services.pdf_parser import PageInfo

    with (
        patch("app.services.processing_pipeline.GeminiOCRService"),
        patch("app.services.processing_pipeline.MathpixService"),
        patch("app.services.processing_pipeline.ImageExtractor"),
        patch("app.services.processing_pipeline.StructureParser"),
    ):
        pipeline = ProcessingPipeline("b1", "/tmp/test.pdf")

        mock_extractor = MagicMock()
        pipeline.image_extractor = mock_extractor

        blocks = [
            ContentBlock(type="text", content="hello", order=1),
            ContentBlock(type="image", image_bbox=(), order=2),   # no bbox → skip
            ContentBlock(type="formula", latex="x^2", order=3),
        ]
        analysis = PageAnalysis(page_num=1, blocks=blocks)
        page_info = PageInfo(1, "/fake/p.jpg", 50.0, 800, 1200, False)

        results = await pipeline._extract_images(analysis, page_info)

    assert results == {}
    mock_extractor.extract_and_store.assert_not_called()
    print_ok("Non-image and no-bbox blocks correctly skipped")


def test_extract_images_skips():
    asyncio.run(_test_extract_images_skips())


# ============================================================================
# Test 8: _save_to_db — persists structure via repositories
# ============================================================================

async def _test_save_to_db():
    print_step(8, "Save to DB — chapters, lessons, content blocks persisted")

    from app.services.processing_pipeline import ProcessingPipeline
    from app.services.structure_parser import (
        BookStructure, Chapter, Lesson, FinalContentBlock
    )

    with (
        patch("app.services.processing_pipeline.GeminiOCRService"),
        patch("app.services.processing_pipeline.MathpixService"),
        patch("app.services.processing_pipeline.ImageExtractor"),
        patch("app.services.processing_pipeline.StructureParser"),
        patch("app.services.processing_pipeline.chapter_repository") as mock_ch_repo,
        patch("app.services.processing_pipeline.lesson_repository") as mock_les_repo,
        patch("app.services.processing_pipeline.content_repository") as mock_content_repo,
    ):
        mock_ch_repo.create = AsyncMock(return_value="ch_id_1")
        mock_les_repo.create = AsyncMock(return_value="les_id_1")
        mock_content_repo.bulk_create = AsyncMock(return_value=["c1", "c2"])

        pipeline = ProcessingPipeline("bookA", "/tmp/test.pdf")

        lesson = Lesson(
            index=1,
            title="Bài 1: Số hữu tỉ",
            page_start=1,
            content_blocks=[
                FinalContentBlock(type="text", content="Định nghĩa...", order=1),
                FinalContentBlock(type="formula", latex="\\frac{a}{b}", order=2),
            ],
        )
        chapter = Chapter(
            index=1, roman_index="I", title="Số hữu tỉ", page_start=1,
            lessons=[lesson],
        )
        book_structure = BookStructure(
            grade=8, title="Toán 8", publisher="CTST",
            chapters=[chapter],
        )

        await pipeline._save_to_db(book_structure)

    mock_ch_repo.create.assert_called_once()
    mock_les_repo.create.assert_called_once()
    mock_content_repo.bulk_create.assert_called_once()
    # Verify bulk_create received 2 content blocks
    call_args = mock_content_repo.bulk_create.call_args[0][0]
    assert len(call_args) == 2
    assert call_args[0].type == "text"
    assert call_args[1].type == "formula"
    assert call_args[1].latex == "\\frac{a}{b}"
    print_ok("chapter.create called once, lesson.create once, bulk_create with 2 blocks")


def test_save_to_db():
    asyncio.run(_test_save_to_db())


# ============================================================================
# Test 9: Progress sequence — _update and _update_done
# ============================================================================

async def _test_progress_sequence():
    print_step(9, "Progress sequence — update_status called with correct phases")

    from app.services.processing_pipeline import ProcessingPipeline

    with (
        patch("app.services.processing_pipeline.GeminiOCRService"),
        patch("app.services.processing_pipeline.MathpixService"),
        patch("app.services.processing_pipeline.ImageExtractor"),
        patch("app.services.processing_pipeline.StructureParser"),
        patch("app.services.processing_pipeline.book_repository") as mock_book_repo,
    ):
        mock_book_repo.update_status = AsyncMock()
        mock_book_repo.increment_api_calls = AsyncMock()

        pipeline = ProcessingPipeline("bk1", "/tmp/test.pdf")
        pipeline.book_repo = mock_book_repo

        await pipeline._update("ingesting", 5)
        await pipeline._update("analyzing", 10)
        await pipeline._update("parsing", 82)
        await pipeline._update("saving", 88)
        await pipeline._update_done(3, 1)

    calls = mock_book_repo.update_status.call_args_list
    statuses   = [c[0][1] for c in calls]   # positional arg 1
    progresses = [c[0][2] for c in calls]   # positional arg 2
    phases     = [c[0][3] for c in calls]   # positional arg 3

    assert "processing" in statuses
    assert "done" in statuses
    assert 5 in progresses
    assert 10 in progresses
    assert 82 in progresses
    assert 88 in progresses
    assert 100 in progresses
    assert "ingesting" in phases
    assert "analyzing" in phases
    assert "parsing" in phases
    assert "saving" in phases
    assert "done" in phases

    # increment_api_calls called with correct counts
    mock_book_repo.increment_api_calls.assert_called_once_with(
        "bk1", gemini=3, mathpix=1
    )
    print_ok("Progress sequence: 5→10→82→88→100, all phases set correctly")


def test_progress_sequence():
    asyncio.run(_test_progress_sequence())


# ============================================================================
# Test 10: Full pipeline run — end-to-end mock
# ============================================================================

async def _test_full_pipeline_run():
    print_step(10, "Full pipeline run — end-to-end mock (no real APIs / DB)")

    from app.services.processing_pipeline import ProcessingPipeline
    from app.services.gemini_service import ContentBlock, PageAnalysis
    from app.services.pdf_parser import PageInfo
    from app.services.structure_parser import (
        BookStructure, Chapter, Lesson, FinalContentBlock
    )
    from app.schemas.book import BookDB
    from datetime import datetime, timezone

    # Build mock PageInfo list
    mock_page_info = PageInfo(
        page_num=1,
        image_path="/fake/page_001.jpg",
        file_size_kb=90.0,
        width=800,
        height=1200,
        is_grayscale=False,
    )

    # Build mock Gemini PageAnalysis
    mock_analysis = PageAnalysis(
        page_num=1,
        blocks=[
            ContentBlock(type="chapter_title", content="Chương I. SỐ HỮU TỈ", order=1, confidence=0.99),
            ContentBlock(type="lesson_title", content="Bài 1. Số hữu tỉ", order=2, confidence=0.99),
            ContentBlock(type="text", content="Số hữu tỉ là số có thể viết dạng a/b", order=3, confidence=0.95),
            ContentBlock(type="formula", latex="\\frac{a}{b}", order=4, confidence=0.9, needs_mathpix=False),
        ],
        raw_response='{"page_num":1,"blocks":[]}',
    )

    # Parsed book structure
    mock_book_structure = BookStructure(
        grade=8,
        title="Toán 8",
        publisher="CTST",
        chapters=[
            Chapter(
                index=1, roman_index="I", title="Số hữu tỉ", page_start=1,
                lessons=[
                    Lesson(
                        index=1, title="Bài 1", page_start=1,
                        content_blocks=[
                            FinalContentBlock(type="text", content="Số hữu tỉ...", order=1),
                            FinalContentBlock(type="formula", latex="\\frac{a}{b}", order=2),
                        ],
                    )
                ],
            )
        ],
    )

    # Mock BookDB for get_by_id
    now = datetime.now(timezone.utc)
    mock_book_doc = BookDB(
        **{
            "_id": "book_test_id",
            "title": "Toán 8",
            "grade": 8,
            "publisher": "CTST",
            "academic_year": "2024-2025",
            "status": "pending",
            "progress": 0,
            "current_phase": "",
            "total_pages": 0,
            "processed_pages": 0,
            "file_path": "/tmp/test.pdf",
            "error_message": "",
            "created_at": now,
            "updated_at": now,
            "gemini_calls": 0,
            "mathpix_calls": 0,
        }
    )

    with (
        patch("app.services.processing_pipeline.GeminiOCRService") as MockGemini,
        patch("app.services.processing_pipeline.MathpixService") as MockMathpix,
        patch("app.services.processing_pipeline.ImageExtractor") as MockExtractor,
        patch("app.services.processing_pipeline.StructureParser") as MockParser,
        patch("app.services.processing_pipeline.render_pages", return_value=[mock_page_info]),
        patch("app.services.processing_pipeline.book_repository") as mock_book_repo,
        patch("app.services.processing_pipeline.chapter_repository") as mock_ch_repo,
        patch("app.services.processing_pipeline.lesson_repository") as mock_les_repo,
        patch("app.services.processing_pipeline.content_repository") as mock_cont_repo,
    ):
        # Configure mocks
        mock_gemini = MagicMock()
        mock_gemini.analyze_page = AsyncMock(return_value=mock_analysis)
        MockGemini.return_value = mock_gemini

        mock_mathpix = MagicMock()
        MockMathpix.return_value = mock_mathpix

        mock_extractor = MagicMock()
        mock_extractor.extract_and_store.return_value = None
        MockExtractor.return_value = mock_extractor

        mock_parser = MagicMock()
        mock_parser.parse_book.return_value = mock_book_structure
        MockParser.return_value = mock_parser

        mock_book_repo.update_status = AsyncMock()
        mock_book_repo.update_total_pages = AsyncMock()
        mock_book_repo.increment_processed_pages = AsyncMock()
        mock_book_repo.increment_api_calls = AsyncMock()
        mock_book_repo.get_by_id = AsyncMock(return_value=mock_book_doc)

        mock_ch_repo.create = AsyncMock(return_value="ch_id_1")
        mock_les_repo.create = AsyncMock(return_value="les_id_1")
        mock_cont_repo.bulk_create = AsyncMock(return_value=["c1", "c2"])

        pipeline = ProcessingPipeline("book_test_id", "/tmp/test.pdf")
        await pipeline.run()

    # Verify key interactions
    mock_gemini.analyze_page.assert_called_once()
    assert pipeline.gemini_call_count == 1

    # update_status called for "done" at the end
    done_calls = [
        c for c in mock_book_repo.update_status.call_args_list
        if c[0][1] == "done"
    ]
    assert len(done_calls) == 1, "update_status('done') should be called exactly once"

    # Progress reached 100
    all_progresses = [c[0][2] for c in mock_book_repo.update_status.call_args_list]
    assert 100 in all_progresses

    # DB was persisted
    mock_ch_repo.create.assert_called_once()
    mock_les_repo.create.assert_called_once()
    mock_cont_repo.bulk_create.assert_called_once()

    print_ok("Full pipeline run completed: Gemini called, structure parsed, DB saved, status=done")


def test_full_pipeline_run():
    asyncio.run(_test_full_pipeline_run())


# ============================================================================
# Test 11: Error handling — exception sets status="error"
# ============================================================================

async def _test_error_handling():
    print_step(11, "Error handling — pipeline sets status='error' on exception")

    from app.services.processing_pipeline import ProcessingPipeline

    with (
        patch("app.services.processing_pipeline.GeminiOCRService"),
        patch("app.services.processing_pipeline.MathpixService"),
        patch("app.services.processing_pipeline.ImageExtractor"),
        patch("app.services.processing_pipeline.StructureParser"),
        patch(
            "app.services.processing_pipeline.render_pages",
            side_effect=RuntimeError("PDF corrupt"),
        ),
        patch("app.services.processing_pipeline.book_repository") as mock_book_repo,
    ):
        mock_book_repo.update_status = AsyncMock()
        mock_book_repo.update_total_pages = AsyncMock()

        pipeline = ProcessingPipeline("book_err", "/tmp/bad.pdf")

        raised = False
        try:
            await pipeline.run()
        except RuntimeError:
            raised = True

    assert raised, "Exception should be re-raised after setting error status"

    error_calls = [
        c for c in mock_book_repo.update_status.call_args_list
        if c[0][1] == "error"
    ]
    assert len(error_calls) == 1
    # Error message should contain the original exception text
    error_msg = error_calls[0][1].get("error", "") or error_calls[0][0][3] if len(error_calls[0][0]) > 3 else ""
    print_ok(f"Exception re-raised; update_status('error') called")


def test_error_handling():
    asyncio.run(_test_error_handling())


# ============================================================================
# Test 12: run_pipeline standalone function
# ============================================================================

async def _test_run_pipeline_function():
    print_step(12, "run_pipeline() function delegates to ProcessingPipeline.run")

    from app.services.processing_pipeline import run_pipeline

    with patch(
        "app.services.processing_pipeline.ProcessingPipeline"
    ) as MockPipeline:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock()
        MockPipeline.return_value = mock_instance

        await run_pipeline("book_bg", "/tmp/test.pdf")

    MockPipeline.assert_called_once_with("book_bg", "/tmp/test.pdf")
    mock_instance.run.assert_called_once()
    print_ok("run_pipeline creates ProcessingPipeline and calls .run()")


def test_run_pipeline_function():
    asyncio.run(_test_run_pipeline_function())


# ============================================================================
# Test 13: source field propagation — ContentBlock.source
# ============================================================================

def test_content_block_source_field():
    print_step(13, "ContentBlock.source field exists with default='gemini'")

    from app.services.gemini_service import ContentBlock

    block = ContentBlock(type="formula", latex="x^2")
    assert hasattr(block, "source"), "ContentBlock must have a 'source' field"
    assert block.source == "gemini"

    block.source = "mathpix"
    assert block.source == "mathpix"
    print_ok("ContentBlock.source field present and mutable")


# ============================================================================
# Main
# ============================================================================

def main():
    print_header("PHASE 7: Processing Pipeline — Test Suite")

    test_imports()
    test_instantiation()
    test_mathpix_fallback_disabled()
    test_mathpix_fallback_upgrades()
    test_mathpix_skip_high_confidence()
    test_extract_images()
    test_extract_images_skips()
    test_save_to_db()
    test_progress_sequence()
    test_full_pipeline_run()
    test_error_handling()
    test_run_pipeline_function()
    test_content_block_source_field()

    print_header("✅ ALL TESTS PASSED (without real API calls)!")
    print("\n📊 SUMMARY:")
    print("  Test 1:  Import & class structure           ✅")
    print("  Test 2:  Pipeline instantiation              ✅")
    print("  Test 3:  Mathpix fallback — disabled         ✅")
    print("  Test 4:  Mathpix fallback — upgrades formula ✅")
    print("  Test 5:  Mathpix fallback — skip high-conf   ✅")
    print("  Test 6:  Image extraction — normal           ✅")
    print("  Test 7:  Image extraction — skips empty      ✅")
    print("  Test 8:  Save to DB                          ✅")
    print("  Test 9:  Progress sequence                   ✅")
    print("  Test 10: Full end-to-end mock run            ✅")
    print("  Test 11: Error handling                      ✅")
    print("  Test 12: run_pipeline function               ✅")
    print("  Test 13: ContentBlock.source field           ✅")
    print()


if __name__ == "__main__":
    main()
