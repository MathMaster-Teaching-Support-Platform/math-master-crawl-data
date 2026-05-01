"""
Phase 6: MongoDB Pydantic Schemas + Async Repositories — Standalone Test
Run with: python tests/test_phase6.py
(No pytest required, uses mocks, no real DB calls)
"""

import sys
import os
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
# Test 1: Schema imports & Pydantic v2 compatibility
# ============================================================================

def test_schema_imports():
    print_step(1, "Schema imports & Pydantic v2 compatibility")

    from app.schemas.book import BookCreate, BookDB
    from app.schemas.chapter import ChapterCreate, ChapterDB
    from app.schemas.lesson import LessonCreate, LessonDB
    from app.schemas.content import ContentBlockCreate, ContentBlockDB

    print_ok("All schema imports successful")


# ============================================================================
# Test 2: BookCreate / BookDB validation
# ============================================================================

def test_book_schemas():
    print_step(2, "BookCreate & BookDB validation")

    from app.schemas.book import BookCreate, BookDB

    book = BookCreate(title="Toán 8", grade=8, publisher="CTST", academic_year="2024-2025")
    assert book.title == "Toán 8"
    assert book.grade == 8
    assert book.publisher == "CTST"
    print_ok("BookCreate instantiation correct")

    try:
        BookCreate(title="X", grade=0)
        print_error("Should have rejected grade=0")
    except Exception:
        print_ok("Grade ge=1 validation enforced")

    try:
        BookCreate(title="X", grade=13)
        print_error("Should have rejected grade=13")
    except Exception:
        print_ok("Grade le=12 validation enforced")

    now = datetime.now(timezone.utc)
    db_doc = {
        "_id": "abc123", "title": "Toán 8", "grade": 8, "publisher": "",
        "academic_year": "", "status": "pending", "progress": 0, "current_phase": "",
        "total_pages": 0, "processed_pages": 0, "file_path": "/data/books/abc123/file.pdf",
        "error_message": "", "created_at": now, "updated_at": now,
        "gemini_calls": 0, "mathpix_calls": 0,
    }
    book_db = BookDB(**db_doc)
    assert book_db.id == "abc123"
    assert book_db.status == "pending"
    assert book_db.gemini_calls == 0
    assert book_db.mathpix_calls == 0
    assert book_db.progress == 0
    assert book_db.current_phase == ""
    print_ok("BookDB alias '_id' -> 'id' works correctly")


# ============================================================================
# Test 3: ChapterDB / LessonDB / ContentBlockDB validation
# ============================================================================

def test_other_schemas():
    print_step(3, "ChapterDB / LessonDB / ContentBlockDB validation")

    from app.schemas.chapter import ChapterCreate, ChapterDB
    from app.schemas.lesson import LessonCreate, LessonDB
    from app.schemas.content import ContentBlockCreate, ContentBlockDB

    ch = ChapterCreate(book_id="book1", chapter_index=1, roman_index="I", title="So huu ti", page_start=5)
    assert ch.chapter_index == 1
    ch_db = ChapterDB(**{**ch.model_dump(), "_id": "ch_id_1"})
    assert ch_db.id == "ch_id_1"
    assert ch_db.roman_index == "I"
    print_ok("ChapterDB correct")

    ls = LessonCreate(chapter_id="ch1", lesson_index=1, title="Bai 1", page_start=6)
    ls_db = LessonDB(**{**ls.model_dump(), "_id": "ls_id_1"})
    assert ls_db.id == "ls_id_1"
    assert ls_db.lesson_index == 1
    print_ok("LessonDB correct")

    cb = ContentBlockCreate(lesson_id="ls1", order=1, type="formula", content="", latex=r"\frac{a}{b}", confidence=0.95, source="gemini")
    cb_db = ContentBlockDB(**{**cb.model_dump(), "_id": "cb_id_1"})
    assert cb_db.id == "cb_id_1"
    assert cb_db.latex == r"\frac{a}{b}"
    assert cb_db.source == "gemini"
    print_ok("ContentBlockDB formula correct")

    cb_img = ContentBlockCreate(lesson_id="ls1", order=2, type="image", image_url="/static/images/book1/page_001_fig_01.jpg", thumbnail_url="/static/images/book1/thumbs/page_001_fig_01_thumb.jpg", caption="Hinh 1.1", confidence=0.98, source="gemini")
    assert cb_img.image_url != ""
    assert cb_img.caption == "Hinh 1.1"
    print_ok("ContentBlockDB image block correct")


