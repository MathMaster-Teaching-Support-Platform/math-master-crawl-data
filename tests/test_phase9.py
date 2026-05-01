"""
Phase 9: Comprehensive E2E Tests — Standalone Test
Run with: python tests/test_phase9.py
(No pytest required, uses mocks, minimal dependencies)
"""

import asyncio
import io
import os
import sys
import time
import types
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Set env vars BEFORE any app imports (mirrors conftest.py behaviour)
# ---------------------------------------------------------------------------
os.environ["MONGO_DB"] = "sgk_toan_test"
os.environ.setdefault("GEMINI_API_KEY", "fake-test-key-for-testing")
os.environ["MATHPIX_ENABLED"] = "false"

# ---------------------------------------------------------------------------
# Stub heavy optional dependencies so imports work without GPU / cloud access.
# httpx must NOT be stubbed (used by TestClient internals).
# ---------------------------------------------------------------------------
for _mod in ["google", "google.generativeai", "fitz", "rapidfuzz", "rapidfuzz.fuzz", "openai"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# motor.motor_asyncio has a custom metaclass; provide a plain replacement.
_motor_mod = types.ModuleType("motor.motor_asyncio")
_motor_mod.AsyncIOMotorClient = MagicMock
sys.modules["motor"] = MagicMock()
sys.modules["motor.motor_asyncio"] = _motor_mod


# ---------------------------------------------------------------------------
# Console helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Shared mock data builders
# ---------------------------------------------------------------------------

def _make_book(book_id="aabbccddeeff001122334455"):
    from datetime import datetime, timezone

    from app.schemas.book import BookDB

    now = datetime.now(timezone.utc)
    return BookDB(
        **{
            "_id": book_id,
            "title": "Toán 7 Tập 1",
            "grade": 7,
            "publisher": "CTST",
            "academic_year": "2024-2025",
            "status": "done",
            "progress": 100,
            "current_phase": "done",
            "total_pages": 3,
            "processed_pages": 3,
            "file_path": "data/books/aabbccddeeff001122334455/original.pdf",
            "error_message": "",
            "created_at": now,
            "updated_at": now,
            "gemini_calls": 3,
            "mathpix_calls": 0,
        }
    )


def _make_chapter(chapter_id="ch1", book_id="aabbccddeeff001122334455"):
    from app.schemas.chapter import ChapterDB

    return ChapterDB(
        **{
            "_id": chapter_id,
            "book_id": book_id,
            "chapter_index": 1,
            "roman_index": "I",
            "title": "Số hữu tỉ",
            "page_start": 1,
        }
    )


def _make_lesson(lesson_id="les1", chapter_id="ch1"):
    from app.schemas.lesson import LessonDB

    return LessonDB(
        **{
            "_id": lesson_id,
            "chapter_id": chapter_id,
            "lesson_index": 1,
            "title": "Bài 1. Số hữu tỉ",
            "page_start": 2,
        }
    )


def _make_content_block(block_id="blk1", lesson_id="les1", btype="text", order=1):
    from app.schemas.content import ContentBlockDB

    extras = {}
    if btype == "formula":
        extras = {"latex": r"\frac{a}{b}", "content": ""}
    elif btype == "image":
        extras = {
            "image_url": "/static/images/aabbccddeeff001122334455/page_003_fig_01.jpg",
            "thumbnail_url": "/static/images/aabbccddeeff001122334455/thumbs/page_003_fig_01_thumb.jpg",
            "caption": "Hình 1. Trục số",
        }
    else:
        extras = {"content": "Số hữu tỉ là số có thể viết dưới dạng a/b."}

    return ContentBlockDB(
        **{
            "_id": block_id,
            "lesson_id": lesson_id,
            "order": order,
            "type": btype,
            "content": extras.get("content", ""),
            "latex": extras.get("latex", ""),
            "image_url": extras.get("image_url", ""),
            "thumbnail_url": extras.get("thumbnail_url", ""),
            "caption": extras.get("caption", ""),
            "exercise_type": "",
            "exercise_num": 0,
            "confidence": 0.95,
            "source": "gemini",
        }
    )


# ---------------------------------------------------------------------------
# Build a FastAPI TestClient with all DB calls mocked
# ---------------------------------------------------------------------------

def _make_test_client():
    from fastapi.testclient import TestClient

    book = _make_book()
    chapter = _make_chapter()
    lesson = _make_lesson()
    blocks = [
        _make_content_block("blk1", btype="text", order=1),
        _make_content_block("blk2", btype="formula", order=2),
        _make_content_block("blk3", btype="image", order=3),
    ]
    search_block = _make_content_block("blk1", btype="text", order=1)

    # --- mock run_pipeline to avoid real processing ---
    async def _noop_pipeline(book_id, pdf_path):
        pass

    # --- Build mocks per repo ---
    book_mock = MagicMock()
    book_mock.create = AsyncMock(return_value="aabbccddeeff001122334455")
    book_mock.get_by_id = AsyncMock(return_value=book)
    book_mock.list_all = AsyncMock(return_value=[book])
    book_mock.update_status = AsyncMock()
    book_mock.update_total_pages = AsyncMock()
    book_mock.increment_processed_pages = AsyncMock()
    book_mock.increment_api_calls = AsyncMock()
    book_mock.delete = AsyncMock(return_value=True)

    # Expose collection for direct update_one calls in upload handler
    col_mock = MagicMock()
    col_mock.update_one = AsyncMock()
    book_mock.collection = col_mock

    chapter_mock = MagicMock()
    chapter_mock.list_by_book = AsyncMock(return_value=[chapter])
    chapter_mock.get_by_id = AsyncMock(return_value=chapter)
    chapter_mock.delete_by_book = AsyncMock(return_value=1)

    lesson_mock = MagicMock()
    lesson_mock.list_by_chapter = AsyncMock(return_value=[lesson])
    lesson_mock.get_by_id = AsyncMock(return_value=lesson)
    lesson_mock.delete_by_chapter = AsyncMock(return_value=1)

    content_mock = MagicMock()
    content_mock.list_by_lesson = AsyncMock(return_value=blocks)
    content_mock.search_text = AsyncMock(return_value=[search_block])
    content_mock.delete_by_lesson = AsyncMock(return_value=3)

    patches = [
        patch("app.controllers.book_controller.book_repository", book_mock),
        patch("app.controllers.book_controller.chapter_repository", chapter_mock),
        patch("app.controllers.book_controller.lesson_repository", lesson_mock),
        patch("app.controllers.book_controller.content_repository", content_mock),
        patch("app.controllers.book_controller.run_pipeline", _noop_pipeline),
        patch("app.controllers.chapter_controller.chapter_repository", chapter_mock),
        patch("app.controllers.chapter_controller.lesson_repository", lesson_mock),
        patch("app.controllers.lesson_controller.lesson_repository", lesson_mock),
        patch("app.controllers.lesson_controller.content_repository", content_mock),
        patch("app.controllers.search_controller.chapter_repository", chapter_mock),
        patch("app.controllers.search_controller.lesson_repository", lesson_mock),
        patch("app.controllers.search_controller.content_repository", content_mock),
    ]

    for p in patches:
        p.start()

    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    return client, patches


# ============================================================================
# Test 1 — conftest.py + fixtures importable
# ============================================================================

def test_conftest_importable():
    print_step(1, "conftest.py fixtures are importable")

    try:
        # Confirm conftest helpers are importable by importing from the module path
        import importlib.util

        conftest_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "conftest.py"
        )
        spec = importlib.util.spec_from_file_location("conftest", conftest_path)
        mod = importlib.util.module_from_spec(spec)
        # We just check the module compiles (don't execute it — it's designed for pytest)
        with open(conftest_path, encoding="utf-8") as f:
            source = f.read()
        compile(source, conftest_path, "exec")
        print_ok("conftest.py compiles without syntax errors")
    except SyntaxError as e:
        print_error(f"conftest.py syntax error: {e}")


