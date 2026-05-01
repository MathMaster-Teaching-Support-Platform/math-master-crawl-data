# 📚 SGK TOÁN PDF → API — AI PROMPT GUIDE v2
> **Stack:** FastAPI + MongoDB + Gemini Flash (OCR chính) + Mathpix (formula fallback)  
> **Nguyên tắc:** Làm từng step một. Test xong mới qua bước kế. Copy từng prompt vào AI, chờ checklist ✅ trước khi tiếp.

---

## 🗺️ TỔNG QUAN KIẾN TRÚC MỚI

```
Upload PDF
   ↓
PyMuPDF → render từng trang thành ảnh (150–200 DPI, JPEG)
   ↓
Gemini Flash Vision (1 API call/trang)
   → Nhận diện layout + text + công thức + hình cùng lúc
   → Output JSON có cấu trúc block
   ↓
Post-process JSON:
   - Nếu formula confidence thấp → gọi Mathpix v3/text (fallback)
   - Nếu formula OK → giữ LaTeX từ Gemini
   - Nếu image block → crop + lưu storage
   ↓
Rule Engine: detect Chương / Bài / Ví dụ / Bài tập
   ↓
MongoDB normalize
   ↓
FastAPI query layer
```

### Tại sao Gemini Flash thay vì local stack?
| | Local (PaddleOCR + Pix2Text) | Gemini Flash |
|---|---|---|
| Formula accuracy | 60–75% | 85–92% |
| Code phức tạp | Rất cao (5 thư viện) | Thấp (1 API call) |
| RAM yêu cầu | 8GB+ | Bình thường |
| Chi phí | $0 nhưng accuracy thấp | Free (250 req/ngày) |
| Setup | Khó (CUDA, paddle...) | Dễ (pip install) |

### Khi nào dùng Mathpix fallback?
Mathpix hỗ trợ toàn bộ LaTeX math commands chuẩn: `\frac`, `\sum`, `\int`, `\sqrt`, `\alpha`...`\omega`, `\mathbb`, `\mathcal`, tất cả ký hiệu tập hợp, mũi tên, hình học — đủ cho SGK phổ thông. Dùng Mathpix khi:
- Gemini trả về latex trống hoặc rác (`confidence < 0.6`)
- Block công thức phức tạp: tích phân, ma trận, tổng có giới hạn
- Ảnh chất lượng thấp mà Gemini fail

---

## ⚙️ PHASE 0 — PROJECT SETUP

### 📋 Prompt cho AI:

```
Bạn là senior backend developer. Tôi đang làm đồ án sinh viên: số hóa SGK Toán PDF → FastAPI + MongoDB.

Stack chính: FastAPI + MongoDB + Gemini Flash API (OCR) + Mathpix API (formula fallback).

Hãy setup project skeleton với cấu trúc (tuân theo convention hiện tại của dự án):

math-master-crawl-data/
├── app/
│   ├── main.py
│   ├── controllers/             # FastAPI routers (APIRouter)
│   │   ├── __init__.py
│   │   ├── book_controller.py
│   │   ├── chapter_controller.py
│   │   ├── lesson_controller.py
│   │   └── search_controller.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── pdf_parser.py        # PyMuPDF
│   │   ├── gemini_service.py    # Gemini Flash Vision — OCR chính
│   │   ├── mathpix_service.py   # Mathpix — formula fallback
│   │   ├── image_service.py     # Crop + lưu hình
│   │   ├── structure_parser.py  # Rule engine Chương/Bài
│   │   └── processing_pipeline.py
│   ├── repositories/            # Motor async repos (tương tự chat_repository.py)
│   │   ├── __init__.py
│   │   ├── book_repository.py
│   │   ├── chapter_repository.py
│   │   ├── lesson_repository.py
│   │   └── content_repository.py
│   ├── schemas/                 # Pydantic request/response models
│   │   ├── __init__.py
│   │   ├── book.py
│   │   ├── chapter.py
│   │   ├── lesson.py
│   │   └── content.py
│   ├── core/                    # Config + MongoDB (đã có sẵn)
│   │   ├── __init__.py
│   │   ├── config.py            # pydantic_settings Settings
│   │   └── mongo.py             # Motor AsyncIOMotorClient
│   └── utils/
│       ├── __init__.py
│       └── response.py          # success_response helper
├── storage/images/
├── data/books/
├── tests/
├── requirements.txt
├── .env.example
└── docker-compose.yml

YÊU CẦU:

1. requirements.txt — thêm vào file hiện tại:
   pymupdf, pillow, google-generativeai
   (motor, pymongo, python-multipart, python-dotenv, httpx, pytest, pytest-asyncio đã có)

2. .env.example — thêm các keys mới vào file .env hiện tại:
   # --- SGK PDF Processing ---
   MONGO_URL=mongodb://localhost:27017   # đã có, giữ nguyên
   MONGO_DB=sgk_toan                    # đổi từ ai_chatbot nếu muốn DB riêng
   STORAGE_PATH=./storage
   GEMINI_API_KEY=your_key_here
   MATHPIX_APP_ID=your_app_id
   MATHPIX_APP_KEY=your_app_key
   MATHPIX_ENABLED=false         # bật khi có key, tắt để test local
   MAX_FILE_SIZE_MB=50
   GEMINI_MODEL=gemini-2.0-flash

3. docker-compose.yml: chạy MongoDB + app

4. app/core/config.py — thêm fields mới vào class Settings hiện tại:
   # Các field đã có: app_name, debug, openai_api_key, mongo_url, mongo_db, ...
   storage_path: str = os.getenv("STORAGE_PATH", "./storage")
   gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
   gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
   mathpix_app_id: Optional[str] = os.getenv("MATHPIX_APP_ID")
   mathpix_app_key: Optional[str] = os.getenv("MATHPIX_APP_KEY")
   mathpix_enabled: bool = os.getenv("MATHPIX_ENABLED", "false").lower() == "true"
   max_file_size_mb: int = int(os.getenv("MAX_FILE_SIZE_MB", 50))

5. app/main.py — cập nhật file hiện tại:
   - Thêm StaticFiles mount: app.mount("/static", StaticFiles(directory=settings.storage_path))
   - Thêm /health trả về {"status": "ok", "gemini": bool(settings.gemini_api_key), "mathpix": settings.mathpix_enabled}
   - Register các controllers mới: book_controller, chapter_controller, lesson_controller, search_controller

6. app/core/mongo.py — tạo indexes khi startup (thêm vào startup event của main.py):
   Import mongo_db từ app.core.mongo (đã có sẵn, dùng lại)

SAU KHI XONG, hãy:
✅ CHECKLIST:
- [x] Cấu trúc thư mục đầy đủ
- [x] requirements.txt có đủ thư viện
- [x] .env.example có GEMINI_API_KEY và MATHPIX keys
- [x] app/main.py chạy được: uvicorn app.main:app --reload
- [x] GET /health trả về {"status": "ok"}
- [x] Static mount hoạt động

⚠️ BÁO LỖI NẾU:
- google-generativeai version conflict
- Motor không kết nối được MongoDB

🧪 TEST:
  uvicorn app.main:app --reload
  curl http://localhost:8000/health

⏸️ PENDING: Dừng tại đây, chờ tôi confirm "OK Phase 0".
```

