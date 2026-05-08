"""Unit tests: Mathpix full-page retry when Gemini returns no blocks."""

from __future__ import annotations

import os

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("GEMINI_API_KEY", "fake-test-key-for-mathpix-fallback-tests")

from app.services.gemini_service import ContentBlock, PageAnalysis
from app.services.mathpix_service import MathpixResult
from app.services.pdf_parser import PageInfo
from app.services.processing_pipeline import MappingPipeline, _Mapping


@pytest.fixture
def sample_page_info() -> PageInfo:
    return PageInfo(
        page_num=16,
        image_path="/tmp/ocr_page_test.jpg",
        file_size_kb=120.0,
        width=1200,
        height=1600,
        is_grayscale=True,
    )


@pytest.mark.asyncio
async def test_full_page_fallback_populates_when_gemini_empty(sample_page_info: PageInfo) -> None:
    mock_mathpix = MagicMock()
    mock_mathpix.is_enabled.return_value = True
    mock_mathpix.extract_full_page = AsyncMock(
        return_value=MathpixResult(
            latex="",
            text="  OCR recovered text  ",
            confidence=0.88,
            success=True,
        )
    )

    with patch("app.services.processing_pipeline.GeminiOCRService"):
        pipe = MappingPipeline(
            "book1",
            "/fake.pdf",
            1,
            10,
            [_Mapping("les1", 1, 10)],
        )
    pipe.mathpix = mock_mathpix
    pipe.mathpix_call_count = 0

    empty = PageAnalysis(
        page_num=16,
        blocks=[],
        raw_response="not-json",
        processing_time_ms=100,
    )
    out = await pipe._mathpix_full_page_fallback(sample_page_info, empty)

    mock_mathpix.extract_full_page.assert_awaited_once_with(
        sample_page_info.image_path,
        log_label="[book1] pdf_page=16",
    )
    assert pipe.mathpix_call_count == 1
    assert len(out.blocks) == 1
    assert out.blocks[0].content == "OCR recovered text"
    assert out.blocks[0].source == "mathpix"


@pytest.mark.asyncio
async def test_full_page_fallback_skips_when_blocks_present(sample_page_info: PageInfo) -> None:
    mock_mathpix = MagicMock()
    mock_mathpix.is_enabled.return_value = True
    mock_mathpix.extract_full_page = AsyncMock()

    with patch("app.services.processing_pipeline.GeminiOCRService"):
        pipe = MappingPipeline(
            "book1",
            "/fake.pdf",
            1,
            10,
            [_Mapping("les1", 1, 10)],
        )
    pipe.mathpix = mock_mathpix

    analysis = PageAnalysis(
        page_num=16,
        blocks=[ContentBlock(type="text", content="ok", order=1)],
        raw_response="{}",
        processing_time_ms=50,
    )
    out = await pipe._mathpix_full_page_fallback(sample_page_info, analysis)

    mock_mathpix.extract_full_page.assert_not_called()
    assert out is analysis


@pytest.mark.asyncio
async def test_full_page_fallback_skips_when_mathpix_disabled(sample_page_info: PageInfo) -> None:
    mock_mathpix = MagicMock()
    mock_mathpix.is_enabled.return_value = False
    mock_mathpix.extract_full_page = AsyncMock()

    with patch("app.services.processing_pipeline.GeminiOCRService"):
        pipe = MappingPipeline(
            "book1",
            "/fake.pdf",
            1,
            10,
            [_Mapping("les1", 1, 10)],
        )
    pipe.mathpix = mock_mathpix
    pipe.mathpix_call_count = 0

    empty = PageAnalysis(page_num=16, blocks=[], raw_response="", processing_time_ms=1)
    out = await pipe._mathpix_full_page_fallback(sample_page_info, empty)

    mock_mathpix.extract_full_page.assert_not_called()
    assert pipe.mathpix_call_count == 0
    assert out.blocks == []


@pytest.mark.asyncio
async def test_ocr_source_all_mathpix() -> None:
    analysis = PageAnalysis(
        page_num=1,
        blocks=[
            ContentBlock(type="text", content="x", order=1, source="mathpix"),
        ],
        processing_time_ms=1,
    )
    assert MappingPipeline._ocr_source_for_analysis(analysis) == "mathpix"


@pytest.mark.asyncio
async def test_ocr_source_hybrid() -> None:
    analysis = PageAnalysis(
        page_num=1,
        blocks=[
            ContentBlock(type="text", content="a", order=1, source="gemini"),
            ContentBlock(type="formula", content="", latex="x", order=2, source="mathpix"),
        ],
        processing_time_ms=1,
    )
    assert MappingPipeline._ocr_source_for_analysis(analysis) == "hybrid"
