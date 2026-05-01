# Phase 6 Testing Guide — MongoDB Pydantic Schemas + Async Repositories

## Quick Start

### 1️⃣ Standalone Test Script

```bash
python tests/test_phase6.py
```

No API keys, no real MongoDB required. Uses `unittest.mock` for all DB calls.

---

## 2️⃣ Pytest Test Suite

```bash
pytest tests/test_phase6.py -v
```

---

## What is Tested

| # | Test | Description |
|---|------|-------------|
| 1 | Schema imports | All 4 schema modules importable, Pydantic v2 |
| 2 | BookCreate / BookDB | Grade bounds, `_id` alias, default fields |
| 3 | Chapter / Lesson / Content schemas | alias + model_dump round-trip |
| 4 | BookRepository CRUD | create → get_by_id → update_status → delete |
| 5 | ChapterRepository CRUD | create → get_by_id → list_by_book → delete_by_book |
| 6 | LessonRepository CRUD | create → get_by_id → list_by_chapter |
| 7 | ContentRepository CRUD | bulk_create → get_by_id → list_by_lesson → delete_by_lesson |
| 8 | increment_api_calls | gemini/mathpix counters, no-op on zero |

---

## Expected Output

```
PHASE 6: MongoDB Pydantic Schemas + Async Repositories — Test Suite
======================================================================

1️⃣  Schema imports & Pydantic v2 compatibility...
✅ All schema imports successful

2️⃣  BookCreate & BookDB validation...
✅ BookCreate instantiation correct
✅ Grade ge=1 validation enforced
✅ Grade le=12 validation enforced
✅ BookDB alias '_id' → 'id' works correctly

3️⃣  ChapterDB / LessonDB / ContentBlockDB validation...
✅ ChapterDB correct
✅ LessonDB correct
✅ ContentBlockDB formula correct
✅ ContentBlockDB image block correct

4️⃣  BookRepository mock CRUD...
✅ create() returned id: <oid>
✅ get_by_id() returned correct BookDB
✅ update_status() applied correctly
✅ delete() returned True
✅ get_by_id() returns None after delete

5️⃣  ChapterRepository mock CRUD...
✅ ChapterRepository.create() → <oid>
✅ ChapterRepository.get_by_id() correct
✅ ChapterRepository.list_by_book() returned 1 chapter
✅ ChapterRepository.delete_by_book() correct

6️⃣  LessonRepository mock CRUD...
✅ LessonRepository.create() → <oid>
✅ LessonRepository.get_by_id() correct
✅ LessonRepository.list_by_chapter() returned 1 lesson

7️⃣  ContentRepository mock CRUD + bulk_create...
✅ bulk_create() returned 2 ids
✅ get_by_id() returned correct ContentBlockDB
✅ list_by_lesson() returned correct blocks
✅ delete_by_lesson() correct

8️⃣  BookRepository.increment_api_calls()...
✅ gemini_calls incremented correctly
✅ mathpix_calls incremented correctly
✅ No DB call when both increments are 0

✅ ALL TESTS PASSED (without real DB calls)!

📊 SUMMARY:
  Test 1: Schema imports & Pydantic v2 compat   ✅
  Test 2: BookCreate / BookDB validation        ✅
  Test 3: Chapter / Lesson / Content schemas    ✅
  Test 4: BookRepository mock CRUD              ✅
  Test 5: ChapterRepository mock CRUD           ✅
  Test 6: LessonRepository mock CRUD            ✅
  Test 7: ContentRepository bulk + CRUD         ✅
  Test 8: increment_api_calls                   ✅

  Total: 8 tests — 0 failures
```

---

## Manual Testing with Real MongoDB

```bash
# Start MongoDB
docker-compose up -d mongo

# Run interactive test
python - <<'EOF'
import asyncio
from app.schemas.book import BookCreate
from app.repositories.book_repository import book_repository

async def test():
    # Create
    book_id = await book_repository.create(
        BookCreate(title="Toán 8", grade=8), "path/to/file.pdf"
    )
    print(f"Created book_id: {book_id}")

    # Get
    book = await book_repository.get_by_id(book_id)
    assert book.grade == 8
    assert book.status == "pending"
    print(f"Status: {book.status}, Progress: {book.progress}")

    # Update
    await book_repository.update_status(book_id, "processing", progress=10, phase="ingesting")
    book = await book_repository.get_by_id(book_id)
    assert book.progress == 10
    print(f"After update — Status: {book.status}, Progress: {book.progress}")

    # Increment calls
    await book_repository.increment_api_calls(book_id, gemini=5, mathpix=2)
    book = await book_repository.get_by_id(book_id)
    print(f"API calls — Gemini: {book.gemini_calls}, Mathpix: {book.mathpix_calls}")

    # Delete
    deleted = await book_repository.delete(book_id)
    print(f"Deleted: {deleted}")
    assert deleted

asyncio.run(test())
EOF
```

---

## Index Verification (with real MongoDB)

After starting the app (`uvicorn app.main:app --reload`), verify indexes are created:

```python
import asyncio
from app.core.mongo import mongo_db

async def check_indexes():
    for coll_name in ["books", "chapters", "lessons", "lesson_contents"]:
        indexes = await mongo_db[coll_name].index_information()
        print(f"\n{coll_name}:")
        for name, info in indexes.items():
            print(f"  {name}: {info['key']}")

asyncio.run(check_indexes())
```

Expected:
- `books`: indexes on `grade`, `status`
- `chapters`: unique compound `(book_id, chapter_index)`
- `lessons`: unique compound `(chapter_id, lesson_index)`
- `lesson_contents`: compound `(lesson_id, order)` + text index `(content, latex)`

---

## Checklist

- [x] Schema imports work (Pydantic v2)
- [x] `_id` alias → `id` field works with `populate_by_name=True`
- [x] BookDB has `progress`, `current_phase`, `gemini_calls`, `mathpix_calls`
- [x] All repositories have full CRUD methods
- [x] `bulk_create` for batch content insertion
- [x] `increment_api_calls` uses `$inc` (atomic)
- [x] `update_status` uses `$set` (no full document replace)
- [x] Timestamps use UTC (`timezone.utc`)
- [x] `ObjectId` never exposed raw in response (always `str(oid)`)
- [x] Indexes defined in `app/main.py` startup event

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `ValidationError: id field required` | Missing `_id` key in dict | Pass dict with `"_id"` key |
| `ValueError: extra inputs not allowed` | Pydantic v2 strict mode | Schemas use default settings (extra ignored) |
| `ServerSelectionTimeoutError` | MongoDB not running | `docker-compose up -d mongo` |
| `DuplicateKeyError` on chapter | Unique index violation | Check `(book_id, chapter_index)` not already inserted |
| `$text index not found` | Indexes not created | Restart app to trigger startup event |

---

**Last Updated:** May 1, 2026  
**Phase:** 6 — MongoDB Pydantic Schemas + Async Repositories