# ============================================================================
# Test 4: BookRepository mock CRUD
# ============================================================================

@pytest.mark.asyncio
async def test_book_repository():
    print_step(4, "BookRepository mock CRUD")

    from app.schemas.book import BookCreate
    from bson import ObjectId

    fake_oid = ObjectId()
    fake_id_str = str(fake_oid)
    now = datetime.now(timezone.utc)

    fake_doc = {
        "_id": fake_oid, "title": "Toan 8", "grade": 8, "publisher": "",
        "academic_year": "", "status": "pending", "progress": 0, "current_phase": "",
        "total_pages": 0, "processed_pages": 0, "file_path": "path/to/file.pdf",
        "error_message": "", "created_at": now, "updated_at": now,
        "gemini_calls": 0, "mathpix_calls": 0,
    }
    updated_doc = {**fake_doc, "status": "processing", "progress": 10, "current_phase": "ingesting"}

    mock_collection = MagicMock()
    insert_result = MagicMock()
    insert_result.inserted_id = fake_oid
    mock_collection.insert_one = AsyncMock(return_value=insert_result)
    mock_collection.find_one = AsyncMock(side_effect=[fake_doc, updated_doc, None])
    mock_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    delete_result = MagicMock()
    delete_result.deleted_count = 1
    mock_collection.delete_one = AsyncMock(return_value=delete_result)

    async def fake_cursor(docs):
        for d in docs:
            yield d

    fr = MagicMock()
    fr.sort = MagicMock(return_value=fake_cursor([fake_doc]))
    mock_collection.find = MagicMock(return_value=fr)

    from app.repositories.book_repository import BookRepository
    repo = BookRepository()
    repo.collection = mock_collection

    book_id = await repo.create(BookCreate(title="Toan 8", grade=8), "path/to/file.pdf")
    assert book_id == fake_id_str
    print_ok(f"create() returned id: {book_id}")

    book = await repo.get_by_id(book_id)
    assert book is not None
    assert book.grade == 8
    assert book.status == "pending"
    print_ok("get_by_id() returned correct BookDB")

    await repo.update_status(book_id, "processing", progress=10, phase="ingesting")
    book_updated = await repo.get_by_id(book_id)
    assert book_updated.status == "processing"
    assert book_updated.progress == 10
    assert book_updated.current_phase == "ingesting"
    print_ok("update_status() applied correctly")

    deleted = await repo.delete(book_id)
    assert deleted is True
    print_ok("delete() returned True")

    book_gone = await repo.get_by_id(book_id)
    assert book_gone is None
    print_ok("get_by_id() returns None after delete")


# ============================================================================
# Test 5: ChapterRepository mock CRUD
# ============================================================================

