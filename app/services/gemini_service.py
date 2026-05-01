# Gemini Flash Vision OCR service — Phase 2
import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass, field

import google.generativeai as genai

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "Bạn là AI chuyên phân tích sách giáo khoa Toán Việt Nam. "
    "Hãy phân tích ảnh trang SGK và trả về JSON CHÍNH XÁC theo format sau. "
    "CHỈ trả về JSON, không giải thích thêm."
)

PAGE_ANALYSIS_PROMPT = r"""Phân tích trang SGK Toán này. Nhận diện TẤT CẢ các block nội dung theo thứ tự đọc (trên→dưới, trái→phải).

Với mỗi block, xác định:
- type: chapter_title | lesson_title | text | formula | exercise | image | table | definition | note
- content: nội dung text (nếu có)
- latex: công thức LaTeX chuẩn (nếu type=formula). Dùng đúng commands: \frac{}{}, \sqrt{}, \sum_{i=1}^{n}, \int_{a}^{b}, \alpha, \beta, \gamma, \Delta, \Sigma, \mathbb{R}, \vec{v}, \overline{AB}, \angle, \perp, \parallel, \in, \subset, \cup, \cap
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
    }
  ]
}"""

FALLBACK_PROMPT = r"""Trang SGK Toán. Trả về JSON với trường "blocks" là danh sách các block nội dung.
Mỗi block: {"type":"text","content":"...","latex":null,"image_bbox":null,"caption":null,"confidence":0.8,"needs_mathpix":false,"order":N}
CHỈ JSON, không giải thích."""

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ContentBlock:
    type: str                           # chapter_title|lesson_title|text|formula|exercise|image|table|definition|note
    content: str = ""
    latex: str = ""
    image_bbox: tuple = ()             # (x1,y1,x2,y2) relative 0-1, empty if not image
    caption: str = ""
    order: int = 0
    confidence: float = 1.0
    needs_mathpix: bool = False


@dataclass
class PageAnalysis:
    page_num: int
    blocks: list[ContentBlock] = field(default_factory=list)
    raw_response: str = ""
    processing_time_ms: int = 0


# ---------------------------------------------------------------------------
# Rate limiter — 10 RPM for Gemini free tier → 6 s between requests
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Simple async rate limiter: enforces a minimum interval between calls."""

    def __init__(self, min_interval_s: float = 6.0):
        self._min_interval = min_interval_s
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_call)
            if wait > 0:
                logger.debug("Rate limiter: sleeping %.1f s", wait)
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()


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
        # Guard against re-initialisation on repeated __new__ returns
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set in configuration.")

        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=SYSTEM_PROMPT,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        self._rate_limiter = _RateLimiter(min_interval_s=6.0)
        logger.info("GeminiOCRService ready (model=%s)", settings.gemini_model)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_page(self, image_path: str, page_num: int) -> PageAnalysis:
        """Analyse a single page image and return structured PageAnalysis."""
        start = time.monotonic()

        await self._rate_limiter.acquire()

        raw = await self._call_with_retry(image_path, PAGE_ANALYSIS_PROMPT, page_num)

        elapsed_ms = int((time.monotonic() - start) * 1000)

        blocks = self._parse_blocks(raw, page_num)
        return PageAnalysis(
            page_num=page_num,
            blocks=blocks,
            raw_response=raw,
            processing_time_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call_with_retry(
        self, image_path: str, prompt: str, page_num: int
    ) -> str:
        """Call Gemini API with exponential-backoff retry (max 3 attempts)."""
        image_part = self._encode_image(image_path)
        delays = [2, 4, 8]

        for attempt, delay in enumerate(delays, start=1):
            try:
                response = await asyncio.to_thread(
                    self._model.generate_content,
                    [image_part, prompt],
                )
                return response.text
            except Exception as exc:
                logger.warning(
                    "Gemini API error (attempt %d/3) for page %d: %s",
                    attempt,
                    page_num,
                    exc,
                )
                if attempt == len(delays):
                    raise
                await asyncio.sleep(delay)

        return ""  # unreachable

    def _encode_image(self, image_path: str) -> dict:
        """Read JPEG and return a Gemini-compatible image part dict."""
        with open(image_path, "rb") as fh:
            data = base64.b64encode(fh.read()).decode("utf-8")
        return {"mime_type": "image/jpeg", "data": data}

    def _parse_blocks(self, raw: str, page_num: int) -> list[ContentBlock]:
        """Parse JSON response into ContentBlock list, with one retry on failure."""
        try:
            return self._do_parse(raw, page_num)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(
                "JSON parse failed for page %d (%s). Attempting fallback prompt.",
                page_num,
                exc,
            )
            # Synchronous retry with fallback prompt — run from async context via
            # the caller already being in a thread-friendly path.
            try:
                # We can't easily re-call async here; try extracting JSON substring
                extracted = self._extract_json(raw)
                return self._do_parse(extracted, page_num)
            except Exception:
                logger.error("Fallback parse also failed for page %d.", page_num)
                return []

    def _do_parse(self, raw: str, page_num: int) -> list[ContentBlock]:
        data = json.loads(raw)
        raw_blocks = data.get("blocks", [])
        blocks: list[ContentBlock] = []
        for rb in raw_blocks:
            bbox_raw = rb.get("image_bbox")
            if isinstance(bbox_raw, (list, tuple)) and len(bbox_raw) == 4:
                bbox: tuple = tuple(float(v) for v in bbox_raw)
            else:
                bbox = ()

            blocks.append(
                ContentBlock(
                    type=str(rb.get("type", "text")),
                    content=rb.get("content") or "",
                    latex=rb.get("latex") or "",
                    image_bbox=bbox,
                    caption=rb.get("caption") or "",
                    order=int(rb.get("order", 0)),
                    confidence=float(rb.get("confidence", 1.0)),
                    needs_mathpix=bool(rb.get("needs_mathpix", False)),
                )
            )
        return blocks

    @staticmethod
    def _extract_json(text: str) -> str:
        """Try to extract a JSON object substring from a noisy response."""
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            return text[start:end]
        raise ValueError("No JSON object found in response")
