"""
Phase 8: Book Controller & Lesson-Page API — Standalone Test
Run with: python tests/test_phase8.py
(No pytest required, uses mocks and httpx TestClient, no real DB or API calls)

Tests the new architecture:
  1. Schema imports (lesson_page, book)
  2. LessonPageDB creation & serialization
  3. OcrTriggerRequest validation
  4. UpdateLessonPageRequest (PATCH body)
  5. Router paths exist
  6. VerifyState schema
  7. LessonPageRepository interface (mock)
  8. MappingItem page range validation
"""

import asyncio
import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _mod in [
    "google", "google.genai",
    "fitz",
    "rapidfuzz", "rapidfuzz.fuzz",
    "openai",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

if "motor" not in sys.modules or "motor.motor_asyncio" not in sys.modules:
    _motor_mock = types.ModuleType("motor.motor_asyncio")
    _motor_mock.AsyncIOMotorClient = MagicMock
    sys.modules["motor"] = MagicMock()
    sys.modules["motor.motor_asyncio"] = _motor_mock

os.environ.setdefault("GEMINI_API_KEY", "fake-test-key-for-testing")
os.environ["MATHPIX_ENABLED"] = "false"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB", "sgk_toan_test")
os.environ["SKIP_DB_INIT"] = "true"


def print_header(text):
    print(f"\n{text}")
    print("=" * 70)


def print_step(num, text):
    print(f"\n{num}. {text}...")


def print_ok(text=""):
    print(f"OK: {text}" if text else "OK")


def print_error(text):
    print(f"FAIL: {text}")
    sys.exit(1)


def test_imports():
    print_step(1, "Schema & repository imports")
    try:
        from app.schemas.lesson_page import (
            ContentBlock, LessonPageDB, MappingItem, OcrStatusResponse,
            OcrTriggerRequest, OcrTriggerResult, UpdateLessonPageRequest, VerifyState,
        )
        print_ok("lesson_page schemas imported")
        from app.repositories.lesson_page_repository import LessonPageRepository
        print_ok("LessonPageRepository imported")
        from app.controllers.book_controller import router, lesson_scoped_router
        print_ok("book_controller routers imported")
    except ImportError as e:
        print_error(f"Import failed: {e}")


def test_lesson_page_schema():
    print_step(2, "LessonPageDB creation & serialization")
    from app.schemas.lesson_page import ContentBlock, LessonPageDB
    now = datetime.now(timezone.utc)
    page = LessonPageDB(**{
        "_id": "507f1f77bcf86cd799439011",
        "bookId": "book-uuid-123",
        "lessonId": "lesson-uuid-456",
        "pageNumber": 5,
        "contentBlocks": [{"order": 1, "type": "text", "content": "So huu ti", "confidence": 0.95}],
        "ocrConfidence": 0.95,
        "ocrSource": "gemini",
        "verified": False,
    })
    assert page.book_id == "book-uuid-123"
    assert page.lesson_id == "lesson-uuid-456"
    assert page.page_number == 5
    assert len(page.content_blocks) == 1
    assert page.verified is False
    print_ok("LessonPageDB fields validated")
    d = page.model_dump(by_alias=True)
    assert "bookId" in d and "lessonId" in d and "pageNumber" in d
    print_ok("model_dump(by_alias=True) produces camelCase keys")


def test_ocr_trigger_request():
    print_step(3, "OcrTriggerRequest validation")
    from app.schemas.lesson_page import OcrTriggerRequest
    req = OcrTriggerRequest(**{
        "bookId": "book-uuid-123",
        "pdfPath": "/storage/books/book.pdf",
        "ocrPageFrom": 1,
        "ocrPageTo": 30,
        "mappings": [
            {"lessonId": "lesson-uuid-1", "pageStart": 3, "pageEnd": 8},
            {"lessonId": "lesson-uuid-2", "pageStart": 9, "pageEnd": 15},
        ],
    })
    assert req.book_id == "book-uuid-123"
    assert req.ocr_page_from == 1
    assert len(req.mappings) == 2
    assert req.mappings[0].lesson_id == "lesson-uuid-1"
    print_ok("OcrTriggerRequest validated")


def test_update_lesson_page_request():
    print_step(4, "UpdateLessonPageRequest (PATCH body)")
    from app.schemas.lesson_page import UpdateLessonPageRequest
    body = UpdateLessonPageRequest(**{
        "contentBlocks": [{"order": 1, "type": "formula", "latex": r"\frac{a}{b}", "confidence": 0.99}],
        "verified": True,
    })
    assert body.verified is True
    assert len(body.content_blocks) == 1
    print_ok("UpdateLessonPageRequest validated")
    empty = UpdateLessonPageRequest()
    assert empty.verified is None and empty.content_blocks is None
    print_ok("Empty UpdateLessonPageRequest yields None fields")


def test_router_paths():
    print_step(5, "book_controller router paths")
    from app.controllers.book_controller import lesson_scoped_router, router
    paths = {r.path for r in router.routes}
    lesson_paths = {r.path for r in lesson_scoped_router.routes}

    def has(collection, suffix):
        return any(p == suffix or p.endswith(suffix) for p in collection)

    assert has(paths, "/ocr-with-mapping"), f"Missing ocr-with-mapping in {paths}"
    assert has(paths, "/ocr-cancel"), f"Missing ocr-cancel in {paths}"
    assert has(paths, "/ocr-status"), f"Missing ocr-status in {paths}"
    assert any("lessons" in p and p.endswith("/pages") for p in paths), f"Missing pages list in {paths}"
    assert any("page_number" in p for p in paths), f"Missing single page in {paths}"
    assert has(paths, "/verification"), f"Missing verification in {paths}"
    assert any(p.endswith("/pages") for p in lesson_paths), f"Missing lesson-scoped pages in {lesson_paths}"
    print_ok("All expected router paths present")


def test_verify_state_schema():
    print_step(6, "VerifyState schema")
    from app.schemas.lesson_page import VerifyState
    state = VerifyState(**{"fullyVerified": False, "totalPages": 18, "verifiedPages": 10})
    assert state.total_pages == 18
    assert state.verified_pages == 10
    assert state.fully_verified is False
    print_ok("VerifyState validated")


def test_lesson_page_repository_interface():
    print_step(7, "LessonPageRepository interface")
    from app.repositories.lesson_page_repository import LessonPageRepository
    repo = LessonPageRepository.__new__(LessonPageRepository)
    for method in ("upsert_page", "list_by_book_and_lesson", "get_page", "update_page", "delete_by_book", "count_pages_for_book"):
        assert hasattr(repo, method), f"Missing method: {method}"
    print_ok("All LessonPageRepository methods present")


def test_mapping_item_validation():
    print_step(8, "MappingItem page range validation")
    from pydantic import ValidationError
    from app.schemas.lesson_page import MappingItem
    item = MappingItem(**{"lessonId": "l1", "pageStart": 5, "pageEnd": 10})
    assert item.page_start == 5 and item.page_end == 10
    print_ok("Valid MappingItem accepted")
    try:
        MappingItem(**{"lessonId": "l1", "pageStart": 0, "pageEnd": 5})
        print_error("Should have raised ValidationError for pageStart=0")
    except ValidationError:
        print_ok("Correctly rejects pageStart=0 (must be >=1)")


def main():
    print_header("PHASE 8: Book Controller & Lesson-Page API Tests")
    results = []

    def run(fn, name):
        try:
            fn()
            results.append((name, True))
        except SystemExit:
            results.append((name, False))
        except Exception as e:
            print(f"FAIL {name}: unexpected error — {e}")
            import traceback; traceback.print_exc()
            results.append((name, False))

    run(test_imports, "schema & repository imports")
    run(test_lesson_page_schema, "LessonPageDB schema")
    run(test_ocr_trigger_request, "OcrTriggerRequest")
    run(test_update_lesson_page_request, "UpdateLessonPageRequest")
    run(test_router_paths, "router paths")
    run(test_verify_state_schema, "VerifyState schema")
    run(test_lesson_page_repository_interface, "LessonPageRepository interface")
    run(test_mapping_item_validation, "MappingItem validation")

    print("\n" + "=" * 70)
    passed = sum(1 for _, ok in results if ok)
    print(f"Results: {passed}/{len(results)} passed")
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    if passed < len(results):
        sys.exit(1)
    print("\nAll tests passed!")


if __name__ == "__main__":
    main()
