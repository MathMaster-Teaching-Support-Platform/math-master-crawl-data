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


_RENDER_DPI = 200          # bumped from 150 — small glyphs (subscript, ∂, ∈) need it
_JPEG_QUALITY = 90
_MAX_FILE_KB = 350         # only resize if file is bigger than this
_RESIZE_SCALE = 0.9        # gentler than the old 0.8
_RESIZE_QUALITY = 85


def render_pages(
    pdf_path: str,
    output_dir: str,
    page_from: int | None = None,
    page_to: int | None = None,
) -> list[PageInfo]:
    """
    Render every page of *pdf_path* to JPEG and return a list of PageInfo.

    Images are saved as:
        <output_dir>/pages/page_001.jpg, page_002.jpg, ...

    Strategy (revised):
    - 200 DPI — needed for small math glyphs and exercise numbering.
    - JPEG quality=90, optimize=True. Color preserved (Gemini relies on
      page colour cues for definition/example boxes — never grayscale).
    - Only down-scale to 90% if the file exceeds 350 KB; never recompress
      twice (single resize pass).
    """
    pages_dir = os.path.join(output_dir, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    results: list[PageInfo] = []

    with fitz.open(pdf_path) as doc:
        mat = fitz.Matrix(_RENDER_DPI / 72, _RENDER_DPI / 72)
        # 1-based inclusive window; defaults render the whole PDF.
        first = max(1, page_from) if page_from is not None else 1
        last = min(doc.page_count, page_to) if page_to is not None else doc.page_count

        for page in doc:
            page_num = page.number + 1  # 1-based
            if page_num < first or page_num > last:
                continue

            pix = page.get_pixmap(matrix=mat, alpha=False)
            pil_img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            filename = f"page_{page_num:03d}.jpg"
            image_path = os.path.join(pages_dir, filename)

            pil_img.save(image_path, format="JPEG", quality=_JPEG_QUALITY, optimize=True)

            size_kb = os.path.getsize(image_path) / 1024
            if size_kb > _MAX_FILE_KB:
                new_w = int(pil_img.width * _RESIZE_SCALE)
                new_h = int(pil_img.height * _RESIZE_SCALE)
                pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)
                pil_img.save(image_path, format="JPEG", quality=_RESIZE_QUALITY, optimize=True)
                size_kb = os.path.getsize(image_path) / 1024
                logger.debug("Page %d resized to 90%%: %.1f KB", page_num, size_kb)

            results.append(
                PageInfo(
                    page_num=page_num,
                    image_path=image_path,
                    file_size_kb=round(size_kb, 2),
                    width=pil_img.width,
                    height=pil_img.height,
                    is_grayscale=False,
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