---

## 📄 PHASE 1 — PDF INGESTION

### 📋 Prompt cho AI:

```
Tiếp tục dự án SGK Toán. Phase 0 xong.

Implement PHASE 1: PDF Ingestion với PyMuPDF.

File: app/services/pdf_parser.py

YÊU CẦU:

1. Hàm validate_pdf(file_path: str) -> bool
   - Kiểm tra PDF hợp lệ, số trang > 0

2. Hàm render_pages(pdf_path: str, output_dir: str) -> list[PageInfo]
   - Render từng trang thành ảnh JPEG (KHÔNG dùng PNG)
   - DPI: 150 (theo Mathpix best practices: 150–200 DPI đủ cho OCR)
   - Compress JPEG quality=85 để giữ file < 100KB/trang nếu có thể
   - Convert sang grayscale nếu trang không có màu quan trọng
   - Lưu: output_dir/pages/page_001.jpg, page_002.jpg...
   - Return list PageInfo

3. Dataclass PageInfo:
   @dataclass
   class PageInfo:
       page_num: int
       image_path: str
       file_size_kb: float
       width: int
       height: int
       is_grayscale: bool

4. Hàm extract_pdf_metadata(pdf_path: str) -> dict
   - title, author, num_pages, file_size_mb

5. Hàm check_image_size(image_path: str) -> dict
   - Nếu file > 100KB → warn (sẽ ảnh hưởng latency Mathpix/Gemini)
   - Return {"path": ..., "size_kb": ..., "needs_compression": bool}

LƯU Ý QUAN TRỌNG từ Mathpix docs:
- "Keep images under 100KB for maximum speed"
- "Use JPEG compression to reduce file size"
- "150–200 DPI is sufficient for most documents"
→ Áp dụng cho cả Gemini (cùng nguyên tắc)

PATH CONVENTION:
  /data/books/{book_id}/
    pages/
      page_001.jpg   ← JPEG, ~50-150KB mỗi trang
    metadata.json

SAU KHI XONG, hãy:
✅ CHECKLIST:
- [x] render_pages() output JPEG (không phải PNG)
- [x] File size hợp lý: < 200KB/trang ở 150 DPI
- [x] PageInfo dataclass đủ fields
- [x] check_image_size() warn khi > 100KB
- [x] extract_pdf_metadata() trả về đủ info
- [x] Không memory leak (dùng context manager fitz.open)

⚠️ BÁO LỖI NẾU:
- JPEG quality 85 vẫn > 200KB → cần giảm DPI hoặc resize
- fitz render crash với PDF có font lạ

🧪 TEST:
  from app.services.pdf_parser import render_pages, check_image_size
  pages = render_pages("test.pdf", "data/books/test")
  for p in pages:
      info = check_image_size(p.image_path)
      print(f"Page {p.page_num}: {info['size_kb']:.1f} KB")

⏸️ PENDING: Dừng tại đây, chờ tôi confirm "OK Phase 1".
```

---

## 🤖 PHASE 2 — GEMINI FLASH OCR SERVICE

### 📋 Prompt cho AI:

```
Tiếp tục dự án SGK Toán. Phase 1 xong.

Implement PHASE 2: Gemini Flash Vision Service — đây là thay thế toàn bộ
PaddleOCR + PP-Structure + Pix2Text trong 1 service duy nhất.

File: app/services/gemini_service.py

CONTEXT SGK TOÁN VIỆT NAM:
- Layout: 1-2 cột, có viền màu cho ví dụ/bài tập
- Công thức: inline ($x^2$) và display ($$\frac{a}{b}$$)
- Các block đặc trưng: Chương, Bài, Ví dụ, Hoạt động, Bài tập, Ghi nhớ
- Hình vẽ hình học kèm caption "Hình X"
- LaTeX chuẩn: \frac, \sqrt, \sum, \int, \alpha...\omega, \mathbb, \vec, v.v.

YÊU CẦU:

1. Class GeminiOCRService (Singleton):
   - __init__: init google.generativeai với API key từ config
   - analyze_page(image_path: str, page_num: int) -> PageAnalysis

2. Dataclass PageAnalysis:
   @dataclass
   class PageAnalysis:
       page_num: int
       blocks: list[ContentBlock]
       raw_response: str       # giữ lại để debug
       processing_time_ms: int

3. Dataclass ContentBlock:
   @dataclass
   class ContentBlock:
       type: str               # "chapter_title"|"lesson_title"|"text"|"formula"|
                               # "exercise"|"image"|"table"|"definition"|"note"
       content: str            # text nội dung
       latex: str              # nếu type=formula
       image_bbox: tuple       # (x1,y1,x2,y2) nếu type=image, tọa độ tương đối 0-1
       caption: str            # caption của hình nếu có
       order: int              # thứ tự trong trang
       confidence: float       # 0.0-1.0, do Gemini tự đánh giá
       needs_mathpix: bool     # True nếu formula khó, cần Mathpix verify

4. PROMPT TEMPLATE cho Gemini (quan trọng nhất):

SYSTEM_PROMPT = """
Bạn là AI chuyên phân tích sách giáo khoa Toán Việt Nam. 
Hãy phân tích ảnh trang SGK và trả về JSON CHÍNH XÁC theo format sau.
CHỈ trả về JSON, không giải thích thêm.
"""

PAGE_ANALYSIS_PROMPT = """
Phân tích trang SGK Toán này. Nhận diện TẤT CẢ các block nội dung theo thứ tự đọc (trên→dưới, trái→phải).

Với mỗi block, xác định:
- type: chapter_title | lesson_title | text | formula | exercise | image | table | definition | note
- content: nội dung text (nếu có)  
- latex: công thức LaTeX chuẩn (nếu type=formula). Dùng đúng commands: \\frac{}{}, \\sqrt{}, \\sum_{i=1}^{n}, \\int_{a}^{b}, \\alpha, \\beta, \\gamma, \\Delta, \\Sigma, \\mathbb{R}, \\vec{v}, \\overline{AB}, \\angle, \\perp, \\parallel, \\in, \\subset, \\cup, \\cap
- image_bbox: [x1,y1,x2,y2] tọa độ tương đối 0-1 nếu type=image (null nếu không phải)
- caption: caption của hình (null nếu không có)
- confidence: độ tin cậy của nhận diện (0.0-1.0)
- needs_mathpix: true nếu công thức phức tạp hoặc bạn không chắc về latex

Patterns nhận diện:
- chapter_title: "CHƯƠNG I", "Chương 1.", "CHƯƠNG 2:", text to/đậm ở đầu chapter
- lesson_title: "Bài 1.", "Bài 2:", "§1.", text to ở đầu bài học
- exercise: bắt đầu bằng "Bài tập", "Luyện tập", "Ví dụ N", "Hoạt động N", "Khám phá"
- definition: "Định nghĩa", "Tính chất", "Định lý", "Hệ quả" thường có viền/nền màu
- note: "Chú ý", "Nhận xét", "Ghi nhớ"
- formula: bất kỳ công thức toán nào, kể cả inline trong câu

Trả về JSON:
{
  "page_num": <số trang>,
  "blocks": [
    {
      "type": "chapter_title",
      "content": "CHƯƠNG I. SỐ HỮU TỈ",
      "latex": null,
      "image_bbox": null,
      "caption": null,
      "confidence": 0.98,
      "needs_mathpix": false,
      "order": 1
    },
    {
      "type": "formula",
      "content": null,
      "latex": "\\frac{a}{b} + \\frac{c}{d} = \\frac{ad+bc}{bd}",
      "image_bbox": null,
      "caption": null,
      "confidence": 0.85,
      "needs_mathpix": false,
      "order": 5
    },
    {
      "type": "image",
      "content": null,
      "latex": null,
      "image_bbox": [0.1, 0.4, 0.6, 0.75],
      "caption": "Hình 1.3",
      "confidence": 0.95,
      "needs_mathpix": false,
      "order": 7
    }
  ]
}
"""

5. Hàm analyze_page():
   - Load ảnh JPEG
   - Gọi Gemini với prompt trên
   - Parse JSON response
   - Nếu JSON parse lỗi → retry 1 lần với prompt ngắn hơn
   - Return PageAnalysis

6. Hàm _encode_image(image_path: str) -> dict:
   - Đọc JPEG, encode base64
   - Return {"mime_type": "image/jpeg", "data": base64_string}

7. Rate limiting helper:
   - Gemini free: 10 RPM → sleep 6s giữa các request
   - Implement simple rate limiter với asyncio

8. Retry logic:
   - Max 3 retries nếu API error
   - Exponential backoff: 2s, 4s, 8s

LƯU Ý:
- Dùng google.generativeai SDK: import google.generativeai as genai
- Import config: from app.core.config import settings
- Model: settings.gemini_model (default: "gemini-2.0-flash")
- API key: settings.gemini_api_key
- Temperature: 0.1 (cần output ổn định, không sáng tạo)
- Không dùng stream (cần full response để parse JSON)

SAU KHI XONG, hãy:
✅ CHECKLIST:
- [ ] GeminiOCRService khởi tạo không lỗi
- [ ] analyze_page() trả về PageAnalysis hợp lệ
- [ ] JSON parse thành công với response thật
- [ ] Rate limiter hoạt động (không exceed 10 RPM)
- [ ] Retry logic hoạt động khi API timeout
- [ ] formula block có latex hợp lệ
- [ ] image block có image_bbox dạng [x1,y1,x2,y2]
- [ ] needs_mathpix được set đúng

⚠️ BÁO LỖI NẾU:
- Gemini trả về text không phải JSON → cần fix prompt
- Rate limit 429 error → cần tăng sleep interval
- Image quá lớn → Gemini từ chối

🧪 TEST:
  import asyncio
  from app.services.gemini_service import GeminiOCRService
  
  async def test():
      svc = GeminiOCRService()
      result = await svc.analyze_page("data/books/test/pages/page_001.jpg", 1)
      print(f"Found {len(result.blocks)} blocks")
      for b in result.blocks:
          print(f"  [{b.type}] order={b.order} conf={b.confidence:.2f}")
          if b.type == "formula":
              print(f"    LaTeX: {b.latex}")
  
  asyncio.run(test())

⏸️ PENDING: Dừng tại đây, chờ tôi confirm "OK Phase 2".
```

