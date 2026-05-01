# Phase 10 Testing Guide — Final Validation

## Overview

Phase 10 validates that the entire project is production-ready:

- README.md is complete and informative
- `docker-compose.yml` is valid and has all required services
- `Dockerfile` is correct for Python 3.11
- `scripts/setup.sh` guides new contributors through setup
- `.env.example` covers all required config keys
- `requirements.txt` has all packages
- `app/main.py` registers all controllers and static files
- All previous phase test files exist (phase 1–9)

---

## Quick Start

### 1️⃣ Standalone Test Script (No pytest)

```bash
python tests/test_phase10.py
```

**Expected output:**

```
PHASE 10: Final Validation — Project Completeness
======================================================================

1️⃣  README.md completeness check...
✅ README has: Project description / title
✅ README has: Stack table
✅ README has: Prerequisites section
✅ README has: Gemini API key instructions
✅ README has: Mathpix key instructions
✅ README has: Installation steps
✅ README has: Docker usage
✅ README has: API endpoints table
✅ README has: Example curl commands
✅ README has: Testing section
✅ README has: Accuracy notes
✅ README has: Cost estimation / free tier info
✅ README.md size: 9.3 KB

2️⃣  docker-compose.yml structure validation...
✅ docker-compose.yml has: mongo service
✅ docker-compose.yml has: app service
✅ docker-compose.yml has: MongoDB 7 image
✅ docker-compose.yml has: Dockerfile build instruction
...

✅ 8/8 TESTS PASSED

📊 SUMMARY:
  ✅ README.md completeness
  ✅ docker-compose.yml structure
  ✅ Dockerfile directives
  ✅ setup.sh commands
  ✅ .env.example keys
  ✅ requirements.txt packages
  ✅ app/main.py config
  ✅ all phase test files exist

🎉 PROJECT COMPLETE — all phase-10 checks passed!
```

---

## 2️⃣ Pytest Test Suite

```bash
# Run phase 10 only
pytest tests/test_phase10.py -v

# Run all phases
pytest tests/ -v --timeout=60
```

---

## 3️⃣ Manual Validation Checklist

### Docker Setup

```bash
# Build and start
cp .env.example .env
# Fill in GEMINI_API_KEY in .env

docker-compose up -d
docker-compose ps           # both mongo and app should be Up
curl http://localhost:8000/health  # expect {"status":"ok"}
```

### Setup Script

```bash
# Linux/macOS
bash scripts/setup.sh

# Verify output:
# ✅ Created .env from .env.example
# ✅ Created directories: storage/images, data/books
# ✅ Virtual environment created at ./venv
# ✅ Python dependencies installed
# ✅ MongoDB started (port 27017)
```

### Full pytest Run

```bash
pytest tests/ -v --timeout=60
# Expected: 0 failures
```

### Upload Real PDF (10-page test)

```bash
# Start server
python run.py &

# Upload
BOOK_ID=$(curl -s -X POST http://localhost:8000/api/v1/books/upload \
  -F "file=@tests/fixtures/test_book.pdf" \
  -F "grade=7" \
  -F "publisher=Test" \
  -F "title=Test Book" \
  | python -c "import sys,json; print(json.load(sys.stdin)['data']['book_id'])")

echo "Book ID: $BOOK_ID"

# Poll until done
while true; do
  RESP=$(curl -s "http://localhost:8000/api/v1/books/$BOOK_ID/status")
  STATUS=$(echo "$RESP" | python -c "import sys,json; print(json.load(sys.stdin)['data']['status'])")
  PROG=$(echo "$RESP" | python -c "import sys,json; print(json.load(sys.stdin)['data']['progress'])")
  echo "[$STATUS] $PROG%"
  if [ "$STATUS" = "done" ] || [ "$STATUS" = "error" ]; then break; fi
  sleep 5
done
```

### Export Validation

```bash
# Export JSON
curl "http://localhost:8000/api/v1/books/$BOOK_ID/export/json" \
  | python -m json.tool > output.json
# Check: has "chapters" array, each chapter has "lessons"

# Export Markdown
curl "http://localhost:8000/api/v1/books/$BOOK_ID/export/md" > output.md
# Open output.md — should have # headers and $$ formula blocks

# Export RAG chunks
curl "http://localhost:8000/api/v1/books/$BOOK_ID/export/chunks" \
  | python -m json.tool > chunks.json
# Check: each chunk has chunk_id, text, metadata
```

### Search Test

```bash
curl "http://localhost:8000/api/v1/search?q=chương" | python -m json.tool
# Expect: results array with items
```

### Static Images

```bash
# After upload + processing with a real PDF containing images:
curl -I "http://localhost:8000/static/images/$BOOK_ID/page_001_fig_01.jpg"
# Expect: HTTP/1.1 200 OK (if image exists)
```

---

## 4️⃣ Final Checklist

| Check             | Command                         | Expected                   |
| ----------------- | ------------------------------- | -------------------------- |
| README complete   | Open README.md                  | All sections present       |
| Docker compose    | `docker-compose up -d`          | Both services Up           |
| pytest all phases | `pytest tests/ -v`              | 0 failures                 |
| Health check      | `curl /health`                  | `{"status":"ok"}`          |
| Upload PDF        | `POST /books/upload`            | Returns `book_id`          |
| Export JSON       | `GET /books/{id}/export/json`   | Valid JSON tree            |
| Export Markdown   | `GET /books/{id}/export/md`     | Has `##`, `$...$`          |
| Export chunks     | `GET /books/{id}/export/chunks` | Has `chunk_id`, `metadata` |
| Search            | `GET /search?q=...`             | Returns results            |
| Static images     | `GET /static/images/...`        | 200 OK                     |

---

## Troubleshooting

### Docker build fails

```bash
# Check Dockerfile syntax
docker build --no-cache -t sgk-app .
# Look for missing apt packages (PyMuPDF needs libmupdf)
```

### pytest fails on test_phase10.py

```bash
# Most likely a missing file — check output for which file
# Common fix: ensure all test_phase1..9.py and PHASE1..9_TESTING.md exist
ls tests/test_phase*.py
ls app/docs/test/PHASE*_TESTING.md
```

### `.env.example` check fails

```bash
# Ensure .env.example has all required keys
cat .env.example | grep -E "GEMINI_API_KEY|MONGO_URL|STORAGE_PATH"
```

---

**Last Updated:** May 2, 2026  
**Phase:** 10 / 10  
**Status:** Final
