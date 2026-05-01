# SGK Toán PDF → API

Số hoá Sách Giáo Khoa Toán Việt Nam từ PDF sang REST API có thể truy vấn. Hệ thống dùng **Gemini Flash Vision** làm OCR chính (nhận diện text + công thức + hình vẽ), **Mathpix** làm fallback cho công thức phức tạp, lưu kết quả vào MongoDB và phục vụ qua FastAPI.

## Tính năng nổi bật

- Upload PDF SGK → xử lý tự động (PyMuPDF → Gemini OCR → MongoDB)
- Nhận diện layout thông minh: Chương / Bài / Ví dụ / Bài tập / Định nghĩa / Ghi nhớ
- Công thức LaTeX chính xác (~85–92% với Gemini, ~95%+ với Mathpix fallback)
- Trích xuất và lưu hình vẽ hình học từ trang SGK
- Export dữ liệu ra JSON / Markdown / RAG chunks
- Full-text search nội dung SGK
- Polling status xử lý real-time (tiến độ %, phase hiện tại)
- Chatbot tư vấn tuyển sinh đại học tích hợp sẵn

---

## Stack kỹ thuật

| Layer            | Công nghệ           | Vai trò                                |
| ---------------- | ------------------- | -------------------------------------- |
| PDF Ingestion    | PyMuPDF             | Render trang → JPEG 150 DPI            |
| OCR chính        | Gemini Flash Vision | Text + layout + công thức + hình       |
| Formula fallback | Mathpix v3/text     | Khi Gemini fail với công thức phức tạp |
| Image storage    | Pillow + local JPEG | Crop bbox, serve qua FastAPI static    |
| Structure        | Rule Engine (regex) | Detect Chương/Bài từ Gemini labels     |
| Database         | MongoDB 7 + Motor   | Async, text index cho search           |
| API              | FastAPI             | REST endpoints + BackgroundTasks       |
| Chat AI          | OpenAI / Gemini     | Chatbot tư vấn tuyển sinh              |

---

## Yêu cầu

