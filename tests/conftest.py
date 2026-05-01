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
# Skip MongoDB index creation during tests (avoids Motor event-loop issues)
os.environ["SKIP_DB_INIT"] = "true"

# ---------------------------------------------------------------------------
# Claim real motor in sys.modules BEFORE any test file is collected.
# test_phase8.py / test_phase9.py conditionally stub motor only when it is
# NOT already present; importing it here prevents those stubs from running
# under pytest, while standalone execution of those files still works.
# ---------------------------------------------------------------------------
import motor           # noqa: F401, E402
import motor.motor_asyncio  # noqa: F401, E402
import fitz            # noqa: F401, E402  (PyMuPDF — prevent test_phase8/9 from mocking it)

from datetime import datetime, timezone
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
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, 780, "CHUONG I. SO HUU TI")
    c.showPage()

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 780, "Bai 1. So huu ti")
    c.setFont("Helvetica", 12)
    c.drawString(50, 750, "So huu ti la so co the viet duoi dang a/b voi b khac 0.")
    c.drawString(50, 730, "Vi du: 1/2, -3/4, 0.5")
    c.showPage()

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
    tmp_dir = tmp_path_factory.mktemp("test_pdfs")
    pdf_path = tmp_dir / "test_book.pdf"
    pdf_path.write_bytes(test_pdf_bytes)
    return str(pdf_path)


# ---------------------------------------------------------------------------
# Mock page analyses returned by GeminiOCRService.analyze_page
# ---------------------------------------------------------------------------