---

## 🔢 PHASE 3 — MATHPIX FALLBACK SERVICE

### 📋 Prompt cho AI:

```
Tiếp tục dự án SGK Toán. Phase 2 xong (Gemini OCR).

Implement PHASE 3: Mathpix Fallback Service — chỉ gọi khi Gemini fail với formula.

File: app/services/mathpix_service.py

CHIẾN LƯỢC:
Mathpix chỉ được gọi khi:
1. block.type == "formula" AND block.needs_mathpix == True
2. block.type == "formula" AND block.confidence < 0.6
3. block.latex rỗng hoặc không hợp lệ

MATHPIX API FLOW (theo docs):
- Endpoint: POST https://api.mathpix.com/v3/text
- Headers: app_id + app_key
- Body: {"src": "data:image/jpeg;base64,...", "formats": ["latex_styled", "text"]}
- Response: {"latex_styled": "\\frac{a}{b}", "text": "a/b", "confidence": 0.98}

YÊU CẦU:

1. Class MathpixService:
   - __init__: load app_id, app_key từ config
   - is_enabled() -> bool: check MATHPIX_ENABLED từ config
   - extract_formula(image_path: str, bbox: tuple) -> MathpixResult

2. Dataclass MathpixResult:
   @dataclass
   class MathpixResult:
       latex: str           # latex_styled từ Mathpix
       text: str            # plain text fallback
       confidence: float    # Mathpix confidence
       success: bool        # False nếu API fail

3. Hàm extract_formula(image_path: str, bbox: tuple) -> MathpixResult:
   - Crop vùng bbox từ ảnh trang (bbox là tọa độ pixel tuyệt đối)
   - Nếu bbox là tương đối (0-1) → convert sang pixel dùng image dimensions
   - Preprocess ảnh crop:
     + Convert grayscale
     + Thêm padding 10px mỗi cạnh (giúp Mathpix nhận diện tốt hơn)
     + Compress JPEG < 100KB (theo Mathpix latency guide)
   - Encode base64
   - POST đến Mathpix v3/text
   - Parse response, return MathpixResult

4. Hàm batch_extract(formula_blocks: list[dict], page_image_path: str) -> list[MathpixResult]:
   - Xử lý nhiều formula trên 1 trang
   - Rate limit: tránh quá nhiều request/phút

5. Hàm validate_latex(latex: str) -> bool:
   - Kiểm tra latex không phải chuỗi rác
   - Phải chứa ít nhất 1 trong: \, ^, _, {, }, số, ký tự toán học
   - Không quá ngắn (< 2 ký tự) và không quá dài (> 500 ký tự khi nghi ngờ)

6. Hàm latex_to_readable(latex: str) -> str:
   - Convert latex đơn giản sang text đọc được
   - Dùng khi cần hiển thị plain text
   - VD: \frac{1}{2} → "1/2", \sqrt{x} → "√x", x^2 → "x²"

IMPORTANT — Mathpix supported commands (từ docs):
Mathpix generate được đầy đủ: \frac, \sqrt, \sum, \int, \oint, \prod,
\alpha...\omega, \Gamma...\Omega, \mathbb{R}, \mathcal{A}, \mathbf{A},
\vec, \hat, \dot, \ddot, \overline, \angle, \perp, \parallel,
\in, \notin, \subset, \subseteq, \cup, \cap, \bigcup, \bigcap,
\leq, \geq, \neq, \approx, \equiv, \sim, \therefore, \because,
\rightarrow, \Rightarrow, \Leftrightarrow, \infty, \partial, \nabla...
→ Tất cả ký hiệu trong SGK Toán phổ thông đều được hỗ trợ.

IMPORT CONVENTION:
- from app.core.config import settings
- Dùng: settings.mathpix_enabled, settings.mathpix_app_id, settings.mathpix_app_key

FALLBACK KHI MATHPIX DISABLED (settings.mathpix_enabled = False):
- Return MathpixResult(latex=gemini_latex, success=False, confidence=0)
- Log warning nhưng không crash

SAU KHI XONG, hãy:
✅ CHECKLIST:
- [ ] MathpixService.is_enabled() check config đúng
- [ ] extract_formula() crop bbox chính xác
- [ ] Preprocess: grayscale + padding + compress < 100KB
- [ ] POST đến Mathpix API thành công
- [ ] Response parse đúng (latex_styled, confidence)
- [ ] validate_latex() reject chuỗi rác
- [ ] Fallback hoạt động khi MATHPIX_ENABLED=false
- [ ] Không crash khi API unavailable

⚠️ BÁO LỖI NẾU:
- Mathpix trả về 401 → API key sai
- Mathpix trả về 429 → rate limit → thêm sleep
- Crop bbox out of bounds → cần clamp coordinates

🧪 TEST (với MATHPIX_ENABLED=false trước):
  from app.services.mathpix_service import MathpixService, validate_latex
  
  svc = MathpixService()
  print(f"Mathpix enabled: {svc.is_enabled()}")
  
  assert validate_latex(r"\frac{1}{2}") == True
  assert validate_latex("abc xyz") == False
  assert validate_latex(r"\sum_{i=1}^{n} x_i") == True
  
  # Test với key thật:
  # result = svc.extract_formula("page_005.jpg", (200, 300, 500, 350))
  # print(f"LaTeX: {result.latex}, confidence: {result.confidence}")

⏸️ PENDING: Dừng tại đây, chờ tôi confirm "OK Phase 3".
```