| Thành phần       | Phiên bản / Ghi chú                                                                                |
| ---------------- | -------------------------------------------------------------------------------------------------- |
| Python           | >= 3.11                                                                                            |
| MongoDB          | >= 7.0 (local hoặc Atlas)                                                                          |
| Gemini API key   | **Bắt buộc** cho OCR — lấy miễn phí tại [Google AI Studio](https://aistudio.google.com/app/apikey) |
| Mathpix key      | _Optional_ — chỉ cần nếu muốn fallback công thức độ chính xác cao                                  |
| Docker + Compose | _Optional_ — chạy toàn bộ stack với 1 lệnh                                                         |

---

## Cách lấy API Keys

### Gemini API Key (miễn phí, bắt buộc cho OCR)

1. Truy cập [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Đăng nhập Google account
3. Click **"Create API Key"** → chọn project
4. Copy key → paste vào `.env` dưới `GEMINI_API_KEY=`

> Free tier: 250 requests/ngày, 10 RPM — đủ để xử lý ~250 trang SGK mỗi ngày.

### Mathpix API Key (optional, ~95%+ độ chính xác công thức)

1. Đăng ký tại [Mathpix](https://mathpix.com/)
2. Vào Dashboard → **API Keys** → tạo key mới
3. Copy `app_id` và `app_key` vào `.env`
4. Đặt `MATHPIX_ENABLED=true`

> Mathpix cung cấp $20 credit miễn phí khi đăng ký (~10.000 ảnh).

---

## Cài đặt nhanh (Script tự động)

```bash
# Clone repo
git clone <repo-url>
cd math-master-crawl-data

# Chạy setup script (Linux/macOS)
bash scripts/setup.sh

# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Chỉnh sửa .env: thêm GEMINI_API_KEY=...
```

---

## Cài đặt thủ công

```bash
# 1. Clone repo
git clone <repo-url>
cd math-master-crawl-data

# 2. Tạo virtual environment
python -m venv venv

# Windows
.\venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 3. Cài dependencies
pip install -r requirements.txt

# 4. Tạo file cấu hình
cp .env.example .env
# Mở .env, điền GEMINI_API_KEY (bắt buộc)

# 5. Tạo thư mục cần thiết
mkdir -p storage/images data/books

# 6. Chạy server
python run.py
```

---

## Cài đặt với Docker

```bash
# 1. Clone + copy .env
cp .env.example .env
# Điền GEMINI_API_KEY trong .env

# 2. Chạy toàn bộ stack (MongoDB + App)
docker-compose up -d

# 3. Kiểm tra logs
docker-compose logs -f app

# Server: http://localhost:8000
# Swagger UI: http://localhost:8000/docs
```

---

## Cấu hình

Tạo file `.env` ở thư mục gốc (copy từ `.env.example` nếu có):

```env
# --- LLM ---
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# --- MongoDB ---
MONGO_URL=mongodb://localhost:27017
MONGO_DB=sgk_toan

# --- App ---
PORT=8001
DEBUG=False
API_PREFIX=/api/v1
CHAT_HISTORY_LIMIT=30
SECRET_KEY=your-secret-key
```

### Mô tả biến môi trường

| Biến                 | Mặc định                    | Mô tả                                      |
| -------------------- | --------------------------- | ------------------------------------------ |
| `OPENAI_API_KEY`     | _(bắt buộc)_                | API key của nhà cung cấp LLM               |
| `OPENAI_MODEL`       | `gpt-3.5-turbo`             | Tên model LLM (xem bên dưới)               |
| `MONGO_URL`          | `mongodb://localhost:27017` | Connection string MongoDB                  |
| `MONGO_DB`           | `sgk_toan`                  | Tên database                               |
| `STORAGE_PATH`       | `./storage`                 | Thư mục lưu ảnh trích xuất                 |
| `GEMINI_API_KEY`     | _(optional)_                | Google Gemini API key (OCR chính)          |
| `GEMINI_MODEL`       | `gemini-2.0-flash`          | Tên model Gemini                           |
| `MATHPIX_APP_ID`     | _(optional)_                | Mathpix App ID (formula fallback)          |
| `MATHPIX_APP_KEY`    | _(optional)_                | Mathpix App Key                            |
| `MATHPIX_ENABLED`    | `false`                     | Bật Mathpix fallback                       |
| `MAX_FILE_SIZE_MB`   | `50`                        | Giới hạn kích thước PDF upload             |
| `PORT`               | `8001`                      | Cổng server                                |
| `DEBUG`              | `False`                     | Bật/tắt chế độ debug & auto-reload         |
| `API_PREFIX`         | `/api/v1`                   | Tiền tố cho tất cả các API route           |
| `CHAT_HISTORY_LIMIT` | `30`                        | Số lượt hội thoại tối đa giữ trong context |
| `SECRET_KEY`         | `your-secret-key`           | Secret key cho ứng dụng                    |

---

## Chạy chatbot

```bash
# Cách 1 – dùng run.py (khuyên dùng)
python run.py

# Cách 2 – uvicorn trực tiếp
uvicorn app.main:app --host localhost --port 8001 --reload
```

Server khởi động tại: `http://localhost:8001`  
Swagger UI (tài liệu API): `http://localhost:8001/docs`  
Health check: `http://localhost:8001/health`

---

## API Endpoints

| Method     | Endpoint                            | Mô tả                                 |
| ---------- | ----------------------------------- | ------------------------------------- |
| `GET`      | `/`                                 | Thông tin server                      |
| `GET`      | `/health`                           | Health check (gemini, mathpix status) |
| `POST`     | `/api/v1/chat/session`              | Tạo phiên chat mới                    |
| `POST`     | `/api/v1/chat/message`              | Gửi tin nhắn (streaming)              |
| `GET`      | `/api/v1/chat/history/{session_id}` | Lấy lịch sử chat                      |
| `GET/POST` | `/api/v1/ranking/...`               | Tra cứu điểm, xếp hạng                |
| `GET/POST` | `/api/v1/university/...`            | Thông tin trường đại học              |

### SGK PDF Processing

| Method   | Endpoint                                | Mô tả                                    |
| -------- | --------------------------------------- | ---------------------------------------- |
| `POST`   | `/api/v1/books/upload`                  | Upload PDF SGK (multipart/form-data)     |
| `GET`    | `/api/v1/books/`                        | Danh sách sách (`?grade=8&status=done`)  |
| `GET`    | `/api/v1/books/{id}`                    | Chi tiết sách (stats, gemini_calls, ...) |
| `GET`    | `/api/v1/books/{id}/status`             | Polling trạng thái xử lý real-time       |
| `DELETE` | `/api/v1/books/{id}`                    | Xoá sách + toàn bộ dữ liệu liên quan     |
| `GET`    | `/api/v1/books/{id}/chapters`           | Danh sách chương của sách                |
| `GET`    | `/api/v1/chapters/{chapter_id}`         | Chi tiết chương                          |
| `GET`    | `/api/v1/chapters/{chapter_id}/lessons` | Danh sách bài học                        |
| `GET`    | `/api/v1/lessons/{lesson_id}`           | Chi tiết bài học                         |
| `GET`    | `/api/v1/lessons/{lesson_id}/content`   | Nội dung bài (text, formula, image, ...) |
| `GET`    | `/api/v1/books/{id}/export/json`        | Export toàn bộ cấu trúc dạng JSON        |
| `GET`    | `/api/v1/books/{id}/export/md`          | Export Markdown với LaTeX                |
| `GET`    | `/api/v1/books/{id}/export/chunks`      | Export RAG chunks có metadata            |
| `GET`    | `/api/v1/search?q=...`                  | Full-text search nội dung SGK            |

---

## Ví dụ sử dụng (cURL)

```bash
# 1. Upload PDF
BOOK_ID=$(curl -s -X POST http://localhost:8000/api/v1/books/upload \
  -F "file=@toan8.pdf" \
  -F "grade=8" \
  -F "publisher=CTST" \
  -F "title=Toán 8" \
  | python -c "import sys,json; print(json.load(sys.stdin)['book_id'])")
echo "Book ID: $BOOK_ID"

# 2. Polling trạng thái xử lý
while true; do
  RESP=$(curl -s "http://localhost:8000/api/v1/books/$BOOK_ID/status")
  echo "$RESP" | python -c "import sys,json; d=json.load(sys.stdin); print(f\"[{d['current_phase']}] {d['progress']}%\")"
  STATUS=$(echo "$RESP" | python -c "import sys,json; print(json.load(sys.stdin)['status'])")
  if [ "$STATUS" = "done" ] || [ "$STATUS" = "error" ]; then break; fi
  sleep 5
done

# 3. Lấy danh sách chương
curl "http://localhost:8000/api/v1/books/$BOOK_ID/chapters" | python -m json.tool

# 4. Export Markdown
curl "http://localhost:8000/api/v1/books/$BOOK_ID/export/md" > toan8.md

# 5. Export RAG chunks
curl "http://localhost:8000/api/v1/books/$BOOK_ID/export/chunks" > chunks.json

# 6. Tìm kiếm
curl "http://localhost:8000/api/v1/search?q=số+hữu+tỉ&grade=8" | python -m json.tool
```

---

## Testing (Kiểm thử)

Project có test suite đầy đủ cho tất cả 10 phases:

### Quick Start — Standalone Tests (không cần pytest)

```bash
# Chạy từng phase
python tests/test_phase1.py   # PDF Ingestion
python tests/test_phase2.py   # Gemini OCR
python tests/test_phase3.py   # Mathpix Fallback
python tests/test_phase4.py   # Image Extraction
python tests/test_phase5.py   # Structure Parser
python tests/test_phase6.py   # MongoDB Models
python tests/test_phase7.py   # Processing Pipeline
python tests/test_phase8.py   # FastAPI Endpoints
python tests/test_phase9.py   # E2E Integration
python tests/test_phase10.py  # Final Validation (Docker, README, Scripts)
```

### Full Test Suite

```bash
# Chạy tất cả
pytest tests/ -v

# Chạy với timeout
pytest tests/ -v --timeout=60

# Chạy với coverage
pytest tests/ --cov=app.services --cov-report=html
```

### Bảng tổng hợp

| Phase    | Mô tả                                       | Số tests |
| -------- | ------------------------------------------- | -------- |
| Phase 1  | PDF → JPEG rendering, metadata, image size  | 7        |
| Phase 2  | Gemini OCR, JSON parsing, rate limit, retry | 6        |
| Phase 3  | Mathpix fallback, LaTeX validation, crop    | 9        |
| Phase 4  | Image extraction, bbox, thumbnail           | 8        |
| Phase 5  | Structure parser, chapter/lesson detection  | 8        |
| Phase 6  | MongoDB schemas, repositories, CRUD         | 7        |
| Phase 7  | Processing pipeline end-to-end              | 13       |
| Phase 8  | FastAPI endpoints, upload, export, search   | 10       |
| Phase 9  | E2E integration với mock services           | 8        |
| Phase 10 | Final validation: Docker, README, scripts   | 8        |

---

## Độ chính xác OCR

| Dịch vụ             | Text thường | Công thức toán | Ghi chú                                    |
| ------------------- | ----------- | -------------- | ------------------------------------------ |
| Gemini Flash Vision | ~88–93%     | ~85–92%        | 1 API call/trang, nhận diện toàn bộ layout |
| Mathpix (fallback)  | —           | ~95–98%        | Chỉ gọi khi Gemini fail (confidence < 0.6) |

---

## Chi phí ước tính (5 cuốn SGK ~1000 trang)

| Dịch vụ            | Free limit                     | Chi phí nếu vượt |
| ------------------ | ------------------------------ | ---------------- |
| Gemini Flash       | 250 req/ngày (chia nhiều ngày) | $0.075/1M tokens |
| Mathpix (optional) | $20 credit sau đăng ký         | $0.002/ảnh       |
| MongoDB            | Local / Atlas free 512MB       | $0               |
| Storage            | Local disk                     | $0               |
| **Tổng**           | **~$0–25 cho cả dự án**        |                  |

---

## Thay đổi model LLM (Chatbot)

### OpenAI (ChatGPT)

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

### Google Gemini (qua OpenAI-compatible API)

```env
OPENAI_API_KEY=AIza...
OPENAI_MODEL=gemini-1.5-pro
```

Sửa `app/services/openai_service.py`:

```python
self.client = openai.AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)
```

---

## Tùy chỉnh & mở rộng

- **Prompt Gemini OCR:** chỉnh sửa `PAGE_ANALYSIS_PROMPT` trong `app/services/gemini_service.py`
- **Rule engine:** thêm patterns nhận diện Chương/Bài trong `app/services/structure_parser.py`
- **Knowledge base chatbot:** cập nhật `app/data/knowledge_base.json`
- **Giới hạn context:** thay đổi `CHAT_HISTORY_LIMIT` trong `.env`
- **DPI render:** thay đổi `RENDER_DPI` (150–200) trong `app/services/pdf_parser.py`

---

## Liên hệ

Nếu cần hỗ trợ hoặc file dữ liệu mẫu: dangkhoipham80@gmail.com
