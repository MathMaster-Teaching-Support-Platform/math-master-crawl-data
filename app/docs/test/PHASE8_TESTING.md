# Phase 8 Testing Guide — FastAPI Endpoints

## Quick Start

### 1️⃣ Standalone Test Script

```bash
python tests/test_phase8.py
```

No pytest required. No real database or API calls. All 20 tests run in seconds.

## 2️⃣ Pytest Test Suite

```bash
pytest tests/test_phase8.py -v
```

---

## What Is Tested (20 Tests)

| #   | Test                     | Endpoint                        | Assertion                               |
| --- | ------------------------ | ------------------------------- | --------------------------------------- |
| 1   | imports                  | —                               | All 4 controllers have `router`         |
| 2   | list_books               | `GET /books/`                   | Returns list with correct structure     |
| 3   | get_book_detail          | `GET /books/{id}`               | Returns stats (gemini/mathpix calls)    |
| 4   | get_book_not_found       | `GET /books/{id}`               | 404 when book missing                   |
| 5   | get_book_status          | `GET /books/{id}/status`        | Returns all polling fields              |
| 6   | upload_book              | `POST /books/upload`            | Returns book_id + status=pending        |
| 7   | upload_rejects_non_pdf   | `POST /books/upload`            | 400 for non-.pdf file                   |
| 8   | upload_rejects_oversized | `POST /books/upload`            | 413 when file > MAX_FILE_SIZE_MB        |
| 9   | list_chapters            | `GET /books/{id}/chapters`      | Chapter list with roman_index           |
| 10  | get_chapter              | `GET /chapters/{id}`            | Single chapter by ID                    |
| 11  | get_chapter_not_found    | `GET /chapters/{id}`            | 404 when chapter missing                |
| 12  | list_lessons_by_chapter  | `GET /chapters/{id}/lessons`    | Lesson list                             |
| 13  | get_lesson               | `GET /lessons/{id}`             | Single lesson by ID                     |
| 14  | get_lesson_content       | `GET /lessons/{id}/content`     | Blocks with all fields                  |
| 15  | export_json              | `GET /books/{id}/export/json`   | Full tree chapters→lessons→blocks       |
| 16  | export_markdown          | `GET /books/{id}/export/md`     | H1/H2/H3 headings + `$$latex$$`         |
| 17  | export_chunks            | `GET /books/{id}/export/chunks` | RAG chunks with metadata                |
| 18  | delete_book              | `DELETE /books/{id}`            | Cascade: contents→lessons→chapters→book |
| 19  | search                   | `GET /search/?q=`               | Results with lesson + chapter metadata  |
| 20  | search_missing_q         | `GET /search/`                  | 422 when `q` param missing              |

---

## 3️⃣ Manual Testing with Real Server

Start the server:

```bash
uvicorn app.main:app --reload --port 8001
```

### Upload a PDF

```bash
BOOK_ID=$(curl -s -X POST http://localhost:8001/api/v1/books/upload \
  -F "file=@toan8.pdf" -F "grade=8" -F "publisher=CTST" -F "title=Toán 8" \
  | python -c "import sys,json; print(json.load(sys.stdin)['data']['book_id'])")

echo "Book ID: $BOOK_ID"
```

### Poll Processing Status

```bash
while true; do
  RESP=$(curl -s http://localhost:8001/api/v1/books/$BOOK_ID/status)
  echo $RESP | python -c "import sys,json; d=json.load(sys.stdin)['data']; print(f\"[{d['current_phase']}] {d['progress']}%\")"
  STATUS=$(echo $RESP | python -c "import sys,json; print(json.load(sys.stdin)['data']['status'])")
  if [ "$STATUS" = "done" ] || [ "$STATUS" = "error" ]; then break; fi
  sleep 5
done
```

### Query Structure

