# Gemini Flash Vision OCR service — Phase 2 (revised)
import asyncio
import json
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Literal, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic response schemas — used as Gemini structured output schemas
# ---------------------------------------------------------------------------

BlockType = Literal[
    "chapter_title",
    "lesson_title",
    "text",
    "formula",
    "exercise",
    "image",
    "table",
    "definition",
    "note",
    "toc",
]


class GeminiContentBlock(BaseModel):
    """Schema Gemini must follow for every block on a page."""

    type: BlockType
    content: str = ""
    latex: str = ""
    # Relative coordinates [x1, y1, x2, y2] in [0, 1].
    # For type="image" this is the figure bbox.
    # For type="formula" set this only if the formula is complex enough that
    # a downstream OCR (Mathpix) needs to re-extract — otherwise leave null.
    image_bbox: Optional[list[float]] = None
    caption: str = ""
    order: int = 0
    confidence: float = 1.0
    needs_mathpix: bool = False
    # NEW: marks blocks whose content continues from the previous page (the
    # block's content was split mid-paragraph or mid-exercise).
    is_continuation: bool = False
    # NEW: distinguishes inline math ($x^2$) from display math ($$\frac{a}{b}$$).
    is_display_math: bool = False
    # NEW: column index for two-column SGK layouts (1=left, 2=right). 1 by default.
    column: int = 1


class GeminiPageResponse(BaseModel):
    page_num: int = 0
    blocks: list[GeminiContentBlock] = Field(default_factory=list)


class GeminiTocEntry(BaseModel):
    type: Literal["chapter", "lesson", "section"]
    chapter_index: int = 0
    chapter_roman: str = ""
    lesson_index: int = 0
    title: str = ""
    page_start: int = 0


class GeminiTocResponse(BaseModel):
    # NEW: the printed page number visible in the footer of THIS toc page.
    # Combined with the PDF index, this lets us compute the PDF↔SGK offset.
    toc_printed_page_num: int = 0
    entries: list[GeminiTocEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "Bạn là AI chuyên phân tích sách giáo khoa Toán Việt Nam. "
    "Phân tích ảnh trang SGK và trả về JSON đúng schema được cấu hình. "
    "Không thêm văn bản giải thích nào ngoài JSON."
)