@pytest.mark.asyncio
async def test_chapter_repository():
    print_step(5, "ChapterRepository mock CRUD")

    from app.schemas.chapter import ChapterCreate
    from bson import ObjectId

    fake_oid = ObjectId()
    fake_id_str = str(fake_oid)
    fake_doc = {"_id": fake_oid, "book_id": "book1", "chapter_index": 1, "roman_index": "I", "title": "So huu ti", "page_start": 5}

    mock_collection = MagicMock()
    insert_result = MagicMock()
    insert_result.inserted_id = fake_oid
    mock_collection.insert_one = AsyncMock(return_value=insert_result)
    mock_collection.find_one = AsyncMock(return_value=fake_doc)

    async def fake_cursor(docs):
        for d in docs:
            yield d

    fr = MagicMock()
    fr.sort = MagicMock(return_value=fake_cursor([fake_doc]))
    mock_collection.find = MagicMock(return_value=fr)

    delete_result = MagicMock()
    delete_result.deleted_count = 1
    mock_collection.delete_many = AsyncMock(return_value=delete_result)
    mock_collection.delete_one = AsyncMock(return_value=delete_result)

    from app.repositories.chapter_repository import ChapterRepository
    repo = ChapterRepository()
    repo.collection = mock_collection

    ch_id = await repo.create(ChapterCreate(book_id="book1", chapter_index=1, roman_index="I", title="So huu ti"))
    assert ch_id == fake_id_str
    print_ok(f"ChapterRepository.create() -> {ch_id}")

    ch = await repo.get_by_id(ch_id)
    assert ch is not None
    assert ch.roman_index == "I"
    print_ok("ChapterRepository.get_by_id() correct")

    chapters = await repo.list_by_book("book1")
    assert len(chapters) == 1
    print_ok("ChapterRepository.list_by_book() returned 1 chapter")

    count = await repo.delete_by_book("book1")
    assert count == 1
    print_ok("ChapterRepository.delete_by_book() correct")


# ============================================================================
# Test 6: LessonRepository mock CRUD
# ============================================================================

@pytest.mark.asyncio
async def test_lesson_repository():
    print_step(6, "LessonRepository mock CRUD")

    from app.schemas.lesson import LessonCreate
    from bson import ObjectId

    fake_oid = ObjectId()
    fake_id_str = str(fake_oid)
    fake_doc = {"_id": fake_oid, "chapter_id": "ch1", "lesson_index": 1, "title": "Bai 1", "page_start": 6}

    mock_collection = MagicMock()
    insert_result = MagicMock()
    insert_result.inserted_id = fake_oid
    mock_collection.insert_one = AsyncMock(return_value=insert_result)
    mock_collection.find_one = AsyncMock(return_value=fake_doc)

    async def fake_cursor(docs):
        for d in docs:
            yield d

    fr = MagicMock()
    fr.sort = MagicMock(return_value=fake_cursor([fake_doc]))
    mock_collection.find = MagicMock(return_value=fr)

    delete_result = MagicMock()
    delete_result.deleted_count = 1
    mock_collection.delete_many = AsyncMock(return_value=delete_result)
    mock_collection.delete_one = AsyncMock(return_value=delete_result)

    from app.repositories.lesson_repository import LessonRepository
    repo = LessonRepository()
    repo.collection = mock_collection

    ls_id = await repo.create(LessonCreate(chapter_id="ch1", lesson_index=1, title="Bai 1"))
    assert ls_id == fake_id_str
    print_ok(f"LessonRepository.create() -> {ls_id}")

    ls = await repo.get_by_id(ls_id)
    assert ls is not None
    assert ls.lesson_index == 1
    print_ok("LessonRepository.get_by_id() correct")

    lessons = await repo.list_by_chapter("ch1")
    assert len(lessons) == 1
    print_ok("LessonRepository.list_by_chapter() returned 1 lesson")


# ============================================================================
# Test 7: ContentRepository mock CRUD + bulk_create
# ============================================================================