---

## 🖼️ PHASE 4 — IMAGE EXTRACTION SERVICE

### 📋 Prompt cho AI:

```
Tiếp tục dự án SGK Toán. Phase 3 xong (Mathpix fallback).

Implement PHASE 4: Image Extraction — crop và lưu hình từ trang SGK.

File: app/services/image_service.py

CONTEXT:
Gemini đã trả về image_bbox dạng tọa độ tương đối [x1,y1,x2,y2] trong [0,1].
Cần convert sang pixel, crop, và lưu.

YÊU CẦU:

1. Class ImageExtractor:
   - extract_and_store(page_image_path, bbox_relative, book_id, page_num, fig_index) -> ImageResult
   - generate_thumbnail(image_path, max_size=300) -> str  # path thumbnail

2. Dataclass ImageResult:
   @dataclass
   class ImageResult:
       file_path: str       # đường dẫn tuyệt đối file đã lưu
       url: str             # URL API trả về: /static/images/{book_id}/...
       thumbnail_url: str   # URL thumbnail nhỏ hơn
       width: int
       height: int
       caption: str
       page_num: int
       fig_index: int
       file_size_kb: float

3. Hàm _bbox_relative_to_pixel(bbox_rel, img_width, img_height) -> tuple:
   - Convert [x1,y1,x2,y2] từ [0,1] sang pixel
   - Clamp để không ra ngoài bounds
   - Return (x1_px, y1_px, x2_px, y2_px)

4. Hàm _cleanup_figure(image: PIL.Image) -> PIL.Image:
   - Trim whitespace (auto-crop) bằng cách detect bounding box non-white pixels
   - Không resize (giữ tỉ lệ gốc)

5. Hàm _skip_if_too_small(bbox_px: tuple) -> bool:
   - Return True (skip) nếu width < 50 hoặc height < 50 px
   - Tránh lưu các "hình" là noise

PATH CONVENTION:
  storage/images/{book_id}/page_{page_num:03d}_fig_{fig_index:02d}.jpg
  storage/images/{book_id}/thumbs/page_{page_num:03d}_fig_{fig_index:02d}_thumb.jpg

URL CONVENTION:
  /static/images/{book_id}/page_{page_num:03d}_fig_{fig_index:02d}.jpg

SAU KHI XONG, hãy:
✅ CHECKLIST:
- [ ] bbox convert từ relative sang pixel chính xác
- [ ] Clamp bbox không ra ngoài ảnh
- [ ] Skip figure nhỏ hơn 50x50px
- [ ] Cleanup trim whitespace
- [ ] Thumbnail được tạo
- [ ] Path và URL đúng convention
- [ ] Lưu JPEG (không PNG) để tiết kiệm storage

⚠️ BÁO LỖI NẾU:
- PIL crop lỗi với bbox invalid
- Thumbnail quá mờ (quality thấp)
- Storage directory chưa tồn tại

🧪 TEST:
  from app.services.image_service import ImageExtractor
  extractor = ImageExtractor()
  result = extractor.extract_and_store(
      "data/books/test/pages/page_010.jpg",
      [0.1, 0.3, 0.7, 0.8],   # bbox relative
      "book_test", 10, 0
  )
  print(f"Saved: {result.file_path} ({result.file_size_kb:.1f}KB)")
  print(f"URL: {result.url}")
  assert os.path.exists(result.file_path)

⏸️ PENDING: Dừng tại đây, chờ tôi confirm "OK Phase 4".
```

---

## 🏗️ PHASE 5 — STRUCTURE PARSER

### 📋 Prompt cho AI:

