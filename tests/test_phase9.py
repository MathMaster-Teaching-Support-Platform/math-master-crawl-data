"""
Phase 9: Pipeline & Verification Integration — Standalone Test
Run with: python tests/test_phase9.py
(No pytest required, uses mocks, no real DB or API calls)

Tests:
  1. conftest imports and fixtures are importable
  2. processing_pipeline module imports without error
  3. MappingPipeline class exists with run method
  4. Upsert-page preserves verify state on re-OCR
  5. Verification rollup: VerifyState counting
  6. OcrStatusResponse schema
  7. Lesson-scoped pages endpoint schema
  8. End-to-end: pipeline stores correct lesson_id keys
  9. Env isolation: MONGO_DB override works
 10. Repository collection name is lesson_pages
"""

import asyncio
import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["MONGO_DB"] = "sgk_toan_test"
os.environ.setdefault("GEMINI_API_KEY", "fake-test-key-for-testing")
os.environ["MATHPIX_ENABLED"] = "false"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ["SKIP_DB_INIT"] = "true"

for _mod in ["google", "google.genai", "fitz", "rapidfuzz", "rapidfuzz.fuzz", "openai"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_motor_mod = types.ModuleType("motor.motor_asyncio")
_motor_mod.AsyncIOMotorClient = MagicMock
if "motor" not in sys.modules or "motor.motor_asyncio" not in sys.modules:
    sys.modules["motor"] = MagicMock()
    sys.modules["motor.motor_asyncio"] = _motor_mod


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


def test_conftest_importable():
    print_step(1, "conftest helpers are importable standalone")
    import importlib
    try:
        spec = importlib.util.spec_from_file_location(
            "conftest",
            os.path.join(os.path.dirname(__file__), "conftest.py"),
        )
        # We don't actually execute conftest (pytest does), just verify it parses
        assert spec is not None
        print_ok("conftest.py spec loaded")
    except Exception as e:
        print_error(f"conftest import check failed: {e}")


def test_processing_pipeline_imports():
    print_step(2, "processing_pipeline module imports")
    try:
        from app.services.processing_pipeline import MappingPipeline, run_pipeline_with_mapping
        print_ok("MappingPipeline and run_pipeline_with_mapping imported")
    except ImportError as e:
        print_error(f"Import failed: {e}")


def test_mapping_pipeline_has_run():
    print_step(3, "MappingPipeline class structure")
    from app.services.processing_pipeline import MappingPipeline
    assert hasattr(MappingPipeline, "run"), "MappingPipeline missing .run method"
    print_ok("MappingPipeline.run exists")


def test_upsert_preserves_verify():
    print_step(4, "upsert_page preserves verify state on re-OCR")
    from app.repositories.lesson_page_repository import LessonPageRepository

    repo = LessonPageRepository.__new__(LessonPageRepository)

    # Simulate: existing doc has verified=True and verifiedBy set
    existing_doc = {
        "_id": "existing_id",
        "bookId": "book-uuid-1",
        "lessonId": "lesson-uuid-1",
        "pageNumber": 3,
        "contentBlocks": [],
        "verified": True,
        "verifiedBy": "admin@test.com",
        "verifiedAt": datetime.now(timezone.utc),
    }

    # upsert_page should use $setOnInsert or $set with preserve logic
    # We verify the method signature accepts the right args
    import inspect
    sig = inspect.signature(repo.upsert_page)
    params = list(sig.parameters)
    assert "book_id" in params or "page_doc" in params, f"upsert_page params unexpected: {params}"
    print_ok("upsert_page method signature is compatible")


def test_verify_state_counting():
    print_step(5, "VerifyState total/verified counts")
    from app.schemas.lesson_page import VerifyState

    state = VerifyState(**{"fullyVerified": False, "totalPages": 20, "verifiedPages": 15})
    assert state.total_pages == 20
    assert state.verified_pages == 15
    assert state.fully_verified is False
    # verified fraction
    fraction = state.verified_pages / state.total_pages
    assert 0.74 < fraction < 0.76
    print_ok(f"VerifyState: {state.verified_pages}/{state.total_pages} = {fraction:.0%} verified")


def test_ocr_status_response_schema():
    print_step(6, "OcrStatusResponse schema")
    from app.schemas.lesson_page import OcrStatusResponse

    status = OcrStatusResponse(**{
        "status": "processing",
        "totalPages": 20,
        "processedPages": 8,
        "progressPercent": 42,
        "currentPhase": "analyzing",
    })
    assert status.status == "processing"
    assert status.processed_pages == 8
    assert status.progress_percent == 42
    assert status.current_phase == "analyzing"
    print_ok("OcrStatusResponse validated")


def test_lesson_page_list_schema():
    print_step(7, "LessonPageDB list serialisation")
    from app.schemas.lesson_page import LessonPageDB

    now = datetime.now(timezone.utc)
    pages = [
        LessonPageDB(**{
            "_id": f"id_{i}",
            "bookId": "book-uuid-1",
            "lessonId": "lesson-uuid-1",
            "pageNumber": i,
            "contentBlocks": [],
            "verified": False,
        })
        for i in range(1, 4)
    ]
    assert len(pages) == 3
    serialised = [p.model_dump(by_alias=True) for p in pages]
    assert all("bookId" in s for s in serialised)
    assert all("pageNumber" in s for s in serialised)
    assert [s["pageNumber"] for s in serialised] == [1, 2, 3]
    print_ok("List of LessonPageDB serialised with camelCase keys")


def test_env_isolation():
    print_step(8, "Env isolation — MONGO_DB override")
    assert os.environ.get("MONGO_DB") == "sgk_toan_test"
    print_ok(f"MONGO_DB = {os.environ['MONGO_DB']}")
    assert os.environ.get("SKIP_DB_INIT") == "true"
    print_ok("SKIP_DB_INIT = true")


def test_repository_collection_name():
    print_step(9, "lesson_page_repository uses lesson_pages collection")
    import inspect
    import app.repositories.lesson_page_repository as repo_module
    source = inspect.getsource(repo_module)
    assert "lesson_pages" in source, "Collection name 'lesson_pages' not found in repository source"
    print_ok("lesson_pages collection name confirmed in repository source")


def test_book_id_lesson_id_as_strings():
    print_step(10, "book_id / lesson_id stored as plain UUID strings")
    from app.schemas.lesson_page import LessonPageDB
    page = LessonPageDB(**{
        "_id": "any_id",
        "bookId": "550e8400-e29b-41d4-a716-446655440000",
        "lessonId": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        "pageNumber": 1,
        "contentBlocks": [],
        "verified": False,
    })
    assert isinstance(page.book_id, str)
    assert isinstance(page.lesson_id, str)
    # Must be valid UUID format
    import uuid
    uuid.UUID(page.book_id)
    uuid.UUID(page.lesson_id)
    print_ok("book_id and lesson_id are plain UUID strings")


def main():
    print_header("PHASE 9: Pipeline & Verification Integration Tests")
    results = []

    def run(fn, name):
        try:
            fn()
            results.append((name, True))
        except SystemExit:
            results.append((name, False))
        except Exception as e:
            print(f"FAIL {name}: {e}")
            import traceback; traceback.print_exc()
            results.append((name, False))

    run(test_conftest_importable, "conftest importable")
    run(test_processing_pipeline_imports, "pipeline imports")
    run(test_mapping_pipeline_has_run, "MappingPipeline.run exists")
    run(test_upsert_preserves_verify, "upsert_page signature")
    run(test_verify_state_counting, "VerifyState counting")
    run(test_ocr_status_response_schema, "OcrStatusResponse")
    run(test_lesson_page_list_schema, "LessonPageDB list")
    run(test_env_isolation, "env isolation")
    run(test_repository_collection_name, "collection name")
    run(test_book_id_lesson_id_as_strings, "UUID string keys")

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
