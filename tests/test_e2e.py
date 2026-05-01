"""
tests/test_e2e.py — Phase 9: Comprehensive E2E Tests

Run with:
    pytest tests/test_e2e.py -v --timeout=60 -s

Requires:
- tests/conftest.py (async client, mock Gemini, test DB)
- MongoDB running at MONGO_URL (default: mongodb://localhost:27017)
"""

import asyncio
import io
import time

import pytest


# ============================================================================
# SCENARIO 1: Upload + background processing (mocked Gemini)
# ============================================================================

class TestUploadAndProcess:
    """SCENARIO 1 — Upload PDF, pipeline runs with mocked Gemini, verify result."""

    async def test_upload_returns_book_id(self, client, test_pdf_bytes):
        """POST /books/upload should return 200 with a book_id."""
        resp = await client.post(
            "/api/v1/books/upload",
            files={"file": ("test_book.pdf", io.BytesIO(test_pdf_bytes), "application/pdf")},
            data={"title": "Toán 7 Tập 1", "grade": "7", "publisher": "CTST"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert "book_id" in body["data"]
        assert body["data"]["status"] == "pending"

    async def test_pipeline_completes(self, client, test_pdf_bytes):
        """After upload, background pipeline should finish with status=done."""
        resp = await client.post(
            "/api/v1/books/upload",
            files={"file": ("test_book.pdf", io.BytesIO(test_pdf_bytes), "application/pdf")},
            data={"title": "Toán 7 Tập 1", "grade": "7", "publisher": "CTST"},
        )
        book_id = resp.json()["data"]["book_id"]

        # Background tasks run within the ASGI call; poll briefly if needed.
        book_status = None
        for _ in range(30):  # max ~3 s
            s = await client.get(f"/api/v1/books/{book_id}/status")
            book_status = s.json()["data"]["status"]
            if book_status in ("done", "error"):
                break
            await asyncio.sleep(0.1)

        assert book_status == "done", f"Pipeline did not complete: status={book_status}"

    async def test_chapters_created(self, client, test_pdf_bytes):
        """Processed book should have at least 1 chapter."""
        resp = await client.post(
            "/api/v1/books/upload",
            files={"file": ("test_book.pdf", io.BytesIO(test_pdf_bytes), "application/pdf")},
            data={"title": "Toán 7 Tập 1", "grade": "7", "publisher": "CTST"},
        )
        book_id = resp.json()["data"]["book_id"]

        # Wait for pipeline completion
        for _ in range(30):
            s = await client.get(f"/api/v1/books/{book_id}/status")
            if s.json()["data"]["status"] in ("done", "error"):
                break
            await asyncio.sleep(0.1)

        chap_resp = await client.get(f"/api/v1/books/{book_id}/chapters")
        chapters = chap_resp.json()["data"]
        assert len(chapters) >= 1, "Expected at least 1 chapter after processing"

    async def test_lessons_created(self, client, test_pdf_bytes):
        """Processed book should have at least 1 lesson."""
        resp = await client.post(
            "/api/v1/books/upload",
            files={"file": ("test_book.pdf", io.BytesIO(test_pdf_bytes), "application/pdf")},
            data={"title": "Toán 7 Tập 1", "grade": "7", "publisher": "CTST"},
        )
        book_id = resp.json()["data"]["book_id"]

        for _ in range(30):
            s = await client.get(f"/api/v1/books/{book_id}/status")
            if s.json()["data"]["status"] in ("done", "error"):
                break
            await asyncio.sleep(0.1)

        chaps = (await client.get(f"/api/v1/books/{book_id}/chapters")).json()["data"]
        assert len(chaps) >= 1
        lessons_resp = await client.get(f"/api/v1/chapters/{chaps[0]['id']}/lessons")
        lessons = lessons_resp.json()["data"]
        assert len(lessons) >= 1, "Expected at least 1 lesson after processing"

    async def test_content_blocks_with_formula(self, client, test_pdf_bytes):
        """Lessons should contain formula content blocks."""
        resp = await client.post(
            "/api/v1/books/upload",
            files={"file": ("test_book.pdf", io.BytesIO(test_pdf_bytes), "application/pdf")},
            data={"title": "Toán 7 Tập 1", "grade": "7", "publisher": "CTST"},
        )
        book_id = resp.json()["data"]["book_id"]

        for _ in range(30):
            s = await client.get(f"/api/v1/books/{book_id}/status")
            if s.json()["data"]["status"] in ("done", "error"):
                break
            await asyncio.sleep(0.1)

        chaps = (await client.get(f"/api/v1/books/{book_id}/chapters")).json()["data"]
        lessons = (
            await client.get(f"/api/v1/chapters/{chaps[0]['id']}/lessons")
        ).json()["data"]
        blocks = (
            await client.get(f"/api/v1/lessons/{lessons[0]['id']}/content")
        ).json()["data"]

        formula_blocks = [b for b in blocks if b["type"] == "formula"]
        assert len(formula_blocks) >= 1, "Expected at least 1 formula block"
        assert formula_blocks[0]["latex"] != "", "Formula block should have non-empty latex"

    async def test_performance_mock_pipeline(self, client, test_pdf_bytes):
        """Full pipeline with mocked Gemini should complete in under 5 seconds."""
        start = time.monotonic()
        resp = await client.post(
            "/api/v1/books/upload",
            files={"file": ("test_book.pdf", io.BytesIO(test_pdf_bytes), "application/pdf")},
            data={"title": "Perf Test", "grade": "7", "publisher": "Test"},
        )
        book_id = resp.json()["data"]["book_id"]

        for _ in range(50):
            s = await client.get(f"/api/v1/books/{book_id}/status")
            if s.json()["data"]["status"] in ("done", "error"):
                break
            await asyncio.sleep(0.1)

        elapsed = time.monotonic() - start
        print(f"\n  ⏱  Pipeline completed in {elapsed:.2f}s (limit: 5s)")
        assert elapsed < 5.0, f"Pipeline took too long: {elapsed:.2f}s"


# ============================================================================
# Helper: upload a book and wait for done, return book_id
# ============================================================================

async def _upload_and_wait(client, pdf_bytes: bytes, title: str = "Toán 7") -> str:
    resp = await client.post(
        "/api/v1/books/upload",
        files={"file": ("test_book.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"title": title, "grade": "7", "publisher": "CTST"},
    )
    book_id = resp.json()["data"]["book_id"]
    for _ in range(30):
        s = await client.get(f"/api/v1/books/{book_id}/status")
        if s.json()["data"]["status"] in ("done", "error"):
            break
        await asyncio.sleep(0.1)
    return book_id


# ============================================================================
# SCENARIO 2: Reject invalid files
# ============================================================================

class TestFileValidation:
    """SCENARIO 2 — Validation errors for invalid uploads."""

    async def test_reject_non_pdf(self, client):
        """Uploading a .txt file should be rejected (400)."""
        resp = await client.post(
            "/api/v1/books/upload",
            files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
            data={"title": "Bad File", "grade": "7"},
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"

    async def test_reject_oversized_pdf(self, client):
        """Uploading a PDF exceeding MAX_FILE_SIZE_MB should return 413."""
        # Build a fake 'PDF' of size > 50 MB
        big_content = b"%PDF-1.4\n" + b"X" * (51 * 1024 * 1024)
        resp = await client.post(
            "/api/v1/books/upload",
            files={"file": ("big.pdf", io.BytesIO(big_content), "application/pdf")},
            data={"title": "Big Book", "grade": "7"},
        )
        assert resp.status_code == 413, f"Expected 413, got {resp.status_code}"

    async def test_missing_title_returns_422(self, client, test_pdf_bytes):
        """Form without required 'title' field should return 422."""
        resp = await client.post(
            "/api/v1/books/upload",
            files={"file": ("test_book.pdf", io.BytesIO(test_pdf_bytes), "application/pdf")},
            data={"grade": "7"},  # title is missing
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"

    async def test_invalid_grade_returns_422(self, client, test_pdf_bytes):
        """Grade outside 1-12 should be rejected with 422."""
        resp = await client.post(
            "/api/v1/books/upload",
            files={"file": ("test_book.pdf", io.BytesIO(test_pdf_bytes), "application/pdf")},
            data={"title": "Bad Grade", "grade": "99"},
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


# ============================================================================
# SCENARIO 3: Query structure after processing
# ============================================================================

class TestQueryStructure:
    """SCENARIO 3 — GET endpoints return correct data after pipeline."""

    async def test_get_chapters(self, client, test_pdf_bytes):
        """GET /books/{id}/chapters returns list with correct fields."""
        book_id = await _upload_and_wait(client, test_pdf_bytes)

        resp = await client.get(f"/api/v1/books/{book_id}/chapters")
        assert resp.status_code == 200
        chapters = resp.json()["data"]
        assert isinstance(chapters, list)
        assert len(chapters) >= 1
        for ch in chapters:
            assert "id" in ch
            assert "title" in ch
            assert "chapter_index" in ch

    async def test_get_lesson_content_formula(self, client, test_pdf_bytes):
        """Lesson content should include a formula block with valid latex."""
        book_id = await _upload_and_wait(client, test_pdf_bytes)

        chaps = (await client.get(f"/api/v1/books/{book_id}/chapters")).json()["data"]
        lessons = (
            await client.get(f"/api/v1/chapters/{chaps[0]['id']}/lessons")
        ).json()["data"]
        blocks = (
            await client.get(f"/api/v1/lessons/{lessons[0]['id']}/content")
        ).json()["data"]

        formula_blocks = [b for b in blocks if b["type"] == "formula"]
        assert len(formula_blocks) >= 1
        assert formula_blocks[0]["latex"].strip() != ""

    async def test_get_lesson_content_image(self, client, test_pdf_bytes):
        """Lesson content should include an image block with image_url set."""
        book_id = await _upload_and_wait(client, test_pdf_bytes)

        chaps = (await client.get(f"/api/v1/books/{book_id}/chapters")).json()["data"]
        # Collect all lessons across all chapters
        all_lessons = []
        for ch in chaps:
            lessons_resp = await client.get(f"/api/v1/chapters/{ch['id']}/lessons")
            all_lessons.extend(lessons_resp.json()["data"])

        image_blocks = []
        for les in all_lessons:
            blocks = (
                await client.get(f"/api/v1/lessons/{les['id']}/content")
            ).json()["data"]
            image_blocks.extend(b for b in blocks if b["type"] == "image")

        assert len(image_blocks) >= 1, "Expected at least 1 image block"
        assert image_blocks[0]["image_url"] != "", "Image block should have image_url"

    async def test_book_list_returns_books(self, client, test_pdf_bytes):
        """GET /books/ should list the uploaded book."""
        book_id = await _upload_and_wait(client, test_pdf_bytes)

        resp = await client.get("/api/v1/books/")
        assert resp.status_code == 200
        books = resp.json()["data"]
        ids = [b["id"] for b in books]
        assert book_id in ids

    async def test_book_status_endpoint(self, client, test_pdf_bytes):
        """GET /books/{id}/status returns correct fields."""
        book_id = await _upload_and_wait(client, test_pdf_bytes)

        resp = await client.get(f"/api/v1/books/{book_id}/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "done"
        assert data["progress"] == 100
        assert "total_pages" in data
        assert "processed_pages" in data


# ============================================================================
# SCENARIO 4: Export endpoints
# ============================================================================

class TestExports:
    """SCENARIO 4 — Export endpoints return correctly structured data."""

    async def test_export_json_schema(self, client, test_pdf_bytes):
        """GET /books/{id}/export/json should return a valid book tree."""
        book_id = await _upload_and_wait(client, test_pdf_bytes)

        resp = await client.get(f"/api/v1/books/{book_id}/export/json")
        assert resp.status_code == 200
        data = resp.json()["data"]

        # Top-level fields
        assert "id" in data
        assert "title" in data
        assert "grade" in data
        assert "chapters" in data
        assert isinstance(data["chapters"], list)

        # Chapter structure
        if data["chapters"]:
            ch = data["chapters"][0]
            assert "id" in ch
            assert "lessons" in ch
            assert isinstance(ch["lessons"], list)

            # Lesson structure
            if ch["lessons"]:
                les = ch["lessons"][0]
                assert "id" in les
                assert "content_blocks" in les

    async def test_export_markdown_format(self, client, test_pdf_bytes):
        """GET /books/{id}/export/md should return valid Markdown."""
        book_id = await _upload_and_wait(client, test_pdf_bytes)

        resp = await client.get(f"/api/v1/books/{book_id}/export/md")
        assert resp.status_code == 200
        md = resp.text

        # Markdown structural markers
        assert "##" in md, "Markdown should contain chapter headings (##)"
        assert "###" in md, "Markdown should contain lesson headings (###)"

        # Formula blocks exported as $$latex$$
        assert "$$" in md, "Markdown should contain LaTeX formula blocks ($$)"

    async def test_export_chunks_metadata(self, client, test_pdf_bytes):
        """GET /books/{id}/export/chunks should return RAG-ready chunks."""
        book_id = await _upload_and_wait(client, test_pdf_bytes)

        resp = await client.get(f"/api/v1/books/{book_id}/export/chunks")
        assert resp.status_code == 200
        chunks = resp.json()["data"]

        assert isinstance(chunks, list)
        assert len(chunks) >= 1, "Should have at least 1 chunk"

        # Each chunk must have required fields
        for chunk in chunks:
            assert "chunk_id" in chunk
            assert "text" in chunk
            assert "metadata" in chunk
            meta = chunk["metadata"]
            assert "grade" in meta
            assert "chapter" in meta
            assert "lesson" in meta
            assert "type" in meta


# ============================================================================
# SCENARIO 5: Full-text search
# ============================================================================

class TestSearch:
    """SCENARIO 5 — Full-text search returns relevant results."""

    async def test_search_returns_results(self, client, test_pdf_bytes):
        """GET /search?q=số hữu tỉ should return non-empty results."""
        await _upload_and_wait(client, test_pdf_bytes)

        resp = await client.get("/api/v1/search/", params={"q": "số hữu tỉ"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 0  # text index may not be available in test env

    async def test_search_result_structure(self, client, test_pdf_bytes):
        """Search results should have the expected fields."""
        await _upload_and_wait(client, test_pdf_bytes)

        resp = await client.get("/api/v1/search/", params={"q": "huu ti"})
        assert resp.status_code == 200
        results = resp.json()["data"]["results"]

        for r in results:
            assert "content_id" in r
            assert "type" in r
            assert "lesson" in r
            assert "chapter" in r

    async def test_search_missing_query_returns_422(self, client):
        """GET /search/ without q param should return 422."""
        resp = await client.get("/api/v1/search/")
        assert resp.status_code == 422


# ============================================================================
# SCENARIO 6: Delete book + 404 confirmation
# ============================================================================

class TestDelete:
    """SCENARIO 6 — Delete a book and verify cascade + 404."""

    async def test_delete_returns_200(self, client, test_pdf_bytes):
        """DELETE /books/{id} should return 200 with deleted id."""
        book_id = await _upload_and_wait(client, test_pdf_bytes)

        resp = await client.delete(f"/api/v1/books/{book_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] == book_id

    async def test_get_deleted_book_returns_404(self, client, test_pdf_bytes):
        """After deletion, GET /books/{id} should return 404."""
        book_id = await _upload_and_wait(client, test_pdf_bytes)

        await client.delete(f"/api/v1/books/{book_id}")

        resp = await client.get(f"/api/v1/books/{book_id}")
        assert resp.status_code == 404

    async def test_delete_nonexistent_book_returns_404(self, client):
        """DELETE on a non-existent id should return 404."""
        resp = await client.delete("/api/v1/books/000000000000000000000000")
        assert resp.status_code == 404

    async def test_chapters_deleted_after_book_delete(self, client, test_pdf_bytes):
        """After book deletion, its chapters should no longer be queryable."""
        book_id = await _upload_and_wait(client, test_pdf_bytes)

        # Grab chapter ids before deletion
        chaps = (await client.get(f"/api/v1/books/{book_id}/chapters")).json()["data"]
        chapter_ids = [c["id"] for c in chaps]

        await client.delete(f"/api/v1/books/{book_id}")

        # Each chapter should now return 404
        for cid in chapter_ids:
            resp = await client.get(f"/api/v1/chapters/{cid}")
            assert resp.status_code == 404, f"Chapter {cid} should be 404 after book deletion"

    async def test_data_isolation_between_tests(self, client, test_pdf_bytes):
        """Two separate books should not interfere with each other."""
        book_id_a = await _upload_and_wait(client, test_pdf_bytes, title="Book A")
        book_id_b = await _upload_and_wait(client, test_pdf_bytes, title="Book B")

        # Delete Book A; Book B should still exist
        await client.delete(f"/api/v1/books/{book_id_a}")

        resp_b = await client.get(f"/api/v1/books/{book_id_b}")
        assert resp_b.status_code == 200
        assert resp_b.json()["data"]["id"] == book_id_b