```
Tiếp tục dự án SGK Toán. Phase 4 xong (Image Extraction).

Implement PHASE 5: Structure Parser — Rule Engine phân cấp Chương/Bài.

File: app/services/structure_parser.py

CONTEXT:
Input là list PageAnalysis từ Gemini (đã có blocks phân loại).
Cần build cây: Book → Chapter → Lesson → ContentBlocks.

YÊU CẦU:

1. Regex patterns (compile sẵn, handle 3 bộ SGK Việt Nam):

CHAPTER_PATTERNS = [
    # CTST, Kết Nối: "Chương I.", "CHƯƠNG 2:", "Chương III"
    r"^(CHƯƠNG|Chương)\s+([IVXivx]+|\d+)[.:\s]?\s*(.*)$",
    # Cánh Diều: "Chương 1 —"
    r"^(CHƯƠNG|Chương)\s+(\d+)\s*[—–-]\s*(.*)$",
]

LESSON_PATTERNS = [
    # "Bài 1.", "Bài 2:", "BÀI 3"
    r"^(BÀI|Bài)\s+(\d+)[.:\s]?\s*(.*)$",
    # "§1.", "§ 2:"
    r"^§\s*(\d+)[.:\s]?\s*(.*)$",
    # "1.", "2." ở đầu dòng (nếu font to, là lesson)
    r"^(\d+)\.\s+(.+)$",
]

EXERCISE_PATTERNS = {
    "vi_du":      r"^(Ví dụ|VÍ DỤ)\s*(\d+)",
    "bai_tap":    r"^(Bài tập|BÀI TẬP)",
    "luyen_tap":  r"^(Luyện tập|LUYỆN TẬP)",
    "hoat_dong":  r"^(Hoạt động|HOẠT ĐỘNG)\s*(\d+)",
    "kham_pha":   r"^(Khám phá|KHÁM PHÁ)",
    "van_dung":   r"^(Vận dụng|VẬN DỤNG)",
    "thu_thach":  r"^(Thử thách|THỬ THÁCH)",
}

2. Dataclasses:

@dataclass
class FinalContentBlock:
    type: str         # "text"|"formula"|"image"|"exercise"|"table"|"definition"|"note"
    content: str
    latex: str
    image_url: str
    thumbnail_url: str
    caption: str
    exercise_type: str  # "vi_du"|"bai_tap"|"luyen_tap"|... nếu type=exercise
    exercise_num: int
    order: int

@dataclass
class Lesson:
    index: int
    title: str
    page_start: int
    content_blocks: list[FinalContentBlock]

@dataclass
class Chapter:
    index: int          # số thứ tự (1, 2, 3...)
    roman_index: str    # "I", "II", "III" nếu có
    title: str
    page_start: int
    lessons: list[Lesson]

@dataclass
class BookStructure:
    grade: int
    title: str
    publisher: str
    chapters: list[Chapter]
    unassigned_blocks: list[FinalContentBlock]  # blocks trước chapter đầu tiên

3. Class StructureParser:

   parse_book(pages: list[PageAnalysis], grade: int, title: str) -> BookStructure
   
   _detect_chapter(block: ContentBlock) -> tuple[int, str, str] | None
   # Return (chapter_num, roman, chapter_title) hoặc None
   
   _detect_lesson(block: ContentBlock) -> tuple[int, str] | None
   # Return (lesson_num, lesson_title) hoặc None
   
   _detect_exercise(text: str) -> tuple[str, int] | None
   # Return (exercise_type, exercise_num) hoặc None
   
   _convert_block(block: ContentBlock, image_result: ImageResult | None) -> FinalContentBlock

4. QUAN TRỌNG — xử lý block "chapter_title" và "lesson_title" từ Gemini:
   - Gemini đã label sẵn chapter_title/lesson_title → ưu tiên dùng label này
   - Nếu block.type == "chapter_title" → KHÔNG cần regex, parse thẳng
   - Nếu block.type == "text" → chạy regex để detect chapter/lesson ẩn
   - Regex là safety net, không phải primary detector

SAU KHI XONG, hãy:
✅ CHECKLIST:
- [ ] Chapter detect đúng cả La mã và số Ả rập
- [ ] Lesson detect đúng "Bài X" và "§X"  
- [ ] Exercise type phân biệt đúng 7 loại
- [ ] Gemini labels được ưu tiên hơn regex
- [ ] unassigned_blocks chứa content trước chapter đầu tiên
- [ ] Chapter index là số, có thêm roman_index nếu có
- [ ] parse_book() không crash với SGK không có chapter rõ ràng

⚠️ BÁO LỖI NẾU:
- Regex false positive (match nhầm text thường)
- Chapter/lesson nested sai
- Content blocks bị mất

🧪 TEST (dùng mock PageAnalysis):
  from app.services.structure_parser import StructureParser
  
  mock_blocks = [
      ContentBlock(type="chapter_title", content="Chương I. SỐ HỮU TỈ", order=1, ...),
      ContentBlock(type="lesson_title", content="Bài 1. Số hữu tỉ", order=2, ...),
      ContentBlock(type="text", content="Số hữu tỉ là...", order=3, ...),
      ContentBlock(type="formula", latex=r"\frac{a}{b}", order=4, ...),
  ]
  # Wrap vào PageAnalysis mock
  parser = StructureParser()
  book = parser.parse_book(pages=[...], grade=8, title="Toán 8")
  assert len(book.chapters) == 1
  assert len(book.chapters[0].lessons) == 1
  assert len(book.chapters[0].lessons[0].content_blocks) >= 2

⏸️ PENDING: Dừng tại đây, chờ tôi confirm "OK Phase 5".
```

---

## 🗄️ PHASE 6 — MONGODB MODELS & REPOSITORIES

### 📋 Prompt cho AI:

```
Tiếp tục dự án SGK Toán. Phase 5 xong (Structure Parser).

Implement PHASE 6: MongoDB Pydantic Schemas + Async Repositories.

Convention dự án hiện tại:
- Pydantic models/schemas → app/schemas/*.py  (KHÔNG dùng app/models/)
- Repositories → app/repositories/*.py         (KHÔNG dùng app/db/repositories/)
- MongoDB connection → from app.core.mongo import mongo_db  (dùng lại file có sẵn)
- Config → from app.core.config import settings

Files:
- app/schemas/book.py, chapter.py, lesson.py, content.py
- app/repositories/book_repository.py, chapter_repository.py, lesson_repository.py, content_repository.py
- app/core/mongo.py (thêm index creation, KHÔNG tạo file mới)

SCHEMA:

1. app/schemas/book.py:
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class BookCreate(BaseModel):
    title: str
    grade: int = Field(..., ge=1, le=12)
    publisher: str = ""        # "CTST" | "Kết Nối" | "Cánh Diều" | ""
    academic_year: str = ""

class BookDB(BookCreate):
    id: str = Field(alias="_id")
    status: str = "pending"    # pending|processing|done|error
    progress: int = 0          # 0-100
    current_phase: str = ""    # "ingesting"|"analyzing"|"parsing"|"saving"
    total_pages: int = 0
    processed_pages: int = 0
    file_path: str = ""
    error_message: str = ""
    created_at: datetime
    updated_at: datetime
    gemini_calls: int = 0      # đếm số Gemini API calls
    mathpix_calls: int = 0     # đếm số Mathpix API calls

2. app/models/chapter.py, lesson.py, content.py — theo cấu trúc tương ứng.

3. lesson_contents collection — 1 document = 1 content block:
{
    "_id": "...",
    "lesson_id": "...",
    "order": 1,
    "type": "text"|"formula"|"image"|"exercise"|"table"|"definition"|"note",
    "content": "...",          # text nếu có
    "latex": "...",            # nếu formula
    "image_url": "...",        # nếu image
    "thumbnail_url": "...",
    "caption": "...",
    "exercise_type": "...",    # vi_du|bai_tap|luyen_tap|hoat_dong|kham_pha|van_dung
    "exercise_num": 1,
    "confidence": 0.92,        # từ Gemini
    "source": "gemini"|"mathpix"  # ai đã extract content này
}

4. Repositories — dùng Motor async (tương tự chat_repository.py hiện tại):

class BookRepository:
    def __init__(self):
        self.collection = mongo_db["books"]  # from app.core.mongo import mongo_db
    
    async def create(self, book: BookCreate, file_path: str) -> str
    async def get_by_id(self, book_id: str) -> BookDB | None
    async def list_all(self, grade: int = None) -> list[BookDB]
    async def update_status(self, book_id, status, progress=None, phase=None, error="")
    async def increment_api_calls(self, book_id, gemini=0, mathpix=0)
    async def delete(self, book_id: str) -> bool

# Khởi tạo singleton ở cuối file (tương tự chat_repository = ChatRepository())
book_repository = BookRepository()

5. Indexes — thêm vào startup event trong app/main.py (KHÔNG tạo file mới):
    from app.core.mongo import mongo_db
    await mongo_db["books"].create_index("grade")
    await mongo_db["books"].create_index("status")
    await mongo_db["chapters"].create_index([("book_id", 1), ("chapter_index", 1)], unique=True)
    await mongo_db["lessons"].create_index([("chapter_id", 1), ("lesson_index", 1)], unique=True)
    await mongo_db["lesson_contents"].create_index([("lesson_id", 1), ("order", 1)])
    await mongo_db["lesson_contents"].create_index([("content", "text"), ("latex", "text")])

YÊU CẦU:
- Dùng Motor (async), KHÔNG dùng sync pymongo
- ObjectId ↔ str conversion: str(doc["_id"]) (tương tự chat_repository.py)
- Timestamps UTC
- Không expose ObjectId raw trong API response

SAU KHI XONG, hãy:
✅ CHECKLIST:
- [ ] Models valid với Pydantic v2
- [ ] ObjectId convert đúng sang str
- [ ] BookDB có progress + current_phase + gemini_calls + mathpix_calls
- [ ] Repositories đủ CRUD
- [ ] Text index cho search tạo thành công
- [ ] Unique indexes tránh duplicate chapter/lesson
- [ ] Timestamps UTC

⚠️ BÁO LỖI NẾU:
- Pydantic v2 validator syntax khác v1
- Motor cursor không serialize được

🧪 TEST:
  async def test_book_crud():
      from app.repositories.book_repository import book_repository
      book_id = await book_repository.create(BookCreate(title="Toán 8", grade=8), "path/to/file.pdf")
      book = await book_repository.get_by_id(book_id)
      assert book.grade == 8
      assert book.status == "pending"
      await book_repository.update_status(book_id, "processing", progress=10, phase="ingesting")
      book = await book_repository.get_by_id(book_id)
      assert book.progress == 10
      await book_repository.delete(book_id)

⏸️ PENDING: Dừng tại đây, chờ tôi confirm "OK Phase 6".
```