PAGE_ANALYSIS_PROMPT = r"""Phân tích trang SGK Toán này và trả về JSON đúng schema.

Quy tắc tổng quát:
- Liệt kê TẤT CẢ block nội dung theo thứ tự đọc (trên→dưới, trái→phải; với layout 2 cột thì đọc hết cột trái trước, rồi cột phải).
- KHÔNG kèm số trang vào content (ví dụ "Bài 1. Tính đơn điệu", KHÔNG phải "Bài 1. Tính đơn điệu  5").

Trang MỤC LỤC:
- Nếu trang là MỤC LỤC (có tiêu đề "MỤC LỤC" hoặc liệt kê chương/bài kèm số trang), trả về đúng 1 block:
  {"type": "toc", "content": "MỤC LỤC", "order": 1, "confidence": 1.0, "is_continuation": false, "is_display_math": false, "column": 1}

Cách phân loại block (cho trang KHÔNG phải mục lục):
- chapter_title: "CHƯƠNG I", "Chương 1.", text rất to/đậm mở đầu chương.
- lesson_title:  "Bài 1.", "Bài 2:", "§1.", "Bài tập cuối chương N".
- exercise:      bắt đầu bằng "Luyện tập", "Ví dụ N", "Hoạt động N", "Khám phá", "Vận dụng", "Thử thách".
- definition:    "Định nghĩa", "Tính chất", "Định lý", "Hệ quả" (thường có viền/nền màu).
- note:          "Chú ý", "Nhận xét", "Ghi nhớ".
- formula:       MỘT công thức toán độc lập (display math). Công thức ngắn nội tuyến trong câu thì gộp vào block text với latex inline.
- image:         hình minh họa (đặt image_bbox = [x1,y1,x2,y2] tọa độ tương đối 0-1).
- table:         bảng số liệu.
- text:          các đoạn nội dung khác.

LaTeX: dùng commands chuẩn — \frac{}{}, \sqrt{}, \sum_{i=1}^{n}, \int_{a}^{b}, \alpha…\omega, \mathbb{R}, \vec{v}, \overline{AB}, \angle, \perp, \parallel, \in, \subset, \cup, \cap. Escape backslash trong JSON.

Các trường mới — RẤT QUAN TRỌNG:
- is_continuation = true nếu block đầu tiên ở trên cùng trang là phần TIẾP NỐI từ trang trước (đoạn văn/định nghĩa/bài tập bị cắt giữa chừng, không bắt đầu bằng dấu đầu dòng hoặc tiêu đề mới). Mặc định false.
- is_display_math = true cho block formula nằm riêng trên một dòng (display); false nếu inline trong câu (thường thì block formula là display, set true).
- column: 1 nếu trang 1 cột hoặc block ở cột trái; 2 nếu block ở cột phải của trang 2-cột.
- image_bbox cho formula: chỉ set [x1,y1,x2,y2] khi needs_mathpix=true VÀ bạn xác định được khung công thức; ngược lại để null.

Ví dụ ngắn — trang nội dung:
{
  "page_num": 12,
  "blocks": [
    {"type":"lesson_title","content":"Bài 2. Đường tiệm cận của đồ thị hàm số","order":1,"confidence":0.97,"is_continuation":false,"is_display_math":false,"column":1},
    {"type":"text","content":"Cho hàm số y = f(x) xác định trên (a; +∞).","order":2,"confidence":0.95,"is_continuation":false,"is_display_math":false,"column":1},
    {"type":"definition","content":"Đường thẳng y = b được gọi là tiệm cận ngang...","order":3,"confidence":0.95,"is_continuation":false,"is_display_math":false,"column":1},
    {"type":"formula","latex":"\\lim_{x\\to+\\infty} f(x) = b","order":4,"confidence":0.92,"is_continuation":false,"is_display_math":true,"column":1},
    {"type":"exercise","content":"Ví dụ 1. Tìm các tiệm cận của đồ thị hàm số y = (x+1)/(x-2).","order":5,"confidence":0.96,"is_continuation":false,"is_display_math":false,"column":1}
  ]
}

Ví dụ ngắn — đầu chương:
{
  "page_num": 5,
  "blocks": [
    {"type":"chapter_title","content":"CHƯƠNG I. ỨNG DỤNG ĐẠO HÀM ĐỂ KHẢO SÁT VÀ VẼ ĐỒ THỊ HÀM SỐ","order":1,"confidence":0.99,"is_continuation":false,"is_display_math":false,"column":1},
    {"type":"text","content":"Trong chương này, chúng ta sẽ vận dụng đạo hàm để…","order":2,"confidence":0.93,"is_continuation":false,"is_display_math":false,"column":1}
  ]
}
"""


TOC_ANALYSIS_PROMPT = r"""Đây là một trang MỤC LỤC của sách giáo khoa Toán Việt Nam.

Trích xuất:
1. toc_printed_page_num: số trang in ở chân/đầu trang HIỆN TẠI (số trang theo SGK, không phải PDF). Nếu trang TOC không in số (rất hiếm), để 0.
2. entries: liệt kê TẤT CẢ mục theo thứ tự xuất hiện (trên→dưới, trái→phải; với 2 cột thì đọc hết cột trái rồi cột phải).

Mỗi entry:
- type: "chapter" (mục chương), "lesson" (mục bài học), hoặc "section" (Bài tập cuối chương / Hoạt động thực hành trải nghiệm / …).
- chapter_index: số nguyên 1-based của chương (I→1, II→2, …). Nếu là mục thuộc chương, ghi số chương đó.
- chapter_roman: số La Mã của chương ("I","II","III","IV","V","VI","VII","VIII","IX","X","XI","XII"). Rỗng nếu không có.
- lesson_index: số bài trong chương (1-based). 0 nếu là mục chương; 99 nếu là "Bài tập cuối chương".
- title: tiêu đề thuần — KHÔNG kèm số trang ở cuối dòng.
- page_start: số trang in trên SGK (số nguyên ở cuối dòng).

Quy tắc:
- Số trang nằm cuối dòng (đôi khi có dấu chấm chấm "….."). Đó là page_start.
- "Bài tập cuối chương N" → type="section", lesson_index=99.
- "Hoạt động thực hành và trải nghiệm" thường là section ở cuối sách → chapter_index = số chương cuối + 1, lesson_index = 0.
- Chỉ đọc nội dung trên ảnh, KHÔNG suy đoán.
"""