def _make_page_analyses():
    from app.services.gemini_service import ContentBlock, PageAnalysis

    return [
        PageAnalysis(
            page_num=1,
            blocks=[
                ContentBlock(type="chapter_title", content="CHUONG I. SO HUU TI",
                              order=1, confidence=0.99),
            ],
        ),
        PageAnalysis(
            page_num=2,
            blocks=[
                ContentBlock(type="lesson_title", content="Bai 1. So huu ti",
                              order=1, confidence=0.99),
                ContentBlock(type="text",
                              content="So huu ti la so co the viet duoi dang a/b.",
                              order=2, confidence=0.95),
                ContentBlock(type="formula", content="",
                              latex=r"\frac{a}{b},\ b \neq 0",
                              order=3, confidence=0.9, needs_mathpix=False),
            ],
        ),
        PageAnalysis(
            page_num=3,
            blocks=[
                ContentBlock(type="exercise",
                              content="Vi du 1: Tim so huu ti trong cac so sau.",
                              order=1, confidence=0.95),
                ContentBlock(type="text", content="Giai: 0,5 = 1/2 la so huu ti.",
                              order=2, confidence=0.90),
                ContentBlock(type="image", content="",
                              image_bbox=(0.1, 0.5, 0.9, 0.9),
                              caption="Hinh 1. Truc so",
                              order=3, confidence=0.85),
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# Autouse no-op: stateful mock client already provides per-test isolation
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def clean_test_db():
    yield


# ---------------------------------------------------------------------------
# Reset GeminiOCRService singleton between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_gemini_singleton():
    import app.services.gemini_service as _gs
    _gs._instance = None
    yield
    _gs._instance = None


# ---------------------------------------------------------------------------
# HTTP client backed by stateful in-memory mock repositories
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client():
    """
    Async httpx client against the FastAPI ASGI app.

    ALL MongoDB repositories are replaced by stateful in-memory dicts so
    that tests run without a real MongoDB instance and without Motor
    event-loop conflicts.  Data saved by the processing pipeline during a
    test is immediately visible to subsequent query calls in the same test.

    Additional patches:
    - GeminiOCRService.analyze_page       -> returns pre-canned PageAnalysis
    - ImageExtractor.extract_and_store    -> returns a fake ImageResult
    """
    import httpx
    from app.main import app
    from app.services.gemini_service import GeminiOCRService
    from app.services.image_service import ImageExtractor, ImageResult
    from app.schemas.book import BookCreate, BookDB
    from app.schemas.chapter import ChapterCreate, ChapterDB
    from app.schemas.lesson import LessonCreate, LessonDB
    from app.schemas.content import ContentBlockCreate, ContentBlockDB

    pages = _make_page_analyses()

    # ---- per-test in-memory stores ----------------------------------------
    books: dict = {}
    chapters: dict = {}
    lessons: dict = {}
    contents: dict = {}
    _ctr = [0]

    def _nid() -> str:
        _ctr[0] += 1
        # Return a valid 24-hex-char string compatible with bson.ObjectId()
        return f"{_ctr[0]:024x}"

    # ---- book repository mock ---------------------------------------------
    book_mock = MagicMock()
    _col = MagicMock()
    _col.update_one = AsyncMock()
    book_mock.collection = _col

    async def _b_create(book: BookCreate, file_path: str = "") -> str:
        bid = _nid()
        now = datetime.now(timezone.utc)
        books[bid] = {
            "_id": bid, **book.model_dump(),
            "status": "pending", "progress": 0, "current_phase": "",
            "total_pages": 0, "processed_pages": 0, "file_path": file_path,
            "error_message": "", "created_at": now, "updated_at": now,
            "gemini_calls": 0, "mathpix_calls": 0,
        }
        return bid

    async def _b_get(book_id: str):
        d = books.get(book_id)
        return BookDB(**d) if d else None

    async def _b_list(grade=None, status=None):
        out = []
        for d in books.values():
            if grade is not None and d["grade"] != grade:
                continue
            if status is not None and d["status"] != status:
                continue
            out.append(BookDB(**d))
        return out

    async def _b_update_status(book_id, status, progress=None, phase=None, error=""):
        if book_id not in books:
            return
        books[book_id]["status"] = status
        if progress is not None:
            books[book_id]["progress"] = progress
        if phase is not None:
            books[book_id]["current_phase"] = phase
        if error:
            books[book_id]["error_message"] = error

    async def _b_update_total(book_id, total_pages):
        if book_id in books:
            books[book_id]["total_pages"] = total_pages

    async def _b_inc_processed(book_id):
        if book_id in books:
            books[book_id]["processed_pages"] += 1

    async def _b_inc_api(book_id, gemini=0, mathpix=0):
        if book_id in books:
            books[book_id]["gemini_calls"] += gemini
            books[book_id]["mathpix_calls"] += mathpix

    async def _b_delete(book_id):
        return bool(books.pop(book_id, None))

    book_mock.create = _b_create
    book_mock.get_by_id = _b_get
    book_mock.list_all = _b_list
    book_mock.update_status = _b_update_status
    book_mock.update_total_pages = _b_update_total
    book_mock.increment_processed_pages = _b_inc_processed
    book_mock.increment_api_calls = _b_inc_api
    book_mock.delete = _b_delete

    # ---- chapter repository mock ------------------------------------------
    chapter_mock = MagicMock()

    async def _ch_create(chapter: ChapterCreate) -> str:
        cid = _nid()
        chapters[cid] = {"_id": cid, **chapter.model_dump()}
        return cid

    async def _ch_get(chapter_id: str):
        d = chapters.get(chapter_id)
        return ChapterDB(**d) if d else None

    async def _ch_list(book_id: str):
        return [
            ChapterDB(**d)
            for d in sorted(
                (v for v in chapters.values() if v["book_id"] == book_id),
                key=lambda x: x["chapter_index"],
            )
        ]

    async def _ch_del_by_book(book_id: str) -> int:
        ids = [k for k, v in chapters.items() if v["book_id"] == book_id]
        for k in ids:
            del chapters[k]
        return len(ids)

    chapter_mock.create = _ch_create
    chapter_mock.get_by_id = _ch_get
    chapter_mock.list_by_book = _ch_list
    chapter_mock.delete_by_book = _ch_del_by_book

    # ---- lesson repository mock -------------------------------------------
    lesson_mock = MagicMock()

    async def _le_create(lesson: LessonCreate) -> str:
        lid = _nid()
        lessons[lid] = {"_id": lid, **lesson.model_dump()}
        return lid

    async def _le_get(lesson_id: str):
        d = lessons.get(lesson_id)
        return LessonDB(**d) if d else None

    async def _le_list(chapter_id: str):
        return [
            LessonDB(**d)
            for d in sorted(
                (v for v in lessons.values() if v["chapter_id"] == chapter_id),
                key=lambda x: x["lesson_index"],
            )
        ]

    async def _le_del_by_chap(chapter_id: str) -> int:
        ids = [k for k, v in lessons.items() if v["chapter_id"] == chapter_id]
        for k in ids:
            del lessons[k]
        return len(ids)

    lesson_mock.create = _le_create
    lesson_mock.get_by_id = _le_get
    lesson_mock.list_by_chapter = _le_list
    lesson_mock.delete_by_chapter = _le_del_by_chap

    # ---- content repository mock ------------------------------------------
    content_mock = MagicMock()

    async def _co_bulk(blocks: list) -> list:
        ids = []
        for b in blocks:
            cid = _nid()
            contents[cid] = {"_id": cid, **b.model_dump()}
            ids.append(cid)
        return ids

    async def _co_list(lesson_id: str):
        return [
            ContentBlockDB(**d)
            for d in sorted(
                (v for v in contents.values() if v["lesson_id"] == lesson_id),
                key=lambda x: x["order"],
            )
        ]

    async def _co_search(query: str, limit: int = 20):
        q = query.lower()
        out = []
        for d in contents.values():
            if q in (d.get("content") or "").lower() or q in (d.get("latex") or "").lower():
                out.append(ContentBlockDB(**d))
                if len(out) >= limit:
                    break
        return out

    async def _co_del_by_les(lesson_id: str) -> int:
        ids = [k for k, v in contents.items() if v["lesson_id"] == lesson_id]
        for k in ids:
            del contents[k]
        return len(ids)

    content_mock.bulk_create = _co_bulk
    content_mock.list_by_lesson = _co_list
    content_mock.search_text = _co_search
    content_mock.delete_by_lesson = _co_del_by_les

    # ---- Gemini / ImageExtractor mocks ------------------------------------
    async def _fake_analyze(image_path: str, page_num: int):
        idx = min(page_num - 1, len(pages) - 1)
        return pages[idx]

    def _fake_extract(
        page_image_path, bbox_relative, book_id, page_num, fig_index, caption=""
    ):
        return ImageResult(
            file_path=f"storage/images/{book_id}/page_{page_num:03d}_fig_{fig_index:02d}.jpg",
            url=f"/static/images/{book_id}/page_{page_num:03d}_fig_{fig_index:02d}.jpg",
            thumbnail_url=(
                f"/static/images/{book_id}/thumbs/"
                f"page_{page_num:03d}_fig_{fig_index:02d}_thumb.jpg"
            ),
            width=300, height=200, caption=caption,
            page_num=page_num, fig_index=fig_index, file_size_kb=15.0,
        )

    # ---- assemble patches and yield the client ----------------------------
    with (
        patch.object(GeminiOCRService, "analyze_page", AsyncMock(side_effect=_fake_analyze)),
        patch.object(ImageExtractor, "extract_and_store", MagicMock(side_effect=_fake_extract)),
        # controllers
        patch("app.controllers.book_controller.book_repository", book_mock),
        patch("app.controllers.book_controller.chapter_repository", chapter_mock),
        patch("app.controllers.book_controller.lesson_repository", lesson_mock),
        patch("app.controllers.book_controller.content_repository", content_mock),
        patch("app.controllers.chapter_controller.chapter_repository", chapter_mock),
        patch("app.controllers.chapter_controller.lesson_repository", lesson_mock),
        patch("app.controllers.lesson_controller.lesson_repository", lesson_mock),
        patch("app.controllers.lesson_controller.content_repository", content_mock),
        patch("app.controllers.search_controller.content_repository", content_mock),
        patch("app.controllers.search_controller.lesson_repository", lesson_mock),
        patch("app.controllers.search_controller.chapter_repository", chapter_mock),
        # processing pipeline
        patch("app.services.processing_pipeline.book_repository", book_mock),
        patch("app.services.processing_pipeline.chapter_repository", chapter_mock),
        patch("app.services.processing_pipeline.lesson_repository", lesson_mock),
        patch("app.services.processing_pipeline.content_repository", content_mock),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            yield ac