---

## ⚡ PHASE 7 — PROCESSING PIPELINE

### 📋 Prompt cho AI:

```
Tiếp tục dự án SGK Toán. Phase 6 xong (MongoDB).

Implement PHASE 7: Processing Pipeline — kết nối tất cả services.

File: app/services/processing_pipeline.py

FLOW HOÀN CHỈNH:
PDF → Pages → [Gemini per page] → [Mathpix fallback cho formula khó] → 
[Image crop] → [Structure parse] → MongoDB

YÊU CẦU:

1. Class ProcessingPipeline:

class ProcessingPipeline:
    def __init__(self, book_id: str, pdf_path: str):
        self.book_id = book_id
        self.pdf_path = pdf_path
        self.pdf_parser = PDFParser()
        self.gemini = GeminiOCRService()
        self.mathpix = MathpixService()
        self.image_extractor = ImageExtractor()
        self.structure_parser = StructureParser()
        # Dùng singleton repositories (không nhận db qua constructor)
        self.book_repo = book_repository      # from app.repositories.book_repository
        self.gemini_call_count = 0
        self.mathpix_call_count = 0
    
    async def run(self) -> None: ...

2. PIPELINE STEPS:

async def run(self):
    try:
        # PHASE 1: Ingest
        await self._update("ingesting", 5)
        pages_info = self.pdf_parser.render_pages(self.pdf_path, ...)
        total = len(pages_info)
        
        # PHASE 2: Gemini OCR per page
        await self._update("analyzing", 10)
        page_analyses = []
        for i, page_info in enumerate(pages_info):
            analysis = await self.gemini.analyze_page(page_info.image_path, page_info.page_num)
            self.gemini_call_count += 1
            
            # PHASE 3: Mathpix fallback cho formula needs_mathpix=True
            analysis = await self._apply_mathpix_fallback(analysis, page_info.image_path)
            
            # PHASE 4: Extract images
            analysis = await self._extract_images(analysis, page_info)
            
            page_analyses.append(analysis)
            
            # Update progress (10% → 80%)
            progress = 10 + int((i + 1) / total * 70)
            await self._update("analyzing", progress, f"Page {i+1}/{total}")
        
        # PHASE 5: Structure parse
        await self._update("parsing", 82)
        book_structure = self.structure_parser.parse_book(page_analyses, ...)
        
        # PHASE 6: Save to MongoDB
        await self._update("saving", 88)
        await self._save_to_db(book_structure)
        
        # Done
        await self._update_done(self.gemini_call_count, self.mathpix_call_count)
        
    except Exception as e:
        await self.book_repo.update_status(self.book_id, "error", error=str(e))
        raise

3. _apply_mathpix_fallback(analysis, page_image_path):
   - Với mỗi block trong analysis.blocks:
     + Nếu block.type == "formula" AND (block.needs_mathpix OR block.confidence < 0.6):
       - Cần bbox pixel: convert từ image size
       - Gọi mathpix.extract_formula()
       - Nếu mathpix.success AND mathpix.confidence > block.confidence:
           block.latex = mathpix.latex
           block.source = "mathpix"
           self.mathpix_call_count += 1
   - Return analysis (đã update)

4. _extract_images(analysis, page_info):
   - Với mỗi block type == "image":
     + Gọi image_extractor.extract_and_store()
     + Gắn block.image_url, block.thumbnail_url từ result
   - Return analysis

5. _update(phase, progress, message=""):
   - await self.book_repo.update_status(book_id, "processing", progress, phase)

6. _update_done(gemini_calls, mathpix_calls):
   - Update status = "done", progress = 100
   - Update gemini_calls + mathpix_calls count
   - Cleanup temp page images (tùy config KEEP_PAGE_IMAGES)

7. Hàm standalone để chạy trong BackgroundTasks:
   async def run_pipeline(book_id: str, pdf_path: str):
       pipeline = ProcessingPipeline(book_id, pdf_path)
       await pipeline.run()

SAU KHI XONG, hãy:
✅ CHECKLIST:
- [ ] Pipeline chạy end-to-end không crash
- [ ] Progress update đúng: 5% → 10% → (10-80%) per page → 82% → 88% → 100%
- [ ] current_phase update đúng tên
- [ ] Mathpix chỉ gọi khi needs_mathpix=True hoặc confidence < 0.6
- [ ] Image extraction gán đúng URL vào block
- [ ] gemini_calls và mathpix_calls được đếm đúng
- [ ] Error → status="error", message rõ ràng
- [ ] Temp files cleanup sau khi xong

⚠️ BÁO LỖI NẾU:
- Gemini rate limit 429 trong vòng lặp → cần đợi
- Memory tăng vô hạn (mỗi PageAnalysis giữ raw_response lớn)
- Background task bị kill trước khi xong

🧪 TEST (integration test):
  # Chạy với PDF test nhỏ 5 trang
  import asyncio
  from app.repositories.book_repository import book_repository
  from app.repositories.chapter_repository import chapter_repository
  async def test_pipeline():
      pipeline = ProcessingPipeline("test_id", "tests/fixtures/test_book.pdf")
      await pipeline.run()
      book = await book_repository.get_by_id("test_id")
      assert book.status == "done"
      assert book.progress == 100
      assert book.gemini_calls > 0
      chapters = await chapter_repository.list_by_book("test_id")
      assert len(chapters) >= 1

⏸️ PENDING: Dừng tại đây, chờ tôi confirm "OK Phase 7".
```