# ---------------------------------------------------------------------------
# Dataclasses (internal — independent from the Pydantic response schemas)
# ---------------------------------------------------------------------------

@dataclass
class ContentBlock:
    type: str                           # chapter_title|lesson_title|text|formula|exercise|image|table|definition|note|toc
    content: str = ""
    latex: str = ""
    image_bbox: tuple = ()             # (x1,y1,x2,y2) relative 0-1, empty if not set
    caption: str = ""
    order: int = 0
    confidence: float = 1.0
    needs_mathpix: bool = False
    source: str = "gemini"             # "gemini" | "mathpix"
    # New fields
    is_continuation: bool = False
    is_display_math: bool = False
    column: int = 1


@dataclass
class PageAnalysis:
    page_num: int
    blocks: list[ContentBlock] = field(default_factory=list)
    raw_response: str = ""
    processing_time_ms: int = 0


@dataclass
class TocEntry:
    type: str           # "chapter" | "lesson" | "section"
    chapter_index: int
    chapter_roman: str
    lesson_index: int   # 0 if chapter entry; 99 for end-of-chapter sections
    title: str
    page_start: int
    page_end: int = 0   # filled in by TocAnalysis.compute_page_ends()


@dataclass
class TocAnalysis:
    entries: list[TocEntry]
    toc_page_num: int                # PDF page index of the TOC page itself
    toc_printed_page_num: int = 0    # printed page number on the TOC page
    pdf_page_offset: int = 0         # PDF index - SGK printed index

    def compute_page_ends(self, total_pages: int) -> None:
        """Set page_end for each entry = (next entry.page_start - 1).

        Page numbers here are SGK-printed page numbers (NOT PDF indices) —
        callers should subtract pdf_page_offset before comparing with PDF
        page indices. Re-run after every entry mutation.
        """
        sorted_entries = sorted(self.entries, key=lambda e: (e.page_start, e.lesson_index))
        for i, entry in enumerate(sorted_entries):
            if i + 1 < len(sorted_entries):
                entry.page_end = max(sorted_entries[i + 1].page_start - 1, entry.page_start)
            else:
                # Last entry: cap at the last SGK page = total_pages - offset
                entry.page_end = max(total_pages - self.pdf_page_offset, entry.page_start)

    def _to_sgk_page(self, pdf_page_num: int) -> int:
        return pdf_page_num - self.pdf_page_offset

    def find_lesson(self, pdf_page_num: int) -> "TocEntry | None":
        """Return the lesson/section entry covering this PDF page index."""
        sgk_page = self._to_sgk_page(pdf_page_num)
        candidates = [
            e for e in self.entries
            if e.type in ("lesson", "section") and e.page_start <= sgk_page
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda e: e.page_start)

    def find_chapter(self, pdf_page_num: int) -> "TocEntry | None":
        """Return the chapter entry covering this PDF page index."""
        sgk_page = self._to_sgk_page(pdf_page_num)
        candidates = [
            e for e in self.entries
            if e.type == "chapter" and e.page_start <= sgk_page
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda e: e.page_start)

    def merge(self, other: "TocAnalysis") -> None:
        """Merge another TOC's entries into this one (multi-page TOC)."""
        seen = {(e.chapter_index, e.lesson_index, e.page_start) for e in self.entries}
        for e in other.entries:
            key = (e.chapter_index, e.lesson_index, e.page_start)
            if key not in seen:
                self.entries.append(e)
                seen.add(key)
        self.entries.sort(key=lambda e: (e.page_start, e.lesson_index))