```bash
# List books
curl http://localhost:8001/api/v1/books/ | python -m json.tool

# Chapters of a book
curl http://localhost:8001/api/v1/books/$BOOK_ID/chapters | python -m json.tool

# Get a chapter's lessons (replace CHAPTER_ID)
curl http://localhost:8001/api/v1/chapters/CHAPTER_ID/lessons | python -m json.tool

# Get lesson content (replace LESSON_ID)
curl http://localhost:8001/api/v1/lessons/LESSON_ID/content | python -m json.tool
```

### Export

```bash
# Full JSON tree
curl http://localhost:8001/api/v1/books/$BOOK_ID/export/json | python -m json.tool

# Markdown
curl http://localhost:8001/api/v1/books/$BOOK_ID/export/md

# RAG chunks
curl http://localhost:8001/api/v1/books/$BOOK_ID/export/chunks | python -m json.tool
```

### Search

```bash
curl "http://localhost:8001/api/v1/search/?q=số+hữu+tỉ" | python -m json.tool

# Filter by chapter
curl "http://localhost:8001/api/v1/search/?q=phân+số&chapter_id=CHAPTER_ID" | python -m json.tool
```

### Delete a Book

```bash
curl -X DELETE http://localhost:8001/api/v1/books/$BOOK_ID | python -m json.tool
```

---

## API Reference

### POST /api/v1/books/upload

**Form fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| file | file | ✅ | PDF only, max `MAX_FILE_SIZE_MB` (default 50 MB) |
| title | string | ✅ | Book title |
| grade | int | ✅ | 1–12 |
| publisher | string | — | Publisher name |
| academic_year | string | — | e.g. "2024-2025" |

**Response:**

```json
{ "success": true, "data": { "book_id": "...", "status": "pending" } }
```

### GET /api/v1/books/{book_id}/status

**Response:**

```json
{
  "success": true,
  "data": {
    "status": "processing",
    "progress": 45,
    "current_phase": "analyzing",
    "processed_pages": 9,
    "total_pages": 20
  }
}
```

### GET /api/v1/books/{book_id}/export/md

Returns `text/plain` Markdown:

```markdown
# [Lớp 8] Toán 8 — CTST

## Chương I: Số hữu tỉ

### Bài 1: Số hữu tỉ

Số hữu tỉ là số có thể viết dưới dạng...

$$\frac{a}{b}$$
```

### GET /api/v1/books/{book_id}/export/chunks

Returns JSON array for RAG ingestion:

```json
[
  {
    "chunk_id": "book8_ch1_l1_c000",
    "text": "[Lớp 8] [Chương I] [Bài 1: Số hữu tỉ] Số hữu tỉ là...",
    "metadata": {
      "grade": 8,
      "chapter": "Chương I",
      "lesson": "Bài 1: Số hữu tỉ",
      "type": "text",
      "source": "gemini"
    }
  }
]
```

---

## Checklist

- [x] POST /upload nhận file, trigger background task, trả về book_id
- [x] GET /status trả về progress real-time
- [x] GET /chapters list đúng theo book_id
- [x] GET /lessons/content trả về đủ blocks (text, formula, image, exercise)
- [x] Export JSON đúng format spec
- [x] Export Markdown format đẹp với formula LaTeX
- [x] Export chunks có metadata đầy đủ
- [x] Search tìm được text và latex
- [x] Error 404 khi book_id không tồn tại
- [x] Static files mount tại /static

---

## Troubleshooting

| Problem                       | Solution                                            |
| ----------------------------- | --------------------------------------------------- |
| Upload returns 400            | Check file is `.pdf` and content-type correct       |
| Upload returns 413            | File exceeds `MAX_FILE_SIZE_MB` in `.env`           |
| Export returns empty chapters | Processing not yet done (check `/status`)           |
| Search returns 0 results      | MongoDB text index may not be created — restart app |
| 404 on book                   | Check book_id is valid 24-char hex ObjectId         |

---

**Last Updated:** May 2, 2026  
**Phase:** 8 — FastAPI Endpoints
