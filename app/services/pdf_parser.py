# PDF ingestion service — Phase 1
import logging
import os
from dataclasses import dataclass

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class PageInfo:
    page_num: int
    image_path: str
    file_size_kb: float
    width: int
    height: int
    is_grayscale: bool


def validate_pdf(file_path: str) -> bool:
    """Return True if file_path is a valid PDF with at least one page."""
    try:
        with fitz.open(file_path) as doc:
            return doc.page_count > 0
    except Exception:
        return False


def render_pages(pdf_path: str, output_dir: str) -> list[PageInfo]:
    """
    Render every page of *pdf_path* to JPEG and return a list of PageInfo.

    Images are saved as:
        <output_dir>/pages/page_001.jpg, page_002.jpg, ...

    Strategy:
    - 150 DPI (sufficient for OCR per Mathpix best-practices)
    - JPEG quality=85
    - Convert to grayscale when the page contains no significant colour
    """
    pages_dir = os.path.join(output_dir, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    results: list[PageInfo] = []

    with fitz.open(pdf_path) as doc:
        mat = fitz.Matrix(150 / 72, 150 / 72)  # 72 dpi is fitz default

        for page in doc:
            page_num = page.number + 1  # 1-based

            # Render to pixmap (RGB)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            pil_img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            # Decide grayscale: if all pixels are near-neutral, convert
            is_grayscale = _is_effectively_grayscale(pil_img)
            if is_grayscale:
                pil_img = pil_img.convert("L").convert("RGB")  # keep 3-ch JPEG

            filename = f"page_{page_num:03d}.jpg"
            image_path = os.path.join(pages_dir, filename)

            pil_img.save(image_path, format="JPEG", quality=85, optimize=True)

            size_kb = os.path.getsize(image_path) / 1024
            if size_kb > 200:
                logger.warning(
                    "Page %d: JPEG %.1f KB > 200 KB. "
                    "Consider reducing DPI or quality.",
                    page_num,
                    size_kb,
                )

            results.append(
                PageInfo(
                    page_num=page_num,
                    image_path=image_path,
                    file_size_kb=round(size_kb, 2),
                    width=pil_img.width,
                    height=pil_img.height,
                    is_grayscale=is_grayscale,
                )
            )

    return results


def extract_pdf_metadata(pdf_path: str) -> dict:
    """Return basic metadata for the PDF file."""
    with fitz.open(pdf_path) as doc:
        meta = doc.metadata or {}
        return {
            "title": meta.get("title", ""),
            "author": meta.get("author", ""),
            "num_pages": doc.page_count,
            "file_size_mb": round(os.path.getsize(pdf_path) / (1024 * 1024), 3),
        }


def check_image_size(image_path: str) -> dict:
    """
    Return size info for *image_path*.

    Warns when the file exceeds 100 KB (Mathpix/Gemini latency threshold).
    """
    size_kb = os.path.getsize(image_path) / 1024
    needs_compression = size_kb > 100
    if needs_compression:
        logger.warning(
            "Image %s is %.1f KB (> 100 KB). "
            "This may increase Mathpix/Gemini latency.",
            image_path,
            size_kb,
        )
    return {
        "path": image_path,
        "size_kb": round(size_kb, 2),
        "needs_compression": needs_compression,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_effectively_grayscale(img: Image.Image, threshold: float = 10.0) -> bool:
    """
    Return True when the average per-pixel colour saturation is below
    *threshold* (0-255 scale), meaning the page has no meaningful colour.
    """
    try:
        import numpy as np  # optional fast path

        arr = np.array(img, dtype=float)
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        # max channel deviation from mean as a proxy for saturation
        mean = (r + g + b) / 3
        deviation = (
            np.abs(r - mean) + np.abs(g - mean) + np.abs(b - mean)
        ).mean()
        return float(deviation) < threshold
    except ImportError:
        # Fallback: convert to HSV via PIL and check saturation channel
        hsv = img.convert("HSV")
        s_channel = list(hsv.getdata(band=1))
        avg_saturation = sum(s_channel) / len(s_channel)
        return avg_saturation < threshold