# ---------------------------------------------------------------------------
# Rate limiter — token bucket for 10 RPM with bursts up to 5 in flight
# ---------------------------------------------------------------------------

class _TokenBucketRateLimiter:
    """
    Allow up to *capacity* concurrent calls within a *window* second period.

    Free tier: 10 RPM. Default config (capacity=10, window=60) lets several
    calls run in parallel as long as no more than 10 are issued in any rolling
    60-second window. Significantly faster than a strict 6 s spacing.
    """

    def __init__(self, capacity: int = 10, window_seconds: float = 60.0) -> None:
        self._capacity = capacity
        self._window = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                # Drop timestamps older than the window
                while self._timestamps and now - self._timestamps[0] > self._window:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._capacity:
                    self._timestamps.append(now)
                    return
                wait_for = self._window - (now - self._timestamps[0]) + 0.05
            logger.debug("Rate limiter: bucket full, sleeping %.2f s", wait_for)
            await asyncio.sleep(max(wait_for, 0.05))


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

_instance: "GeminiOCRService | None" = None


class GeminiOCRService:
    """Singleton wrapper around Gemini Flash Vision for SGK page analysis."""

    def __new__(cls) -> "GeminiOCRService":
        global _instance
        if _instance is None:
            _instance = super().__new__(cls)
        return _instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return

        if not settings.gemini_api_key:
            global _instance
            _instance = None
            raise ValueError("GEMINI_API_KEY is not set in configuration.")

        self._client = genai.Client(api_key=settings.gemini_api_key)
        # Two pre-built configs: one per response schema. system_instruction +
        # temperature + max_output_tokens stay the same.
        self._page_config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.2,
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema=GeminiPageResponse,
        )
        self._toc_config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.1,  # TOC needs strict parsing
            max_output_tokens=4096,
            response_mime_type="application/json",
            response_schema=GeminiTocResponse,
        )
        # Free tier: 10 RPM. Burst-capable bucket replaces the old 6-s spacing.
        self._rate_limiter = _TokenBucketRateLimiter(capacity=10, window_seconds=60.0)
        self._initialized = True
        logger.info("GeminiOCRService ready (model=%s)", settings.gemini_model)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_page(self, image_path: str, page_num: int) -> PageAnalysis:
        """Analyse a single page image and return structured PageAnalysis."""
        start = time.monotonic()

        await self._rate_limiter.acquire()
        raw = await self._call_with_retry(
            image_path, PAGE_ANALYSIS_PROMPT, page_num, self._page_config
        )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        blocks = self._parse_blocks(raw, page_num)
        return PageAnalysis(
            page_num=page_num,
            blocks=blocks,
            raw_response=raw,
            processing_time_ms=elapsed_ms,
        )

    async def analyze_toc_page(self, image_path: str, page_num: int) -> "TocAnalysis | None":
        """Analyse a single TOC page; return parsed TocAnalysis or None."""
        await self._rate_limiter.acquire()
        try:
            raw = await self._call_with_retry(
                image_path, TOC_ANALYSIS_PROMPT, page_num, self._toc_config
            )
            data = json.loads(raw) if raw else {}
            raw_entries = data.get("entries", []) or []
            entries: list[TocEntry] = []
            for re_ in raw_entries:
                try:
                    entries.append(TocEntry(
                        type=str(re_.get("type", "lesson")),
                        chapter_index=int(re_.get("chapter_index", 0)),
                        chapter_roman=str(re_.get("chapter_roman", "")),
                        lesson_index=int(re_.get("lesson_index", 0)),
                        title=str(re_.get("title", "")),
                        page_start=int(re_.get("page_start", 0)),
                    ))
                except (ValueError, TypeError) as exc:
                    logger.warning("[TOC] Skipping entry %s: %s", re_, exc)
            if not entries:
                logger.warning("[TOC] No entries extracted from page %d.", page_num)
                return None
            toc_printed_page_num = int(data.get("toc_printed_page_num", 0) or 0)
            toc = TocAnalysis(
                entries=entries,
                toc_page_num=page_num,
                toc_printed_page_num=toc_printed_page_num,
            )
            logger.info(
                "[TOC] Page %d: %d entries (toc_printed=%d).",
                page_num, len(entries), toc_printed_page_num,
            )
            return toc
        except Exception as exc:
            logger.warning("[TOC] Failed to parse TOC page %d: %s", page_num, exc)
            return None

    async def detect_toc(self, image_path: str, page_num: int) -> bool:
        """Quickly check whether a page is a TOC page.

        We piggy-back on analyze_page (one Gemini call) and inspect the result.
        Used by the pipeline to decide whether to invoke analyze_toc_page().
        """
        # Caller already has a page analysis — they invoke this only as a
        # convenience helper. Kept for symmetry; not currently called.
        analysis = await self.analyze_page(image_path, page_num)
        return any(b.type == "toc" for b in analysis.blocks)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call_with_retry(
        self,
        image_path: str,
        prompt: str,
        page_num: int,
        config: types.GenerateContentConfig,
    ) -> str:
        """Call Gemini with retry, honouring retryDelay from 429 responses."""
        image_part = self._encode_image(image_path)
        max_attempts = 3

        for attempt in range(1, max_attempts + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=settings.gemini_model,
                    contents=[image_part, prompt],
                    config=config,
                )
                return response.text or ""
            except Exception as exc:
                error_msg = str(exc)
                logger.warning(
                    "Gemini API error (attempt %d/%d) for page %d: %s",
                    attempt, max_attempts, page_num, error_msg,
                )
                if attempt == max_attempts:
                    raise

                # Honour retryDelay from 429 responses; otherwise exp-backoff.
                match = re.search(r"retryDelay.*?(\d+)s", error_msg)
                if match:
                    wait_sec = int(match.group(1)) + 5
                elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    wait_sec = 30 * attempt
                else:
                    wait_sec = (2 ** attempt) * 4

                logger.warning(
                    "Waiting %ds before retry (page %d, attempt %d/%d)...",
                    wait_sec, page_num, attempt, max_attempts,
                )
                await asyncio.sleep(wait_sec)

        return ""  # unreachable

    def _encode_image(self, image_path: str) -> types.Part:
        with open(image_path, "rb") as fh:
            data = fh.read()
        return types.Part.from_bytes(data=data, mime_type="image/jpeg")

    def _parse_blocks(self, raw: str, page_num: int) -> list[ContentBlock]:
        """Parse JSON response into ContentBlock list.

        With response_schema enforced server-side the JSON should always be
        valid — but we still guard against partial truncation or oddities.
        """
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(
                "JSON parse failed for page %d (%s); attempting substring recovery.",
                page_num, exc,
            )
            try:
                data = json.loads(self._extract_json(raw))
            except Exception:
                logger.error("Cannot recover JSON for page %d.", page_num)
                return []

        raw_blocks = data.get("blocks", []) or []
        blocks: list[ContentBlock] = []
        for rb in raw_blocks:
            bbox_raw = rb.get("image_bbox")
            if isinstance(bbox_raw, (list, tuple)) and len(bbox_raw) == 4:
                try:
                    bbox: tuple = tuple(float(v) for v in bbox_raw)
                except (TypeError, ValueError):
                    bbox = ()
            else:
                bbox = ()

            blocks.append(
                ContentBlock(
                    type=str(rb.get("type", "text")),
                    content=self._normalize_str(rb.get("content")),
                    latex=self._normalize_str(rb.get("latex")),
                    image_bbox=bbox,
                    caption=self._normalize_str(rb.get("caption")),
                    order=int(rb.get("order", 0)),
                    confidence=float(rb.get("confidence", 1.0)),
                    needs_mathpix=bool(rb.get("needs_mathpix", False)),
                    is_continuation=bool(rb.get("is_continuation", False)),
                    is_display_math=bool(rb.get("is_display_math", False)),
                    column=int(rb.get("column", 1) or 1),
                )
            )
        return blocks

    @staticmethod
    def _normalize_str(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return str(value.get("text") or value.get("content") or value.get("latex") or "")
        return str(value)

    @staticmethod
    def _extract_json(text: str) -> str:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            return text[start:end]
        raise ValueError("No JSON object found in response")
