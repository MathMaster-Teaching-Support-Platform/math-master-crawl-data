# Mathpix formula fallback service — Phase 3
import asyncio
import base64
import io
import logging
import re
import time
from dataclasses import dataclass

import httpx
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

_MATHPIX_ENDPOINT = "https://api.mathpix.com/v3/text"

# Simple rate limiter: 10 req/min default for free tier
_RATE_LIMIT_INTERVAL = 6.0  # seconds between requests


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class MathpixResult:
    latex: str
    text: str
    confidence: float
    success: bool


# ---------------------------------------------------------------------------
# Standalone helpers
# ---------------------------------------------------------------------------

def validate_latex(latex: str) -> bool:
    """Return True if *latex* looks like a real math expression."""
    if not latex or len(latex) < 2:
        return False
    if len(latex) > 500:
        return False
    # Must contain at least one math indicator
    math_chars = set(r"\^_{}")
    math_keywords = re.compile(
        r"\\[a-zA-Z]|[0-9]|[\^_{}]|\+|\-|\*|=|<|>"
    )
    if any(c in math_chars for c in latex):
        return True
    if math_keywords.search(latex):
        return True
    return False


def latex_to_readable(latex: str) -> str:
    """Convert simple LaTeX to a plain-text readable form."""
    if not latex:
        return ""
    result = latex
    # \frac{a}{b} → a/b
    result = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"\1/\2", result)
    # \sqrt{x} → √x
    result = re.sub(r"\\sqrt\{([^}]*)\}", r"√(\1)", result)
    # x^{n} or x^n → xⁿ (simple single-char superscript)
    superscript_map = str.maketrans("0123456789+-n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿ")
    def _sup(m):
        inner = m.group(1) or m.group(2)
        if len(inner) == 1:
            return inner.translate(superscript_map)
        return f"^({inner})"
    result = re.sub(r"\^\{([^}]+)\}|\^([^\s{])", _sup, result)
    # x_{n} → x_n (subscript — just strip braces)
    result = re.sub(r"_\{([^}]*)\}", r"_\1", result)
    # Common Greek / symbols
    replacements = [
        (r"\\alpha", "α"), (r"\\beta", "β"), (r"\\gamma", "γ"),
        (r"\\delta", "δ"), (r"\\theta", "θ"), (r"\\pi", "π"),
        (r"\\sigma", "σ"), (r"\\omega", "ω"), (r"\\infty", "∞"),
        (r"\\leq", "≤"), (r"\\geq", "≥"), (r"\\neq", "≠"),
        (r"\\approx", "≈"), (r"\\in", "∈"), (r"\\subset", "⊂"),
        (r"\\cup", "∪"), (r"\\cap", "∩"), (r"\\times", "×"),
        (r"\\cdot", "·"), (r"\\rightarrow", "→"), (r"\\Rightarrow", "⇒"),
        (r"\\Leftrightarrow", "⟺"), (r"\\sum", "Σ"), (r"\\int", "∫"),
        (r"\\partial", "∂"), (r"\\nabla", "∇"),
    ]
    for pattern, repl in replacements:
        result = re.sub(pattern, repl, result)
    # Strip remaining backslash-commands
    result = re.sub(r"\\[a-zA-Z]+\s*", "", result)
    # Strip lone braces
    result = result.replace("{", "").replace("}", "")
    return result.strip()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class MathpixService:
    """Mathpix formula fallback service (async-friendly via httpx)."""

    def __init__(self) -> None:
        self._app_id: str | None = settings.mathpix_app_id
        self._app_key: str | None = settings.mathpix_app_key
        self._last_request_time: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_enabled(self) -> bool:
        return bool(settings.mathpix_enabled and self._app_id and self._app_key)

    async def extract_formula(
        self,
        image_path: str,
        bbox: tuple,
        *,
        gemini_latex: str = "",
    ) -> MathpixResult:
        """Crop *bbox* from *image_path*, send to Mathpix, return result.

        *bbox* may be:
          - absolute pixel coords  (x1, y1, x2, y2)  — any value > 1
          - relative [0,1] coords  (x1, y1, x2, y2)  — all values ≤ 1
        """
        if not self.is_enabled():
            logger.warning("Mathpix disabled — returning Gemini latex as-is")
            return MathpixResult(
                latex=gemini_latex,
                text=latex_to_readable(gemini_latex),
                confidence=0.0,
                success=False,
            )

        try:
            img_bytes = self._preprocess(image_path, bbox)
            return await self._call_api(img_bytes)
        except Exception as exc:
            logger.error("Mathpix extract_formula failed: %s", exc)
            return MathpixResult(
                latex=gemini_latex,
                text=latex_to_readable(gemini_latex),
                confidence=0.0,
                success=False,
            )

    async def batch_extract(
        self,
        formula_blocks: list[dict],
        page_image_path: str,
    ) -> list[MathpixResult]:
        """Process multiple formula blocks from one page image.

        Each item in *formula_blocks* must have ``bbox`` (tuple) and
        optionally ``latex`` (str from Gemini).
        """
        results: list[MathpixResult] = []
        for block in formula_blocks:
            bbox = block.get("bbox") or block.get("image_bbox")
            if bbox is None:
                results.append(MathpixResult("", "", 0.0, False))
                continue
            result = await self.extract_formula(
                page_image_path,
                tuple(bbox),
                gemini_latex=block.get("latex", ""),
            )
            results.append(result)
            # Rate limiting: only pause between real API calls
            if self.is_enabled() and result.success:
                await asyncio.sleep(_RATE_LIMIT_INTERVAL)
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _preprocess(self, image_path: str, bbox: tuple) -> bytes:
        """Return JPEG bytes of the cropped, pre-processed formula region."""
        with Image.open(image_path) as img:
            img_w, img_h = img.size
            x1, y1, x2, y2 = self._resolve_bbox(bbox, img_w, img_h)

            cropped = img.crop((x1, y1, x2, y2))

        # Convert to grayscale
        cropped = cropped.convert("L")

        # Add 10 px padding on each side
        pad = 10
        padded_w = cropped.width + 2 * pad
        padded_h = cropped.height + 2 * pad
        padded = Image.new("L", (padded_w, padded_h), 255)
        padded.paste(cropped, (pad, pad))

        # Compress to JPEG, targeting < 100 KB
        buf = io.BytesIO()
        quality = 85
        while True:
            buf.seek(0)
            buf.truncate()
            padded.save(buf, format="JPEG", quality=quality)
            if buf.tell() <= 100_000 or quality <= 40:
                break
            quality -= 10

        return buf.getvalue()

    @staticmethod
    def _resolve_bbox(
        bbox: tuple, img_w: int, img_h: int
    ) -> tuple[int, int, int, int]:
        """Convert relative or absolute bbox to clamped pixel coordinates."""
        x1, y1, x2, y2 = bbox
        # Detect relative coords (all values in [0, 1])
        if all(0.0 <= v <= 1.0 for v in (x1, y1, x2, y2)):
            x1, x2 = int(x1 * img_w), int(x2 * img_w)
            y1, y2 = int(y1 * img_h), int(y2 * img_h)
        else:
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        # Clamp
        x1 = max(0, min(x1, img_w))
        x2 = max(0, min(x2, img_w))
        y1 = max(0, min(y1, img_h))
        y2 = max(0, min(y2, img_h))
        # Ensure non-degenerate
        if x2 <= x1:
            x2 = min(x1 + 1, img_w)
        if y2 <= y1:
            y2 = min(y1 + 1, img_h)
        return x1, y1, x2, y2

    async def _call_api(self, img_bytes: bytes) -> MathpixResult:
        """Send image bytes to Mathpix and return parsed result."""
        # Enforce rate limit
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < _RATE_LIMIT_INTERVAL:
            await asyncio.sleep(_RATE_LIMIT_INTERVAL - elapsed)
        self._last_request_time = time.monotonic()

        b64 = base64.b64encode(img_bytes).decode()
        payload = {
            "src": f"data:image/jpeg;base64,{b64}",
            "formats": ["latex_styled", "text"],
        }
        headers = {
            "app_id": self._app_id,
            "app_key": self._app_key,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(_MATHPIX_ENDPOINT, json=payload, headers=headers)

        if resp.status_code == 401:
            raise RuntimeError("Mathpix 401 — invalid API credentials")
        if resp.status_code == 429:
            logger.warning("Mathpix 429 rate limit — sleeping 60 s")
            await asyncio.sleep(60)
            raise RuntimeError("Mathpix rate limit hit — retry after sleep")
        resp.raise_for_status()

        data = resp.json()
        latex = data.get("latex_styled") or data.get("latex") or ""
        text = data.get("text") or latex_to_readable(latex)
        confidence = float(data.get("confidence", 0.0))

        return MathpixResult(
            latex=latex,
            text=text,
            confidence=confidence,
            success=bool(latex),
        )


# Singleton
mathpix_service = MathpixService()