---

## 🌐 PHASE 8 — FASTAPI ENDPOINTS

### 📋 Prompt cho AI:

```
Tiếp tục dự án SGK Toán. Phase 7 xong (Pipeline).

Implement PHASE 8: FastAPI Endpoints hoàn chỉnh.

Convention dự án hiện tại:
- Routers nằm trong app/controllers/ (APIRouter, KHÔNG dùng app/api/)
- Đăng ký router trong app/main.py với app.include_router(..., prefix=API_PREFIX)
- API prefix: /api/v1 (lấy từ settings.api_prefix)
- Response helper: from app.utils.response import success_response
- Import config: from app.core.config import settings

Files: app/controllers/book_controller.py, chapter_controller.py, lesson_controller.py, search_controller.py

ENDPOINTS:

### Books (app/controllers/book_controller.py):
POST   /api/v1/books/upload
  - Accept: multipart/form-data (file PDF + grade: int + publisher: str + title: str)
  - Validate: chỉ .pdf, max 50MB
  - Lưu file → /data/books/{book_id}/original.pdf
  - Tạo BookDB trong MongoDB status="pending"
  - Trigger BackgroundTasks → run_pipeline(book_id, pdf_path)  # không truyền db
  - Return: {"book_id": "...", "status": "pending"}

GET    /api/v1/books/
  - Query params: grade (optional), status (optional)
  - Return: list[BookSummary]

GET    /api/v1/books/{book_id}
  - Return: BookDetail (gồm cả stats: gemini_calls, mathpix_calls)

GET    /api/v1/books/{book_id}/status
  - Return: {"status": "...", "progress": 45, "current_phase": "analyzing", 
             "processed_pages": 12, "total_pages": 180}
  - Dùng để frontend polling

DELETE /api/v1/books/{book_id}
  - Xoá book + chapters + lessons + contents + storage files

### Structure Query:
GET /api/v1/books/{book_id}/chapters
GET /api/v1/chapters/{chapter_id}
GET /api/v1/chapters/{chapter_id}/lessons
GET /api/v1/lessons/{lesson_id}
GET /api/v1/lessons/{lesson_id}/content

### Export:
GET /api/v1/books/{book_id}/export/json    → full tree JSON
GET /api/v1/books/{book_id}/export/md      → Markdown
GET /api/v1/books/{book_id}/export/chunks  → RAG chunks

### Search:
GET /api/v1/search?q={keyword}&grade={optional}&chapter_id={optional}
  - Dùng MongoDB $text index
  - Return: list kết quả + metadata (tên bài, chương)

YÊU CẦU RESPONSE SCHEMAS:
- Tất cả endpoints có Pydantic response model
- Error responses chuẩn: {"detail": "...", "code": "..."}
- Timestamps dạng ISO 8601

EXPORT MARKDOWN FORMAT:
# [Lớp 8] Toán 8 — CTST

## Chương I: Số hữu tỉ

### Bài 1: Số hữu tỉ

Số hữu tỉ là số có thể viết dưới dạng $\frac{a}{b}$...

**Ví dụ 1:** Chứng minh rằng...

$$\frac{1}{2} + \frac{1}{3} = \frac{5}{6}$$

![Hình 1.3](http://localhost:8000/static/images/...)

**Bài tập:**

EXPORT CHUNKS FORMAT (cho RAG):
[
  {
    "chunk_id": "book1_ch1_l1_c003",
    "text": "[Lớp 8] [Chương I] [Bài 1] Số hữu tỉ là số viết được...",
    "metadata": {"grade": 8, "chapter": "Chương I", "lesson": "Bài 1", "type": "text"}
  }
]

SAU KHI XONG, hãy:
✅ CHECKLIST:
- [ ] POST /upload nhận file, trigger background task, trả về book_id
- [ ] GET /status trả về progress real-time
- [ ] GET /chapters list đúng theo book_id
- [ ] GET /lessons/content trả về đủ blocks (text, formula, image, exercise)
- [ ] Export JSON đúng format spec ban đầu
- [ ] Export Markdown format đẹp với formula LaTeX
- [ ] Export chunks có metadata đầy đủ
- [ ] Search tìm được text và latex
- [ ] Error 404 khi book_id không tồn tại
- [ ] Static files serve ảnh đúng

⚠️ BÁO LỖI NẾU:
- Upload file không lưu được
- Background task không trigger
- Export lớn timeout
- Search trả về kết quả sai

🧪 TEST (curl):
  # Upload
  BOOK_ID=$(curl -s -X POST http://localhost:8000/api/v1/books/upload \
    -F "file=@toan8.pdf" -F "grade=8" -F "publisher=CTST" -F "title=Toán 8" \
    | python -c "import sys,json; print(json.load(sys.stdin)['book_id'])")
  
  echo "Book: $BOOK_ID"
  
  # Poll status
  while true; do
    RESP=$(curl -s http://localhost:8000/api/v1/books/$BOOK_ID/status)
    echo $RESP | python -c "import sys,json; d=json.load(sys.stdin); print(f\"[{d['current_phase']}] {d['progress']}%\")"
    STATUS=$(echo $RESP | python -c "import sys,json; print(json.load(sys.stdin)['status'])")
    if [ "$STATUS" = "done" ] || [ "$STATUS" = "error" ]; then break; fi
    sleep 5
  done
  
  # Query
  curl http://localhost:8000/api/v1/books/$BOOK_ID/chapters | python -m json.tool

⏸️ PENDING: Dừng tại đây, chờ tôi confirm "OK Phase 8".
```

---

## 🧪 PHASE 9 — INTEGRATION TEST END-TO-END

### 📋 Prompt cho AI:

