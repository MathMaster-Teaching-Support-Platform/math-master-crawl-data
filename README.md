# EduPath AI Chatbot - FastAPI

Chatbot tư vấn tuyển sinh đại học, hỗ trợ tiếng Việt, sử dụng LLM (OpenAI GPT, Gemini, ...), MongoDB, cấu hình linh hoạt qua file `.env`.

## Tính năng nổi bật

- Tư vấn chọn trường, ngành, điểm chuẩn, học phí, lịch tuyển sinh
- Tra cứu điểm thi THPT theo số báo danh, xem xếp hạng
- Nhận diện ý định thông minh (fuzzy intent detection, keyword cấu hình ngoài)
- Giao tiếp tự nhiên, nhớ tên người dùng, cá nhân hóa hội thoại
- Lưu lịch sử chat vào MongoDB, giới hạn context cấu hình được
- Prompt hệ thống, từ khóa, knowledge base đều có thể chỉnh sửa ngoài code
- Logging chuyên nghiệp, dễ debug và mở rộng

---

## Yêu cầu

| Thành phần | Phiên bản / Ghi chú |
|---|---|
| Python | >= 3.11.7 |
| MongoDB | Đang chạy tại `mongodb://localhost:27017` |
| LLM API key | OpenAI / Gemini / Azure OpenAI |
| Rust (Windows) | Cần để build `pydantic-core` |

---

## Cài đặt

```bash
# 1. Clone repo
git clone <repo-url>
cd math-master-crawl-data

# 2. Tạo và kích hoạt virtual environment
python -m venv venv

# Windows
.\venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 3. Cài dependencies
pip install -r requirements.txt
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

| Biến | Mặc định | Mô tả |
|---|---|---|
| `OPENAI_API_KEY` | *(bắt buộc)* | API key của nhà cung cấp LLM |
| `OPENAI_MODEL` | `gpt-3.5-turbo` | Tên model LLM (xem bên dưới) |
| `MONGO_URL` | `mongodb://localhost:27017` | Connection string MongoDB |
| `MONGO_DB` | `sgk_toan` | Tên database |
| `STORAGE_PATH` | `./storage` | Thư mục lưu ảnh trích xuất |
| `GEMINI_API_KEY` | *(optional)* | Google Gemini API key (OCR chính) |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Tên model Gemini |
| `MATHPIX_APP_ID` | *(optional)* | Mathpix App ID (formula fallback) |
| `MATHPIX_APP_KEY` | *(optional)* | Mathpix App Key |
| `MATHPIX_ENABLED` | `false` | Bật Mathpix fallback |
| `MAX_FILE_SIZE_MB` | `50` | Giới hạn kích thước PDF upload |
| `PORT` | `8001` | Cổng server |
| `DEBUG` | `False` | Bật/tắt chế độ debug & auto-reload |
| `API_PREFIX` | `/api/v1` | Tiền tố cho tất cả các API route |
| `CHAT_HISTORY_LIMIT` | `30` | Số lượt hội thoại tối đa giữ trong context |
| `SECRET_KEY` | `your-secret-key` | Secret key cho ứng dụng |

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

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/` | Thông tin server |
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/chat/session` | Tạo phiên chat mới |
| `POST` | `/api/v1/chat/message` | Gửi tin nhắn (streaming) |
| `GET` | `/api/v1/chat/history/{session_id}` | Lấy lịch sử chat |
| `GET/POST` | `/api/v1/ranking/...` | Tra cứu điểm, xếp hạng |
| `GET/POST` | `/api/v1/university/...` | Thông tin trường đại học |
| `POST` | `/api/v1/books/upload` | Upload PDF SGK để xử lý |
| `GET` | `/api/v1/books/` | Danh sách sách đã upload |
| `GET` | `/api/v1/books/{id}/status` | Trạng thái xử lý real-time |
| `GET` | `/api/v1/chapters/` | Danh sách chương theo sách |
| `GET` | `/api/v1/lessons/` | Danh sách bài theo chương |
| `GET` | `/api/v1/search?q=...` | Tìm kiếm nội dung SGK |

---

## Thay đổi model LLM

### OpenAI (ChatGPT)

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o          # hoặc: gpt-4, gpt-4-turbo, gpt-3.5-turbo
```

### Google Gemini (qua OpenAI-compatible API)

Google Gemini hỗ trợ endpoint tương thích OpenAI. Chỉ cần đổi biến môi trường:

```env
OPENAI_API_KEY=AIza...          # Google AI Studio API key
OPENAI_MODEL=gemini-1.5-pro     # hoặc: gemini-1.5-flash, gemini-2.0-flash
```

Sau đó sửa `app/services/openai_service.py` để trỏ base URL sang Gemini:

```python
self.client = openai.AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)
```

### Azure OpenAI

```env
OPENAI_API_KEY=<azure-key>
OPENAI_MODEL=gpt-4o            # deployment name trên Azure
```

Sửa `app/services/openai_service.py`:

```python
self.client = openai.AsyncAzureOpenAI(
    api_key=settings.openai_api_key,
    azure_endpoint="https://<your-resource>.openai.azure.com/",
    api_version="2024-02-01"
)
```

### Dùng LiteLLM (hỗ trợ 100+ provider)

Cài thêm: `pip install litellm`

Sau đó thay toàn bộ `openai.AsyncOpenAI` bằng `litellm.acompletion` trong `app/services/openai_service.py`. LiteLLM hỗ trợ prefix model: `gemini/gemini-1.5-pro`, `anthropic/claude-3-5-sonnet`, `ollama/llama3`, v.v.

---

## Tùy chỉnh & mở rộng

- **Prompt hệ thống:** chỉnh sửa file `app/data/system_prompt.txt` để thay đổi phong cách, nhiệm vụ bot.
- **Từ khóa intent:** chỉnh sửa trực tiếp các trường `keywords` trong file `app/data/knowledge_base.json` để thêm/bớt từ khóa nhận diện ý định.
- **Knowledge base:** cập nhật file `app/data/knowledge_base.json` để bổ sung kiến thức tư vấn.
- **Giới hạn context:** thay đổi `CHAT_HISTORY_LIMIT` trong `.env` để kiểm soát số tin nhắn nhớ trong hội thoại.

## Liên hệ

Nếu cần file dữ liệu mẫu trong thư mục `data/*.json` để training, inbox: dangkhoipham80@gmail.com
