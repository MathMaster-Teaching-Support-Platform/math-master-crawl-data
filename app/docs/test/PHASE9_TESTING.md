# Phase 9 Testing Guide — Comprehensive E2E Tests

## Quick Start

### 1️⃣ Standalone Test Script (No pytest, no real DB)

```bash
python tests/test_phase9.py
```

Expected output:
```
PHASE 9: E2E Tests — Standalone Test Suite
======================================================================
1️⃣  conftest.py fixtures are importable...
✅ conftest.py compiles without syntax errors

2️⃣  test_book.pdf fixture creation via reportlab...
✅ PDF created (2847 bytes)
...
✅ 10/10 TESTS PASSED
```

### 2️⃣ Full E2E Pytest Suite (Requires MongoDB)

```bash
# Make sure MongoDB is running first
pytest tests/test_e2e.py -v --timeout=60 -s
```

Expected output:
```
tests/test_e2e.py::TestUploadAndProcess::test_upload_returns_book_id PASSED
tests/test_e2e.py::TestUploadAndProcess::test_pipeline_completes PASSED
...
20 passed in X.XXs
```

---

## Prerequisites

### MongoDB (required for test_e2e.py only)
```bash
# Docker
docker run -d -p 27017:27017 --name mongo-test mongo:7

# Or use docker-compose
docker-compose up -d mongodb
```

### Python Dependencies
All dependencies are in `requirements.txt`. Ensure the venv is active:
```bash
# Windows
.\venv\Scripts\activate

# Install if missing
pip install -r requirements.txt
```

---

## File Structure

```
tests/
├── conftest.py              ← pytest fixtures (async client, mocks, test DB)
├── test_e2e.py              ← E2E tests (pytest only, requires MongoDB)
├── test_phase9.py           ← Standalone test (no pytest, no real DB)
└── fixtures/
    ├── create_test_pdf.py   ← Script to create test_book.pdf manually
    └── test_book.pdf        ← 3-page test PDF (auto-generated)
```

---

## Environment Setup

`conftest.py` automatically overrides these env vars for test isolation:

| Variable | Test Value | Purpose |
|---|---|---|
| `MONGO_DB` | `sgk_toan_test` | Isolated test database |
| `GEMINI_API_KEY` | `fake-test-key-for-testing` | Avoid real API calls |
| `MATHPIX_ENABLED` | `false` | Disable Mathpix in tests |

> **Note:** The test DB (`sgk_toan_test`) is cleaned before and after each test. Production data is never touched.

---

## Test Scenarios

### SCENARIO 1: Upload + Process (Mocked Gemini)

```bash
pytest tests/test_e2e.py::TestUploadAndProcess -v
```

What it tests:
- POST `/books/upload` returns `200` with `book_id`
- Background pipeline completes with `status=done`
- At least 1 chapter is created
- At least 1 lesson is created
- Formula blocks contain valid LaTeX
- Pipeline completes in under 5 seconds

Mock strategy:
- `GeminiOCRService.analyze_page` → returns predefined `PageAnalysis` per page
- `ImageExtractor.extract_and_store` → returns fake `ImageResult` (no disk I/O)

### SCENARIO 2: File Validation

```bash
pytest tests/test_e2e.py::TestFileValidation -v
```

What it tests:
- `.txt` upload → `400`
- PDF > 50 MB → `413`
- Missing `title` → `422`
- `grade` out of range (1-12) → `422`

### SCENARIO 3: Query Structure

```bash
pytest tests/test_e2e.py::TestQueryStructure -v
```

What it tests:
- `GET /books/{id}/chapters` → list with `id`, `title`, `chapter_index`
- `GET /lessons/{id}/content` → formula blocks with non-empty `latex`
- `GET /lessons/{id}/content` → image blocks with non-empty `image_url`
- `GET /books/` → lists uploaded book
- `GET /books/{id}/status` → `status=done`, `progress=100`

### SCENARIO 4: Export

```bash
pytest tests/test_e2e.py::TestExports -v
```

What it tests:
- `GET /books/{id}/export/json` → valid book tree with chapters and lessons
- `GET /books/{id}/export/md` → Markdown with `##`, `###`, `$$...$$`
- `GET /books/{id}/export/chunks` → RAG chunks with `chunk_id` and `metadata`

### SCENARIO 5: Search

```bash
pytest tests/test_e2e.py::TestSearch -v
```

What it tests:
- `GET /search/?q=số hữu tỉ` → results with `content_id`, `type`, `lesson`, `chapter`
- Missing `q` param → `422`

### SCENARIO 6: Delete + 404

```bash
pytest tests/test_e2e.py::TestDelete -v
```

What it tests:
- `DELETE /books/{id}` → `200` with `deleted` confirmation
- `GET /books/{id}` after deletion → `404`
- `DELETE /books/nonexistent` → `404`
- Chapters of deleted book return `404`
- Data isolation: deleting Book A does not affect Book B

---

## Running All Phase 9 Tests

```bash
# Standalone (no DB needed)
python tests/test_phase9.py

# Pytest E2E (requires MongoDB)
pytest tests/test_e2e.py -v --timeout=60 -s

# Full test suite (all phases + E2E)
pytest tests/ -v --timeout=60
```

---

## Regenerate Test PDF

```bash
python tests/fixtures/create_test_pdf.py
# Output: tests/fixtures/test_book.pdf  (2.8 KB, 3 pages)
```

---

## Troubleshooting

### MongoDB connection refused
```
ConnectionRefusedError: [Errno 111] Connection refused
```
Start MongoDB: `docker run -d -p 27017:27017 mongo:7`

### Event loop issues
```
RuntimeError: no running event loop
```
Make sure `pytest.ini` contains `asyncio_mode = auto`.

### GeminiOCRService raises ValueError
```
ValueError: GEMINI_API_KEY is not set in configuration.
```
`conftest.py` sets `GEMINI_API_KEY=fake-test-key-for-testing` **before** app imports. Make sure conftest.py is in the `tests/` directory.

### Test DB contamination
If tests fail with unexpected data, the DB cleanup may have failed. Run:
```bash
# Drop the test DB manually
python -c "import asyncio; from motor.motor_asyncio import AsyncIOMotorClient; asyncio.run(AsyncIOMotorClient('mongodb://localhost:27017').drop_database('sgk_toan_test'))"
```

### Background tasks not completing
If `status` never reaches `done`, check that FastAPI's BackgroundTask runs within the ASGI call. With `httpx.AsyncClient + ASGITransport`, background tasks execute synchronously.

---

## Checklist

- [ ] `python tests/test_phase9.py` → 10/10 tests pass
- [ ] `pytest tests/test_e2e.py -v` → all scenarios pass (with MongoDB)
- [ ] SCENARIO 1: upload + process (mock) pass
- [ ] SCENARIO 2: validation errors → correct status codes
- [ ] SCENARIO 3: query structure → correct response shapes
- [ ] SCENARIO 4: export JSON/MD/chunks → correct formats
- [ ] SCENARIO 5: search returns results
- [ ] SCENARIO 6: delete + 404 confirmed
- [ ] No dirty data between tests (`clean_test_db` autouse fixture)
- [ ] Performance: pipeline with mock < 5 seconds

---

**Phase:** 9 — Comprehensive E2E Tests  
**Test file:** `tests/test_e2e.py`  
**Standalone:** `tests/test_phase9.py`  
**Last Updated:** May 2026