```
Tiếp tục dự án SGK Toán. Phase 8 xong (FastAPI Endpoints).

Implement PHASE 9: Tests toàn diện.

Files: tests/conftest.py + tests/test_e2e.py + tests/fixtures/

YÊU CẦU:

1. tests/conftest.py:
   - Async client dùng httpx.AsyncClient
   - Test DB riêng: đổi MONGO_DB=sgk_toan_test trong env (cleanup sau mỗi test)
   - Mock GeminiOCRService để test không gọi API thật
   - Mock MathpixService tương tự
   - Lưu ý: mongo_db singleton trong app/core/mongo.py được khởi tạo khi import
     → dùng monkeypatch hoặc override settings trước khi import app

2. tests/fixtures/ — tạo PDF test:
   Tạo file test_book.pdf đơn giản bằng reportlab (hoặc plain PDF với text):
   - Trang 1: "CHƯƠNG I. SỐ HỮU TỈ"
   - Trang 2: "Bài 1. Số hữu tỉ" + text + 1 công thức đơn giản
   - Trang 3: "Ví dụ 1" + bài giải + 1 hình

3. Mock GeminiOCRService:
   - Trả về PageAnalysis cố định cho từng trang test
   - Không gọi API thật

4. Test scenarios:

SCENARIO 1: Upload + Process (dùng mock Gemini)
  - Upload test PDF
  - Wait for status = "done" (timeout 30s)
  - Assert: có chapter, có lesson, có content blocks

SCENARIO 2: Reject invalid files
  - Upload .txt → expect 422
  - Upload PDF > 50MB → expect 413

SCENARIO 3: Query structure
  - GET /chapters → assert count đúng
  - GET /lessons/{id}/content → assert có formula block với latex
  - GET /lessons/{id}/content → assert có image block với url

SCENARIO 4: Export
  - GET /export/json → validate JSON schema đúng format
  - GET /export/md → assert có "##", "###", "$...$" trong Markdown
  - GET /export/chunks → assert chunks có metadata

SCENARIO 5: Search
  - GET /search?q=số hữu tỉ → assert kết quả không rỗng

SCENARIO 6: Delete
  - DELETE /books/{id} → assert 200
  - GET /books/{id} → assert 404

5. Performance test:
   - Đo thời gian process với mock (phải < 5s)
   - Log: "Phase timing: ingest=Xs, gemini=Xs, structure=Xs, save=Xs"

SAU KHI XONG, hãy:
✅ CHECKLIST:
- [ ] conftest.py setup test DB + mock services
- [ ] test_book.pdf fixture tạo được
- [ ] SCENARIO 1: upload + process (mock) pass
- [ ] SCENARIO 2: validation lỗi đúng status code
- [ ] SCENARIO 3: query structure trả về đúng
- [ ] SCENARIO 4: export đúng format
- [ ] SCENARIO 5: search có kết quả
- [ ] SCENARIO 6: delete + 404 confirm
- [ ] Test cleanup: không dirty data giữa các test

⚠️ BÁO LỖI NẾU:
- Mock không intercept được Gemini calls
- Test DB bị ảnh hưởng prod DB
- Async test không chạy được (event loop conflict)

🧪 CHẠY:
  pytest tests/test_e2e.py -v --timeout=60 -s

⏸️ PENDING: Dừng tại đây, chờ tôi confirm "OK Phase 9".
```

---

## 📤 PHASE 10 — HOÀN THIỆN & DOCS

### 📋 Prompt cho AI:

```
Tiếp tục dự án SGK Toán. Phase 9 xong (Tests).

PHASE 10: Hoàn thiện project — README + Docker + minor fixes.

YÊU CẦU:

1. README.md hoàn chỉnh:
   - Mô tả project, stack
   - Prerequisites: Python 3.11+, MongoDB, Gemini API key
   - Setup steps chi tiết
   - Cách lấy Gemini API key (Google AI Studio — free)
   - Cách lấy Mathpix key (optional)
   - API endpoints table
   - Example curl commands
   - Accuracy notes: Gemini ~85-92%, Mathpix formula ~95%+

2. docker-compose.yml hoàn chỉnh:
   services:
     mongo: MongoDB 7
     app: FastAPI app (Dockerfile)
   volumes, env_file

3. Dockerfile cho app:
   FROM python:3.11-slim
   Cài requirements, copy code, uvicorn

4. Script setup nhanh:
   scripts/setup.sh:
   - Tạo .env từ .env.example
   - Tạo thư mục storage/ data/
   - pip install requirements
   - docker-compose up -d mongo

5. Validation cuối — kiểm tra toàn bộ:
   - Chạy pytest → tất cả pass
   - Chạy với PDF thật nhỏ (10 trang) → check output MongoDB
   - Export JSON → validate schema
   - Export Markdown → render thử

✅ CHECKLIST CUỐI CÙNG:
- [ ] README đủ để người khác setup không cần hỏi
- [ ] Docker compose chạy được
- [ ] pytest: 0 failures
- [ ] Upload 1 PDF thật → query API → data đúng
- [ ] Export JSON đúng format spec
- [ ] Export Markdown render đẹp với công thức
- [ ] Search hoạt động
- [ ] Static images serve đúng

🎉 DỰ ÁN HOÀN THÀNH KHI tất cả checklist trên pass.
```

---

## 📊 TỔNG KẾT KỸ THUẬT

### Stack cuối cùng

| Layer | Tool | Vai trò |
|-------|------|---------|
| PDF Ingestion | PyMuPDF | Render trang → JPEG 150 DPI |
| OCR chính | Gemini Flash Vision | Text + layout + formula + detect image regions |
| Formula fallback | Mathpix v3/text | Khi Gemini fail với công thức phức tạp |
| Image storage | Local JPEG | Crop từ bbox, serve qua FastAPI static |
| Structure | Rule Engine (regex) | Detect Chương/Bài từ Gemini labels |
| Database | MongoDB + Motor | Async, text index cho search |
| API | FastAPI | REST endpoints + BackgroundTasks |

### Mathpix LaTeX Coverage cho SGK Toán
Mathpix hỗ trợ đầy đủ tất cả ký hiệu cần thiết:
- **Đại số:** `\frac`, `\sqrt`, `^`, `_`, `\pm`, `\cdot`, `\times`, `\div`
- **Lượng giác:** `\sin`, `\cos`, `\tan`, `\cot`, `\pi`, `\theta`, `\alpha`..`\omega`  
- **Giải tích:** `\int`, `\sum`, `\prod`, `\lim`, `\partial`, `\infty`
- **Hình học:** `\angle`, `\perp`, `\parallel`, `\triangle`, `\overline`, `\vec`
- **Tập hợp:** `\in`, `\notin`, `\subset`, `\cup`, `\cap`, `\emptyset`, `\mathbb{R}`
- **Logic:** `\forall`, `\exists`, `\Rightarrow`, `\Leftrightarrow`, `\therefore`
- **Ma trận:** `\begin{matrix}`, `\begin{pmatrix}`, `\begin{vmatrix}`

### Chi phí ước tính (5 cuốn SGK ~1000 trang)

| Dịch vụ | Free limit | Chi phí nếu vượt |
|---------|-----------|-----------------|
| Gemini Flash | 250 req/ngày (chia nhiều ngày) | $0.075/1M tokens |
| Mathpix (optional) | $29 credit sau $20 setup | $0.002/ảnh |
| MongoDB | Local / MongoDB Atlas free 512MB | $0 |
| Storage | Local disk | $0 |
| **Tổng** | **~$0–25 cho cả dự án** | |

### Tips tối ưu chi phí Gemini
- Process tối đa 200 trang/ngày (chia 2 ngày cho 1 cuốn SGK)
- Compress JPEG < 100KB/trang trước khi gửi (giảm token cost)
- Cache response: nếu cùng page_hash → không gọi lại Gemini
- Chỉ gọi Mathpix khi thực sự cần (confidence < 0.6)
```