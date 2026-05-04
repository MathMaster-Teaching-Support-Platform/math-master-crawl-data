# Image extraction and storage service — Phase 4
import logging
import os
from dataclasses import dataclass, field

from PIL import Image, ImageChops, ImageOps

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class ImageResult:
    file_path: str
    url: str
    thumbnail_url: str
    width: int
    height: int
    caption: str
    page_num: int
    fig_index: int
    file_size_kb: float


# ---------------------------------------------------------------------------
# ImageExtractor
# ---------------------------------------------------------------------------

class ImageExtractor:
    """Crop image regions identified by Gemini and persist them to disk."""

    def extract_and_store(
        self,
        page_image_path: str,
        bbox_relative: list[float],
        book_id: str,
        page_num: int,
        fig_index: int,
        caption: str = "",
    ) -> ImageResult | None:
        """Crop the region defined by *bbox_relative* from *page_image_path*,
        trim whitespace, save as JPEG, and create a thumbnail.

        Returns ``None`` when the region is too small (noise).
        """
        with Image.open(page_image_path) as page_img:
            img_w, img_h = page_img.size
            bbox_px = self._bbox_relative_to_pixel(bbox_relative, img_w, img_h)

            if self._skip_if_too_small(bbox_px):
                logger.debug(
                    "Skipping figure page=%d fig=%d — bounding box too small %s",
                    page_num, fig_index, bbox_px,
                )
                return None

            cropped = page_img.crop(bbox_px)

        cropped = self._cleanup_figure(cropped)
        width, height = cropped.size

        # Build output paths
        images_dir = os.path.join(settings.storage_path, "images", book_id)
        thumbs_dir = os.path.join(images_dir, "thumbs")
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(thumbs_dir, exist_ok=True)

        filename = f"page_{page_num:03d}_fig_{fig_index:02d}.jpg"
        thumb_filename = f"page_{page_num:03d}_fig_{fig_index:02d}_thumb.jpg"

        file_path = os.path.abspath(os.path.join(images_dir, filename))
        thumb_path = os.path.abspath(os.path.join(thumbs_dir, thumb_filename))

        # Save main image
        rgb = cropped.convert("RGB")
        rgb.save(file_path, format="JPEG", quality=85, optimize=True)

        # Save thumbnail
        self.generate_thumbnail(file_path, max_size=300, out_path=thumb_path)

        file_size_kb = os.path.getsize(file_path) / 1024

        url = f"/static/images/{book_id}/{filename}"
        thumbnail_url = f"/static/images/{book_id}/thumbs/{thumb_filename}"

        return ImageResult(
            file_path=file_path,
            url=url,
            thumbnail_url=thumbnail_url,
            width=width,
            height=height,
            caption=caption,
            page_num=page_num,
            fig_index=fig_index,
            file_size_kb=round(file_size_kb, 2),
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def generate_thumbnail(
        self, image_path: str, max_size: int = 300, out_path: str | None = None
    ) -> str:
        """Create a thumbnail capped at *max_size* on the longest side.

        If *out_path* is not provided the thumbnail is saved alongside the
        original with a ``_thumb`` suffix.  Returns the thumbnail path.
        """
        if out_path is None:
            base, ext = os.path.splitext(image_path)
            out_path = f"{base}_thumb{ext}"

        with Image.open(image_path) as img:
            thumb = img.copy()
            thumb.thumbnail((max_size, max_size), Image.LANCZOS)
            rgb = thumb.convert("RGB")
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            rgb.save(out_path, format="JPEG", quality=85, optimize=True)

        return out_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bbox_relative_to_pixel(
        bbox_rel: list[float], img_width: int, img_height: int
    ) -> tuple[int, int, int, int]:
        """Convert relative [x1,y1,x2,y2] in [0,1] to absolute pixel coordinates,
        clamped to image bounds."""
        x1 = max(0, min(1, bbox_rel[0])) * img_width
        y1 = max(0, min(1, bbox_rel[1])) * img_height
        x2 = max(0, min(1, bbox_rel[2])) * img_width
        y2 = max(0, min(1, bbox_rel[3])) * img_height

        # Ensure x1 < x2 and y1 < y2
        x1_px = int(min(x1, x2))
        y1_px = int(min(y1, y2))
        x2_px = int(max(x1, x2))
        y2_px = int(max(y1, y2))

        # Clamp to image bounds
        x1_px = max(0, min(x1_px, img_width))
        y1_px = max(0, min(y1_px, img_height))
        x2_px = max(0, min(x2_px, img_width))
        y2_px = max(0, min(y2_px, img_height))

        return (x1_px, y1_px, x2_px, y2_px)

    @staticmethod
    def _cleanup_figure(image: Image.Image) -> Image.Image:
        """Auto-crop pure-white margins while preserving colored fills.

        Naive grayscale-invert trimming throws away the pastel yellow/blue
        backgrounds SGK uses for định-nghĩa / ví-dụ boxes (light colors have
        near-white luminance). We OR a luminance mask with an HSV saturation
        mask so any pixel that's either dark or colored counts as content,
        then add a small padding so the colored border isn't shaved off.
        """
        rgb = image.convert("RGB")
        luma_inv = ImageOps.invert(rgb.convert("L"))
        sat = rgb.convert("HSV").split()[1]

        luma_mask = luma_inv.point(lambda v: 255 if v > 25 else 0)
        sat_mask = sat.point(lambda v: 255 if v > 30 else 0)
        combined = ImageChops.lighter(luma_mask, sat_mask)

        bbox = combined.getbbox()
        if bbox is None:
            return image

        w, h = image.size
        pad_x = max(2, int(w * 0.02))
        pad_y = max(2, int(h * 0.02))
        x1 = max(0, bbox[0] - pad_x)
        y1 = max(0, bbox[1] - pad_y)
        x2 = min(w, bbox[2] + pad_x)
        y2 = min(h, bbox[3] + pad_y)
        return image.crop((x1, y1, x2, y2))

    @staticmethod
    def _skip_if_too_small(bbox_px: tuple[int, int, int, int]) -> bool:
        """Return True when the cropped area is smaller than 50×50 px."""
        x1, y1, x2, y2 = bbox_px
        return (x2 - x1) < 50 or (y2 - y1) < 50


# Module-level singleton
image_extractor = ImageExtractor()
