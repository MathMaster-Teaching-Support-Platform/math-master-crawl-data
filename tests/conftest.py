"""
tests/conftest.py — Shared fixtures for Phase 9 E2E tests.

IMPORTANT: env vars must be set BEFORE any app module is imported,
because app.core.mongo reads MONGO_DB at module level.
"""

import io
import os

# ---------------------------------------------------------------------------
# Override env vars for test isolation — must happen before app imports.
# ---------------------------------------------------------------------------
os.environ["MONGO_DB"] = "sgk_toan_test"
os.environ.setdefault("GEMINI_API_KEY", "fake-test-key-for-testing")
os.environ["MATHPIX_ENABLED"] = "false"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Test PDF fixture (created programmatically with reportlab)
# ---------------------------------------------------------------------------

def _build_test_pdf_bytes() -> bytes:
    """Return bytes of a minimal 3-page test PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # Page 1 — chapter title
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, 780, "CHUONG I. SO HUU TI")
    c.showPage()

    # Page 2 — lesson title + text + formula hint
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 780, "Bai 1. So huu ti")
    c.setFont("Helvetica", 12)
    c.drawString(50, 750, "So huu ti la so co the viet duoi dang a/b voi b khac 0.")
    c.drawString(50, 730, "Vi du: 1/2, -3/4, 0.5")
    c.showPage()

    # Page 3 — exercise
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 780, "Vi du 1: Tim so huu ti trong cac so sau.")
    c.setFont("Helvetica", 12)
    c.drawString(50, 760, "Giai: 0,5 = 1/2 la so huu ti.")
    c.drawString(50, 740, "Hinh ve: truc so")
    c.showPage()

    c.save()
    return buf.getvalue()


@pytest.fixture(scope="session")
def test_pdf_bytes() -> bytes:
    return _build_test_pdf_bytes()


@pytest.fixture(scope="session")
def test_pdf_path(test_pdf_bytes, tmp_path_factory) -> str:
    """Persist the test PDF to a session-scoped temp directory."""
    tmp_dir = tmp_path_factory.mktemp("test_pdfs")
    pdf_path = tmp_dir / "test_book.pdf"
    pdf_path.write_bytes(test_pdf_bytes)
    return str(pdf_path)


# ---------------------------------------------------------------------------
# Mock page analyses that GeminiOCRService.analyze_page will return
# ---------------------------------------------------------------------------

def _make_page_analyses():
    from app.services.gemini_service import ContentBlock, PageAnalysis

    return [
        # Page 1: chapter title
        PageAnalysis(
            page_num=1,
            blocks=[
                ContentBlock(
                    type="chapter_title",
                    content="CHƯƠNG I. SỐ HỮU TỈ",
                    order=1,
                    confidence=0.99,
                ),
            ],
        ),
        # Page 2: lesson + text + formula
        PageAnalysis(
            page_num=2,
            blocks=[
                ContentBlock(
                    type="lesson_title",
                    content="Bài 1. Số hữu tỉ",
                    order=1,
                    confidence=0.99,
                ),
                ContentBlock(
                    type="text",
                    content="Số hữu tỉ là số có thể viết dưới dạng a/b với b khác 0.",
                    order=2,
                    confidence=0.95,
                ),
                ContentBlock(
                    type="formula",
                    content="",
                    latex=r"\frac{a}{b},\ b \neq 0",
                    order=3,
                    confidence=0.9,
                    needs_mathpix=False,
                ),
            ],
        ),
        # Page 3: exercise + image
        PageAnalysis(
            page_num=3,
            blocks=[
                ContentBlock(
                    type="exercise",
                    content="Ví dụ 1: Tìm số hữu tỉ trong các số sau.",
                    order=1,
                    confidence=0.95,
                ),
                ContentBlock(
                    type="text",
                    content="Giải: 0,5 = 1/2 là số hữu tỉ.",
                    order=2,
                    confidence=0.90,
                ),
                ContentBlock(
                    type="image",
                    content="",
                    image_bbox=(0.1, 0.5, 0.9, 0.9),
                    caption="Hình 1. Trục số",
                    order=3,
                    confidence=0.85,
                ),
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# DB cleanup — runs before and after every test function
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def clean_test_db():
    """Drop all SGK collections to ensure test isolation.

    Skips gracefully when MongoDB is mocked (TypeError from MagicMock await).
    This allows phase-specific standalone tests to run under pytest without a
    real MongoDB connection.
    """
    from app.core.mongo import mongo_db

    _collections = ["books", "chapters", "lessons", "lesson_contents"]
    try:
        for col in _collections:
            await mongo_db[col].drop()
    except TypeError:
        pass  # Motor is mocked — skip cleanup
    yield
    try:
        for col in _collections:
            await mongo_db[col].drop()
    except TypeError:
        pass  # Motor is mocked — skip cleanup


# ---------------------------------------------------------------------------
# Reset GeminiOCRService singleton between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_gemini_singleton():
    """Reset the GeminiOCRService module-level singleton so each test starts fresh."""
    import app.services.gemini_service as _gs

    _gs._instance = None
    yield
    _gs._instance = None


# ---------------------------------------------------------------------------
# HTTP client with Gemini + ImageExtractor mocked
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client():
    """
    Async httpx client against the FastAPI ASGI app.

    Patches:
    - GeminiOCRService.analyze_page  → returns pre-defined PageAnalysis per page
    - ImageExtractor.extract_and_store → returns a fake ImageResult (no disk I/O)
    """
    import httpx
    from app.main import app
    from app.services.gemini_service import GeminiOCRService
    from app.services.image_service import ImageExtractor, ImageResult

    pages = _make_page_analyses()

    async def _fake_analyze(image_path: str, page_num: int):
        idx = min(page_num - 1, len(pages) - 1)
        return pages[idx]

    def _fake_extract(
        page_image_path,
        bbox_relative,
        book_id,
        page_num,
        fig_index,
        caption="",
    ):
        return ImageResult(
            file_path=f"storage/images/{book_id}/page_{page_num:03d}_fig_{fig_index:02d}.jpg",
            url=f"/static/images/{book_id}/page_{page_num:03d}_fig_{fig_index:02d}.jpg",
            thumbnail_url=(
                f"/static/images/{book_id}/thumbs/"
                f"page_{page_num:03d}_fig_{fig_index:02d}_thumb.jpg"
            ),
            width=300,
            height=200,
            caption=caption,
            page_num=page_num,
            fig_index=fig_index,
            file_size_kb=15.0,
        )

    with (
        patch.object(
            GeminiOCRService,
            "analyze_page",
            AsyncMock(side_effect=_fake_analyze),
        ),
        patch.object(
            ImageExtractor,
            "extract_and_store",
            MagicMock(side_effect=_fake_extract),
        ),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            yield ac
