# Phase 7 Testing Guide — Processing Pipeline

## Quick Start

### 1️⃣ Standalone Test Script

```bash
python tests/test_phase7.py
```

Expected output:
```
PHASE 7: Processing Pipeline — Test Suite
======================================================================

1️⃣  Import ProcessingPipeline and run_pipeline...
✅ ProcessingPipeline imported
✅ run_pipeline imported
✅ All expected methods present

2️⃣  Pipeline instantiation with mocked services...
✅ Pipeline instantiated with correct initial state

3️⃣  Mathpix fallback — Mathpix disabled (no calls made)...
✅ Mathpix disabled: block.latex unchanged, mathpix_call_count=0

... (13 tests total)

✅ ALL TESTS PASSED (without real API calls)!
```

---

## 2️⃣ Pytest Test Suite

```bash
pytest tests/test_phase7.py -v
```

Run with coverage:
```bash
pytest tests/test_phase7.py -v --cov=app.services.processing_pipeline --cov-report=term-missing
```

---

## What Phase 7 Tests Cover

| Test | Description |
|------|-------------|
| 1. Import | `ProcessingPipeline` and `run_pipeline` importable |
| 2. Instantiation | Constructor sets correct initial state |
| 3. Mathpix disabled | `_apply_mathpix_fallback` makes no updates when `success=False` |
| 4. Mathpix upgrades | Replaces `block.latex` + sets `source='mathpix'` when confidence improves |
| 5. Mathpix skip | High-confidence formulas (`>= 0.6`) are not sent to Mathpix |
| 6. Image extract | `_extract_images` produces `(page_num, order) → ImageResult` mapping |
| 7. Image skip | Blocks without `image_bbox` are skipped |
| 8. Save to DB | `_save_to_db` calls correct repository methods |
| 9. Progress sequence | Status updates 5→10→82→88→100 with correct phase names |
| 10. Full pipeline | End-to-end mock run completes with `status='done'` |
| 11. Error handling | Exception sets `status='error'` and re-raises |
| 12. run_pipeline | Standalone function delegates to `ProcessingPipeline.run()` |
| 13. source field | `ContentBlock.source` field exists and propagates to `FinalContentBlock` |

---

## 3️⃣ Manual Testing with Real Data

### Prerequisites

Set environment variables in `.env`:
```env
GEMINI_API_KEY=your_key_here
MATHPIX_ENABLED=false       # set to true only if you have Mathpix credentials
KEEP_PAGE_IMAGES=true       # keep rendered pages for inspection
STORAGE_PATH=./storage
MONGO_URL=mongodb://localhost:27017
MONGO_DB=sgk_toán_test
```

### Quick Real-Data Test

```python
import asyncio
from app.repositories.book_repository import book_repository
from app.schemas.book import BookCreate
from app.services.processing_pipeline import run_pipeline

async def test_real():
    # 1. Create a book record
    book_id = await book_repository.create(
        BookCreate(title="Toán 8 Test", grade=8, publisher="CTST"),
        file_path="data/books/test/test.pdf",
    )
    print(f"Created book: {book_id}")

    # 2. Run pipeline
    await run_pipeline(book_id, "data/books/test/test.pdf")

    # 3. Check result
    book = await book_repository.get_by_id(book_id)
    print(f"Status: {book.status}")
    print(f"Progress: {book.progress}%")
    print(f"Gemini calls: {book.gemini_calls}")

asyncio.run(test_real())
```

### Verifying DB Results

```python
import asyncio
from app.repositories.chapter_repository import chapter_repository
from app.repositories.lesson_repository import lesson_repository
from app.repositories.content_repository import content_repository

async def inspect(book_id: str):
    chapters = await chapter_repository.list_by_book(book_id)
    print(f"Chapters: {len(chapters)}")
    for ch in chapters:
        lessons = await lesson_repository.list_by_chapter(ch.id)
        print(f"  Ch {ch.chapter_index}: {ch.title} — {len(lessons)} lessons")
        for les in lessons:
            blocks = await content_repository.list_by_lesson(les.id)
            print(f"    Bài {les.lesson_index}: {les.title} — {len(blocks)} blocks")

asyncio.run(inspect("your_book_id_here"))
```

---

## 4️⃣ Pipeline Flow Diagram

```
PDF file
  │
  ▼ render_pages()          [STEP 1: ingesting, 5%]
JPEG pages (150 DPI)
  │
  ▼ GeminiOCRService.analyze_page()  [STEP 2: analyzing, 10-80%]
PageAnalysis (blocks: text/formula/image/...)
  │
  ├─▶ _apply_mathpix_fallback()      (only for formula, needs_mathpix=True or conf<0.6)
  │     MathpixService.extract_formula()
  │
  └─▶ _extract_images()              (only for image blocks with bbox)
        ImageExtractor.extract_and_store()
  │
  ▼ StructureParser.parse_book()     [STEP 3: parsing, 82%]
BookStructure (chapters → lessons → content_blocks)
  │
  ▼ _save_to_db()                    [STEP 4: saving, 88%]
MongoDB (books, chapters, lessons, lesson_contents)
  │
  ▼ status="done", progress=100      [DONE]
```

---

## 5️⃣ Checklist

- [x] `ProcessingPipeline.__init__` sets all service references
- [x] `run()` updates progress: 5% → 10% → (10-80%) per page → 82% → 88% → 100%
- [x] `_apply_mathpix_fallback` only calls Mathpix when `needs_mathpix=True` or `confidence < 0.6`
- [x] `_apply_mathpix_fallback` only updates `block.latex` if `result.confidence > block.confidence`
- [x] `block.source` set to `"mathpix"` when updated by Mathpix
- [x] `_extract_images` returns `(page_num, block_order) → ImageResult` dict
- [x] `_extract_images` skips blocks with no `image_bbox`
- [x] `_save_to_db` persists chapters → lessons → content_blocks via repositories
- [x] `raw_response` cleared after processing each page (memory safety)
- [x] Exception caught → `status="error"` set in DB → re-raised
- [x] `increment_api_calls` called with correct `gemini` and `mathpix` counts
- [x] Page images cleaned up after pipeline (unless `KEEP_PAGE_IMAGES=true`)
- [x] `run_pipeline(book_id, pdf_path)` standalone function works

---

## 6️⃣ Troubleshooting

### Gemini 429 Rate Limit
The `GeminiOCRService` has a built-in rate limiter (6 s between calls for the free tier). If you still hit 429:
```env
# In .env — slow down further if needed by extending GeminiOCRService._rate_limiter interval
```

### Memory Growing
Each `PageAnalysis.raw_response` is cleared immediately after `analyze_page()` returns. For very large PDFs, monitor memory usage and consider batching.

### MongoDB Connection
```bash
docker-compose up -d mongo
```

### Pages Not Cleaned Up
Set `KEEP_PAGE_IMAGES=false` (default) to enable cleanup. Check `storage/books/<book_id>/pages/`.

---

**Last Updated:** May 1, 2026  
**Phase:** 7 — Processing Pipeline  
**Status:** ✅ Implemented