@pytest.mark.asyncio
async def test_content_repository():
    print_step(7, "ContentRepository mock CRUD + bulk_create")

    from app.schemas.content import ContentBlockCreate
    from bson import ObjectId

    oid1 = ObjectId()
    oid2 = ObjectId()

    blocks = [
        ContentBlockCreate(lesson_id="ls1", order=1, type="text", content="So huu ti la..."),
        ContentBlockCreate(lesson_id="ls1", order=2, type="formula", latex=r"\frac{a}{b}", source="gemini"),
    ]

    mock_collection = MagicMock()
    bulk_result = MagicMock()
    bulk_result.inserted_ids = [oid1, oid2]
    mock_collection.insert_many = AsyncMock(return_value=bulk_result)

    single_result = MagicMock()
    single_result.inserted_id = oid1
    mock_collection.insert_one = AsyncMock(return_value=single_result)

    fake_doc = {
        "_id": oid1, "lesson_id": "ls1", "order": 1, "type": "text",
        "content": "So huu ti la...", "latex": "", "image_url": "", "thumbnail_url": "",
        "caption": "", "exercise_type": "", "exercise_num": 0, "confidence": 0.0, "source": "gemini",
    }
    mock_collection.find_one = AsyncMock(return_value=fake_doc)

    async def fake_cursor(docs):
        for d in docs:
            yield d

    fr = MagicMock()
    fr.sort = MagicMock(return_value=fake_cursor([fake_doc]))
    mock_collection.find = MagicMock(return_value=fr)

    delete_result = MagicMock()
    delete_result.deleted_count = 2
    mock_collection.delete_many = AsyncMock(return_value=delete_result)

    from app.repositories.content_repository import ContentRepository
    repo = ContentRepository()
    repo.collection = mock_collection

    ids = await repo.bulk_create(blocks)
    assert len(ids) == 2
    assert ids[0] == str(oid1)
    assert ids[1] == str(oid2)
    print_ok(f"bulk_create() returned {len(ids)} ids")

    cb = await repo.get_by_id(str(oid1))
    assert cb is not None
    assert cb.type == "text"
    print_ok("get_by_id() returned correct ContentBlockDB")

    content = await repo.list_by_lesson("ls1")
    assert len(content) == 1
    print_ok("list_by_lesson() returned correct blocks")

    count = await repo.delete_by_lesson("ls1")
    assert count == 2
    print_ok("delete_by_lesson() correct")


# ============================================================================
# Test 8: increment_api_calls
# ============================================================================

@pytest.mark.asyncio
async def test_increment_api_calls():
    print_step(8, "BookRepository.increment_api_calls()")

    mock_collection = MagicMock()
    mock_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    from app.repositories.book_repository import BookRepository
    from bson import ObjectId

    repo = BookRepository()
    repo.collection = mock_collection
    fake_id = str(ObjectId())

    await repo.increment_api_calls(fake_id, gemini=1)
    assert mock_collection.update_one.call_args[0][1]["$inc"]["gemini_calls"] == 1
    print_ok("gemini_calls incremented correctly")

    await repo.increment_api_calls(fake_id, mathpix=3)
    assert mock_collection.update_one.call_args[0][1]["$inc"]["mathpix_calls"] == 3
    print_ok("mathpix_calls incremented correctly")

    call_count_before = mock_collection.update_one.call_count
    await repo.increment_api_calls(fake_id, gemini=0, mathpix=0)
    assert mock_collection.update_one.call_count == call_count_before
    print_ok("No DB call when both increments are 0")


# ============================================================================
# Main (standalone runner)
# ============================================================================

async def main():
    print_header("PHASE 6: MongoDB Pydantic Schemas + Async Repositories — Test Suite")

    test_schema_imports()
    test_book_schemas()
    test_other_schemas()
    await test_book_repository()
    await test_chapter_repository()
    await test_lesson_repository()
    await test_content_repository()
    await test_increment_api_calls()

    print_header("✅ ALL TESTS PASSED (without real DB calls)!")
    print("\n📊 SUMMARY:")
    print("  Test 1: Schema imports & Pydantic v2 compat   ✅")
    print("  Test 2: BookCreate / BookDB validation        ✅")
    print("  Test 3: Chapter / Lesson / Content schemas    ✅")
    print("  Test 4: BookRepository mock CRUD              ✅")
    print("  Test 5: ChapterRepository mock CRUD           ✅")
    print("  Test 6: LessonRepository mock CRUD            ✅")
    print("  Test 7: ContentRepository bulk + CRUD         ✅")
    print("  Test 8: increment_api_calls                   ✅")
    print("\n  Total: 8 tests — 0 failures")


if __name__ == "__main__":
    asyncio.run(main())