# ============================================================================
# Test 2 — test_book.pdf fixture can be created
# ============================================================================

def test_fixture_pdf_creation():
    print_step(2, "test_book.pdf fixture creation via reportlab")

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        print_error("reportlab not installed")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(50, 780, "CHUONG I. SO HUU TI")
    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()

    assert len(pdf_bytes) > 100, "PDF too small"
    assert pdf_bytes.startswith(b"%PDF"), "Not a valid PDF"
    print_ok(f"PDF created ({len(pdf_bytes)} bytes)")

    # Verify PyMuPDF can parse it (skip if fitz is stubbed)
    import fitz as _fitz

    if isinstance(_fitz, MagicMock):
        print_ok("fitz is mocked — skipping render verification")
        return

    try:
        doc = _fitz.open(stream=pdf_bytes, filetype="pdf")
        assert doc.page_count >= 1
        doc.close()
        print_ok(f"PyMuPDF parsed PDF ({doc.page_count} pages)")
    except Exception as e:
        print_error(f"PyMuPDF could not parse test PDF: {e}")


# ============================================================================
# Test 3 — mock client: SCENARIO 1 upload endpoint
# ============================================================================

def test_upload_endpoint_mocked():
    print_step(3, "Upload endpoint (mocked pipeline + DB)")

    client, patches = _make_test_client()
    try:
        pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n"
        response = client.post(
            "/api/v1/books/upload",
            files={"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"title": "Toán 7", "grade": "7"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        body = response.json()
        assert body["success"] is True
        assert "book_id" in body["data"]
        print_ok("Upload returned 200 with book_id")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 4 — SCENARIO 2: invalid file rejection
# ============================================================================

def test_reject_invalid_files():
    print_step(4, "Reject non-PDF and oversized files")

    client, patches = _make_test_client()
    try:
        # Non-PDF
        resp = client.post(
            "/api/v1/books/upload",
            files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
            data={"title": "Bad", "grade": "7"},
        )
        assert resp.status_code == 400, f"Expected 400 for .txt, got {resp.status_code}"
        print_ok("Non-PDF rejected with 400")

        # Oversized (>50 MB)
        big = b"%PDF-1.4\n" + b"X" * (51 * 1024 * 1024)
        resp = client.post(
            "/api/v1/books/upload",
            files={"file": ("big.pdf", io.BytesIO(big), "application/pdf")},
            data={"title": "Big", "grade": "7"},
        )
        assert resp.status_code == 413, f"Expected 413 for oversized, got {resp.status_code}"
        print_ok("Oversized PDF rejected with 413")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 5 — SCENARIO 3: query structure endpoints
# ============================================================================

def test_query_structure():
    print_step(5, "Query structure — chapters, lessons, content")

    client, patches = _make_test_client()
    try:
        # chapters
        resp = client.get("/api/v1/books/aabbccddeeff001122334455/chapters")
        assert resp.status_code == 200
        chapters = resp.json()["data"]
        assert len(chapters) >= 1
        print_ok(f"GET /chapters → {len(chapters)} chapter(s)")

        # lessons
        resp = client.get(f"/api/v1/chapters/{chapters[0]['id']}/lessons")
        assert resp.status_code == 200
        lessons = resp.json()["data"]
        assert len(lessons) >= 1
        print_ok(f"GET /lessons → {len(lessons)} lesson(s)")

        # content blocks
        resp = client.get(f"/api/v1/lessons/{lessons[0]['id']}/content")
        assert resp.status_code == 200
        blocks = resp.json()["data"]
        assert len(blocks) >= 1

        formula_blocks = [b for b in blocks if b["type"] == "formula"]
        assert len(formula_blocks) >= 1
        assert formula_blocks[0]["latex"] != ""
        print_ok(f"GET /content → {len(blocks)} block(s), formula latex present")

        image_blocks = [b for b in blocks if b["type"] == "image"]
        assert len(image_blocks) >= 1
        assert image_blocks[0]["image_url"] != ""
        print_ok("Image block has non-empty image_url")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 6 — SCENARIO 4: export endpoints
# ============================================================================

def test_export_endpoints():
    print_step(6, "Export endpoints — JSON, Markdown, chunks")

    client, patches = _make_test_client()
    try:
        # JSON export
        resp = client.get("/api/v1/books/aabbccddeeff001122334455/export/json")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "chapters" in data
        assert isinstance(data["chapters"], list)
        print_ok("JSON export has 'chapters' array")

        # Markdown export
        resp = client.get("/api/v1/books/aabbccddeeff001122334455/export/md")
        assert resp.status_code == 200
        md = resp.text
        assert "##" in md
        assert "###" in md
        assert "$$" in md  # LaTeX formula
        print_ok("Markdown export has ##, ###, and $$ markers")

        # Chunks export
        resp = client.get("/api/v1/books/aabbccddeeff001122334455/export/chunks")
        assert resp.status_code == 200
        chunks = resp.json()["data"]
        assert len(chunks) >= 1
        assert "chunk_id" in chunks[0]
        assert "metadata" in chunks[0]
        print_ok(f"Chunks export → {len(chunks)} chunk(s) with metadata")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 7 — SCENARIO 5: search endpoint
# ============================================================================

def test_search_endpoint():
    print_step(7, "Search endpoint — full-text query")

    client, patches = _make_test_client()
    try:
        resp = client.get("/api/v1/search/", params={"q": "số hữu tỉ"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total" in data
        assert "results" in data
        print_ok(f"Search returned {data['total']} result(s)")

        # Missing q param
        resp = client.get("/api/v1/search/")
        assert resp.status_code == 422
        print_ok("Missing q param → 422")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 8 — SCENARIO 6: delete + 404
# ============================================================================

def test_delete_and_404():
    print_step(8, "Delete book → confirm 200, then 404")

    from app.schemas.book import BookDB

    client, patches = _make_test_client()
    try:
        # Delete
        resp = client.delete("/api/v1/books/aabbccddeeff001122334455")
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] == "aabbccddeeff001122334455"
        print_ok("DELETE /books/{id} → 200")

        # After deletion, get_by_id returns None → 404
        from app.repositories.book_repository import book_repository as br

        # Patch the already-mocked repository to return None
        book_mock_inner = patches[0].attribute_name  # "book_repository"

        # Re-patch get_by_id to return None for 404 check
        with patch("app.controllers.book_controller.book_repository.get_by_id", AsyncMock(return_value=None)):
            resp = client.get("/api/v1/books/aabbccddeeff001122334455")
            assert resp.status_code == 404
            print_ok("GET deleted book → 404")

        # Non-existent delete
        with patch("app.controllers.book_controller.book_repository.get_by_id", AsyncMock(return_value=None)):
            resp = client.delete("/api/v1/books/000000000000000000000000")
            assert resp.status_code == 404
            print_ok("DELETE non-existent book → 404")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 9 — conftest.py uses correct test DB name
# ============================================================================

def test_env_isolation():
    print_step(9, "Environment isolation — MONGO_DB is sgk_toan_test")

    assert os.environ.get("MONGO_DB") == "sgk_toan_test"
    assert os.environ.get("MATHPIX_ENABLED", "false").lower() == "false"
    print_ok("MONGO_DB=sgk_toan_test")
    print_ok("MATHPIX_ENABLED=false")


# ============================================================================
# Test 10 — GeminiOCRService mock intercepts analyze_page
# ============================================================================

def test_gemini_mock_intercepts():
    print_step(10, "GeminiOCRService.analyze_page mock intercepts correctly")

    from app.services.gemini_service import ContentBlock, GeminiOCRService, PageAnalysis

    fake_analysis = PageAnalysis(
        page_num=1,
        blocks=[ContentBlock(type="chapter_title", content="CHƯƠNG I", order=1, confidence=0.99)],
    )

    async def _check():
        with patch.object(
            GeminiOCRService,
            "analyze_page",
            AsyncMock(return_value=fake_analysis),
        ) as mock_method:
            # Reset singleton so __init__ runs fresh
            import app.services.gemini_service as _gs
            _gs._instance = None

            # Pretend a pipeline calls analyze_page
            service = GeminiOCRService()
            result = await service.analyze_page("fake_path.jpg", 1)
            assert result.page_num == 1
            assert result.blocks[0].type == "chapter_title"
            mock_method.assert_called_once()
            print_ok("analyze_page mock intercepted, returned correct PageAnalysis")

    # Run in a new thread's event loop to avoid "cannot be called from running event loop"
    import threading
    result_holder = [None]
    exc_holder = [None]

    def _thread_run():
        try:
            asyncio.run(_check())
        except Exception as e:
            exc_holder[0] = e

    t = threading.Thread(target=_thread_run)
    t.start()
    t.join(timeout=10)
    if exc_holder[0]:
        raise exc_holder[0]


# ============================================================================
# Main
# ============================================================================

async def main():
    print_header("PHASE 9: E2E Tests — Standalone Test Suite")

    results = []

    def run(fn, name):
        try:
            fn()
            results.append((name, True))
        except SystemExit:
            results.append((name, False))
        except Exception as e:
            print(f"❌ {name}: {e}")
            results.append((name, False))

    run(test_conftest_importable, "conftest importable")
    run(test_fixture_pdf_creation, "fixture PDF creation")
    run(test_upload_endpoint_mocked, "upload endpoint (mocked)")
    run(test_reject_invalid_files, "reject invalid files")
    run(test_query_structure, "query structure")
    run(test_export_endpoints, "export endpoints")
    run(test_search_endpoint, "search endpoint")
    run(test_delete_and_404, "delete + 404")
    run(test_env_isolation, "env isolation")
    run(test_gemini_mock_intercepts, "Gemini mock intercepts")

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    print_header(f"✅ {passed}/{total} TESTS PASSED")
    print("\n📊 SUMMARY:")
    for name, ok in results:
        icon = "✅" if ok else "❌"
        print(f"  {icon}  {name}")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
