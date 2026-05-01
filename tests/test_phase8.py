"""
Phase 8: FastAPI Endpoints — Standalone Test
Run with: python tests/test_phase8.py
(No pytest required, uses mocks and httpx TestClient, no real DB or API calls)
"""

import asyncio
import io
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Stub heavy optional dependencies before any app imports.
# httpx MUST NOT be stubbed here — starlette.testclient inherits from
# httpx.Response; stubbing httpx causes a metaclass conflict.
# ---------------------------------------------------------------------------
for _mod in [
    "google", "google.generativeai",
    "fitz",
    "rapidfuzz", "rapidfuzz.fuzz",
    "openai",
    "PIL", "PIL.Image",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# motor.motor_asyncio uses a custom metaclass; provide a plain-class replacement
# so app.core.mongo can import without a real MongoDB connection.
import types as _types
_motor_mock = _types.ModuleType("motor.motor_asyncio")
_motor_mock.AsyncIOMotorClient = MagicMock  # plain class — no metaclass conflict
sys.modules["motor"] = MagicMock()
sys.modules["motor.motor_asyncio"] = _motor_mock


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
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _make_book(book_id="book123"):
    from app.schemas.book import BookDB
    now = datetime.now(timezone.utc)
    return BookDB(
        **{
            "_id": book_id,
            "title": "Toán 8",
            "grade": 8,
            "publisher": "CTST",
            "academic_year": "2024-2025",
            "status": "done",
            "progress": 100,
            "current_phase": "done",
            "total_pages": 10,
            "processed_pages": 10,
            "file_path": "data/books/book123/original.pdf",
            "error_message": "",
            "created_at": now,
            "updated_at": now,
            "gemini_calls": 5,
            "mathpix_calls": 2,
        }
    )


def _make_chapter(chapter_id="chap1", book_id="book123"):
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


def _make_lesson(lesson_id="les1", chapter_id="chap1"):
    from app.schemas.lesson import LessonDB
    return LessonDB(
        **{
            "_id": lesson_id,
            "chapter_id": chapter_id,
            "lesson_index": 1,
            "title": "Bài 1: Số hữu tỉ",
            "page_start": 3,
        }
    )


def _make_content_block(block_id="blk1", lesson_id="les1", btype="text", order=0):
    from app.schemas.content import ContentBlockDB
    return ContentBlockDB(
        **{
            "_id": block_id,
            "lesson_id": lesson_id,
            "order": order,
            "type": btype,
            "content": "Số hữu tỉ là số có thể viết dưới dạng a/b.",
            "latex": "\\frac{a}{b}",
            "image_url": "",
            "thumbnail_url": "",
            "caption": "",
            "exercise_type": "",
            "exercise_num": 0,
            "confidence": 0.95,
            "source": "gemini",
        }
    )


# ---------------------------------------------------------------------------
# Build a TestClient with all DB repositories mocked
# ---------------------------------------------------------------------------

def _make_client():
    """
    Returns (client, mocks) where mocks contains all repository mocks.
    Patches are applied at the controller-import level so that the FastAPI
    app sees mocked repos when routes are called.
    """
    from fastapi.testclient import TestClient

    book_mock = MagicMock()
    chapter_mock = MagicMock()
    lesson_mock = MagicMock()
    content_mock = MagicMock()

    patches = [
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
        # Avoid actually running the background pipeline
        patch("app.controllers.book_controller.run_pipeline", AsyncMock()),
    ]

    for p in patches:
        p.start()

    from app.main import app
    client = TestClient(app, raise_server_exceptions=True)

    return client, {
        "book": book_mock,
        "chapter": chapter_mock,
        "lesson": lesson_mock,
        "content": content_mock,
    }, patches


# ============================================================================
# Test 1: Import all controllers
# ============================================================================

def test_imports():
    print_step(1, "Import all Phase 8 controllers")

    from app.controllers import book_controller, chapter_controller
    from app.controllers import lesson_controller, search_controller

    for mod_name, mod in [
        ("book_controller", book_controller),
        ("chapter_controller", chapter_controller),
        ("lesson_controller", lesson_controller),
        ("search_controller", search_controller),
    ]:
        assert hasattr(mod, "router"), f"{mod_name} missing 'router'"
    print_ok("All controllers imported with router attribute")


# ============================================================================
# Test 2: GET /api/v1/books/ — list books
# ============================================================================

def test_list_books():
    print_step(2, "GET /api/v1/books/ — list books")

    client, mocks, patches = _make_client()
    try:
        book = _make_book()
        mocks["book"].list_all = AsyncMock(return_value=[book])

        resp = client.get("/api/v1/books/")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "book123"
        assert data[0]["grade"] == 8
        assert data[0]["status"] == "done"
        print_ok("GET /books/ returns list with correct structure")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 3: GET /api/v1/books/{book_id} — book detail
# ============================================================================

def test_get_book_detail():
    print_step(3, "GET /api/v1/books/{book_id} — book detail")

    client, mocks, patches = _make_client()
    try:
        book = _make_book()
        mocks["book"].get_by_id = AsyncMock(return_value=book)

        resp = client.get("/api/v1/books/book123")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["gemini_calls"] == 5
        assert data["mathpix_calls"] == 2
        assert data["current_phase"] == "done"
        print_ok("GET /books/{id} returns detail with stats")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 4: GET /api/v1/books/{book_id} — 404 not found
# ============================================================================

def test_get_book_not_found():
    print_step(4, "GET /api/v1/books/{book_id} — 404 when book missing")

    client, mocks, patches = _make_client()
    try:
        mocks["book"].get_by_id = AsyncMock(return_value=None)

        resp = client.get("/api/v1/books/nonexistent")
        assert resp.status_code == 404
        print_ok("GET /books/nonexistent returns 404")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 5: GET /api/v1/books/{book_id}/status — polling endpoint
# ============================================================================

def test_get_book_status():
    print_step(5, "GET /api/v1/books/{book_id}/status — polling endpoint")

    client, mocks, patches = _make_client()
    try:
        book = _make_book()
        book.status = "processing"
        book.progress = 45
        book.current_phase = "analyzing"
        book.processed_pages = 5
        book.total_pages = 10
        mocks["book"].get_by_id = AsyncMock(return_value=book)

        resp = client.get("/api/v1/books/book123/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "processing"
        assert data["progress"] == 45
        assert data["current_phase"] == "analyzing"
        assert data["processed_pages"] == 5
        assert data["total_pages"] == 10
        print_ok("GET /books/{id}/status returns correct progress fields")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 6: POST /api/v1/books/upload — file upload + background task
# ============================================================================

def test_upload_book():
    print_step(6, "POST /api/v1/books/upload — PDF upload triggers pipeline")

    client, mocks, patches = _make_client()
    try:
        mocks["book"].create = AsyncMock(return_value="507f1f77bcf86cd799439011")
        # Stub collection.update_one used to set file_path
        mocks["book"].collection = MagicMock()
        mocks["book"].collection.update_one = AsyncMock()

        # Minimal valid PDF content (fake — validation is filename-based)
        fake_pdf = io.BytesIO(b"%PDF-1.4 fake content")

        with patch("app.controllers.book_controller.os.makedirs"), \
             patch("builtins.open", MagicMock()), \
             patch("app.controllers.book_controller.run_pipeline", AsyncMock()):
            resp = client.post(
                "/api/v1/books/upload",
                files={"file": ("toan8.pdf", fake_pdf, "application/pdf")},
                data={"grade": "8", "publisher": "CTST", "title": "Toán 8"},
            )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()["data"]
        assert "book_id" in data
        assert data["status"] == "pending"
        print_ok("POST /upload returns book_id with status=pending")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 7: POST /api/v1/books/upload — rejects non-PDF
# ============================================================================

def test_upload_rejects_non_pdf():
    print_step(7, "POST /api/v1/books/upload — rejects non-PDF file")

    client, mocks, patches = _make_client()
    try:
        fake_txt = io.BytesIO(b"this is not a pdf")
        resp = client.post(
            "/api/v1/books/upload",
            files={"file": ("notes.txt", fake_txt, "text/plain")},
            data={"grade": "8", "publisher": "CTST", "title": "Toán 8"},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"].lower()
        assert "pdf" in detail
        print_ok("Non-PDF file rejected with 400")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 8: POST /api/v1/books/upload — rejects oversized file
# ============================================================================

def test_upload_rejects_oversized():
    print_step(8, "POST /api/v1/books/upload — rejects file over max size")

    client, mocks, patches = _make_client()
    try:
        from app.core.config import settings
        # Create content just over the limit
        big_content = b"x" * (settings.max_file_size_mb * 1024 * 1024 + 1)
        resp = client.post(
            "/api/v1/books/upload",
            files={"file": ("big.pdf", io.BytesIO(big_content), "application/pdf")},
            data={"grade": "8", "publisher": "CTST", "title": "Toán 8"},
        )
        assert resp.status_code == 413
        print_ok(f"File over {settings.max_file_size_mb}MB rejected with 413")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 9: GET /api/v1/books/{book_id}/chapters — list chapters
# ============================================================================

def test_list_chapters():
    print_step(9, "GET /api/v1/books/{book_id}/chapters — list chapters")

    client, mocks, patches = _make_client()
    try:
        book = _make_book()
        chap = _make_chapter()
        mocks["book"].get_by_id = AsyncMock(return_value=book)
        mocks["chapter"].list_by_book = AsyncMock(return_value=[chap])

        resp = client.get("/api/v1/books/book123/chapters")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == "chap1"
        assert data[0]["roman_index"] == "I"
        assert data[0]["title"] == "Số hữu tỉ"
        print_ok("GET /books/{id}/chapters returns chapter list")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 10: GET /api/v1/chapters/{chapter_id} — single chapter
# ============================================================================

def test_get_chapter():
    print_step(10, "GET /api/v1/chapters/{chapter_id} — single chapter")

    client, mocks, patches = _make_client()
    try:
        chap = _make_chapter()
        mocks["chapter"].get_by_id = AsyncMock(return_value=chap)

        resp = client.get("/api/v1/chapters/chap1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "chap1"
        assert data["chapter_index"] == 1
        print_ok("GET /chapters/{id} returns correct chapter")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 11: GET /api/v1/chapters/{chapter_id} — 404
# ============================================================================

def test_get_chapter_not_found():
    print_step(11, "GET /api/v1/chapters/{chapter_id} — 404 when missing")

    client, mocks, patches = _make_client()
    try:
        mocks["chapter"].get_by_id = AsyncMock(return_value=None)
        resp = client.get("/api/v1/chapters/missing")
        assert resp.status_code == 404
        print_ok("GET /chapters/missing returns 404")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 12: GET /api/v1/chapters/{chapter_id}/lessons
# ============================================================================

def test_list_lessons_by_chapter():
    print_step(12, "GET /api/v1/chapters/{chapter_id}/lessons — list lessons")

    client, mocks, patches = _make_client()
    try:
        chap = _make_chapter()
        les = _make_lesson()
        mocks["chapter"].get_by_id = AsyncMock(return_value=chap)
        mocks["lesson"].list_by_chapter = AsyncMock(return_value=[les])

        resp = client.get("/api/v1/chapters/chap1/lessons")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == "les1"
        assert data[0]["title"] == "Bài 1: Số hữu tỉ"
        print_ok("GET /chapters/{id}/lessons returns lesson list")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 13: GET /api/v1/lessons/{lesson_id}
# ============================================================================

def test_get_lesson():
    print_step(13, "GET /api/v1/lessons/{lesson_id} — single lesson")

    client, mocks, patches = _make_client()
    try:
        les = _make_lesson()
        mocks["lesson"].get_by_id = AsyncMock(return_value=les)

        resp = client.get("/api/v1/lessons/les1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "les1"
        assert data["lesson_index"] == 1
        print_ok("GET /lessons/{id} returns correct lesson")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 14: GET /api/v1/lessons/{lesson_id}/content — content blocks
# ============================================================================

def test_get_lesson_content():
    print_step(14, "GET /api/v1/lessons/{lesson_id}/content — content blocks")

    client, mocks, patches = _make_client()
    try:
        les = _make_lesson()
        text_block = _make_content_block("blk1", "les1", "text", 0)
        formula_block = _make_content_block("blk2", "les1", "formula", 1)
        formula_block.content = ""
        formula_block.latex = "\\frac{1}{2}"
        mocks["lesson"].get_by_id = AsyncMock(return_value=les)
        mocks["content"].list_by_lesson = AsyncMock(return_value=[text_block, formula_block])

        resp = client.get("/api/v1/lessons/les1/content")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
        assert data[0]["type"] == "text"
        assert data[1]["type"] == "formula"
        assert data[1]["latex"] == "\\frac{1}{2}"
        assert "confidence" in data[0]
        assert "source" in data[0]
        print_ok("GET /lessons/{id}/content returns text + formula blocks")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 15: GET /api/v1/books/{book_id}/export/json
# ============================================================================

def test_export_json():
    print_step(15, "GET /api/v1/books/{book_id}/export/json — full tree JSON")

    client, mocks, patches = _make_client()
    try:
        book = _make_book()
        chap = _make_chapter()
        les = _make_lesson()
        block = _make_content_block()
        mocks["book"].get_by_id = AsyncMock(return_value=book)
        mocks["chapter"].list_by_book = AsyncMock(return_value=[chap])
        mocks["lesson"].list_by_chapter = AsyncMock(return_value=[les])
        mocks["content"].list_by_lesson = AsyncMock(return_value=[block])

        resp = client.get("/api/v1/books/book123/export/json")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title"] == "Toán 8"
        assert data["grade"] == 8
        chapters = data["chapters"]
        assert len(chapters) == 1
        assert chapters[0]["title"] == "Số hữu tỉ"
        lessons = chapters[0]["lessons"]
        assert len(lessons) == 1
        assert lessons[0]["title"] == "Bài 1: Số hữu tỉ"
        blocks = lessons[0]["content_blocks"]
        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"
        print_ok("Export JSON returns full book tree with chapters/lessons/blocks")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 16: GET /api/v1/books/{book_id}/export/md
# ============================================================================

def test_export_markdown():
    print_step(16, "GET /api/v1/books/{book_id}/export/md — Markdown export")

    client, mocks, patches = _make_client()
    try:
        book = _make_book()
        chap = _make_chapter()
        les = _make_lesson()
        text_block = _make_content_block("blk1", "les1", "text", 0)
        formula_block = _make_content_block("blk2", "les1", "formula", 1)
        formula_block.content = ""
        formula_block.latex = "\\frac{1}{2}"
        mocks["book"].get_by_id = AsyncMock(return_value=book)
        mocks["chapter"].list_by_book = AsyncMock(return_value=[chap])
        mocks["lesson"].list_by_chapter = AsyncMock(return_value=[les])
        mocks["content"].list_by_lesson = AsyncMock(return_value=[text_block, formula_block])

        resp = client.get("/api/v1/books/book123/export/md")
        assert resp.status_code == 200
        md_text = resp.text
        assert "# [Lớp 8]" in md_text
        assert "## Chương I" in md_text
        assert "### Bài 1" in md_text
        assert "$$\\frac{1}{2}$$" in md_text
        print_ok("Export Markdown contains correct headings and LaTeX formula block")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 17: GET /api/v1/books/{book_id}/export/chunks — RAG chunks
# ============================================================================

def test_export_chunks():
    print_step(17, "GET /api/v1/books/{book_id}/export/chunks — RAG chunks")

    client, mocks, patches = _make_client()
    try:
        book = _make_book()
        chap = _make_chapter()
        les = _make_lesson()
        block = _make_content_block()
        mocks["book"].get_by_id = AsyncMock(return_value=book)
        mocks["chapter"].list_by_book = AsyncMock(return_value=[chap])
        mocks["lesson"].list_by_chapter = AsyncMock(return_value=[les])
        mocks["content"].list_by_lesson = AsyncMock(return_value=[block])

        resp = client.get("/api/v1/books/book123/export/chunks")
        assert resp.status_code == 200
        chunks = resp.json()["data"]
        assert len(chunks) == 1
        chunk = chunks[0]
        assert "chunk_id" in chunk
        assert "text" in chunk
        assert "metadata" in chunk
        assert chunk["metadata"]["grade"] == 8
        assert "Chương I" in chunk["metadata"]["chapter"]
        assert "[Lớp 8]" in chunk["text"]
        print_ok("Export chunks returns RAG-ready chunks with metadata")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 18: DELETE /api/v1/books/{book_id}
# ============================================================================

def test_delete_book():
    print_step(18, "DELETE /api/v1/books/{book_id} — cascade delete")

    client, mocks, patches = _make_client()
    try:
        book = _make_book()
        chap = _make_chapter()
        les = _make_lesson()
        mocks["book"].get_by_id = AsyncMock(return_value=book)
        mocks["chapter"].list_by_book = AsyncMock(return_value=[chap])
        mocks["lesson"].list_by_chapter = AsyncMock(return_value=[les])
        mocks["content"].delete_by_lesson = AsyncMock(return_value=1)
        mocks["lesson"].delete_by_chapter = AsyncMock(return_value=1)
        mocks["chapter"].delete_by_book = AsyncMock(return_value=1)
        mocks["book"].delete = AsyncMock(return_value=True)

        with patch("app.controllers.book_controller.shutil.rmtree"):
            resp = client.delete("/api/v1/books/book123")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["deleted"] == "book123"
        # Verify cascade order
        mocks["content"].delete_by_lesson.assert_called_once_with("les1")
        mocks["lesson"].delete_by_chapter.assert_called_once_with("chap1")
        mocks["chapter"].delete_by_book.assert_called_once_with("book123")
        mocks["book"].delete.assert_called_once_with("book123")
        print_ok("DELETE /books/{id} cascades through contents→lessons→chapters→book")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 19: GET /api/v1/search/?q=keyword — text search
# ============================================================================

def test_search():
    print_step(19, "GET /api/v1/search/?q= — full-text search with metadata")

    client, mocks, patches = _make_client()
    try:
        block = _make_content_block()
        les = _make_lesson()
        chap = _make_chapter()
        mocks["content"].search_text = AsyncMock(return_value=[block])
        mocks["lesson"].get_by_id = AsyncMock(return_value=les)
        mocks["chapter"].get_by_id = AsyncMock(return_value=chap)

        resp = client.get("/api/v1/search/?q=hữu tỉ")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert "total" in body
        assert "results" in body
        assert body["total"] == 1
        result = body["results"][0]
        assert "content_id" in result
        assert "lesson" in result
        assert "chapter" in result
        assert result["lesson"]["title"] == "Bài 1: Số hữu tỉ"
        assert result["chapter"]["roman_index"] == "I"
        print_ok("GET /search/ returns results with lesson + chapter metadata")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Test 20: GET /api/v1/search/ — missing q param returns 422
# ============================================================================

def test_search_missing_q():
    print_step(20, "GET /api/v1/search/ — missing q returns 422")

    client, mocks, patches = _make_client()
    try:
        resp = client.get("/api/v1/search/")
        assert resp.status_code == 422
        print_ok("Missing q param returns 422 Unprocessable Entity")
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Main runner
# ============================================================================

async def main():
    print_header("PHASE 8: FastAPI Endpoints — Test Suite")

    tests = [
        ("imports", test_imports),
        ("list_books", test_list_books),
        ("get_book_detail", test_get_book_detail),
        ("get_book_not_found", test_get_book_not_found),
        ("get_book_status", test_get_book_status),
        ("upload_book", test_upload_book),
        ("upload_rejects_non_pdf", test_upload_rejects_non_pdf),
        ("upload_rejects_oversized", test_upload_rejects_oversized),
        ("list_chapters", test_list_chapters),
        ("get_chapter", test_get_chapter),
        ("get_chapter_not_found", test_get_chapter_not_found),
        ("list_lessons_by_chapter", test_list_lessons_by_chapter),
        ("get_lesson", test_get_lesson),
        ("get_lesson_content", test_get_lesson_content),
        ("export_json", test_export_json),
        ("export_markdown", test_export_markdown),
        ("export_chunks", test_export_chunks),
        ("delete_book", test_delete_book),
        ("search", test_search),
        ("search_missing_q", test_search_missing_q),
    ]

    passed = 0
    failed = 0

    for name, fn in tests:
        try:
            fn()
            passed += 1
        except SystemExit:
            failed += 1
        except Exception as exc:
            print_error(f"{name} raised unexpected exception: {exc}")
            failed += 1

    print_header("TEST SUMMARY")
    print(f"\n📊 RESULTS: {passed} passed / {failed} failed / {passed + failed} total")

    if failed == 0:
        print("\n✅ ALL TESTS PASSED (without real DB or API calls)!")
    else:
        print(f"\n❌ {failed} test(s) FAILED")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
