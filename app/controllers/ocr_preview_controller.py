"""OCR Preview — upload 1-5 page images, get Gemini analysis instantly.

Images are saved to  storage/demo/<session_id>/
Results are persisted to MongoDB collection  demo_analyses
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import settings
from app.core.mongo import mongo_db
from app.services.gemini_service import GeminiOCRService, PageAnalysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/books/ocr-preview", tags=["ocr-preview"])

_MAX_IMAGES = 5
_MAX_SIZE_MB = 10
_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
_DEMO_COLLECTION = "demo_analyses"


def _block_to_dict(b) -> dict:
    return {
        "order": b.order,
        "type": b.type,
        "content": b.content,
        "latex": b.latex,
        "image_bbox": list(b.image_bbox) if b.image_bbox else None,
        "caption": b.caption,
        "confidence": round(b.confidence, 3),
        "needs_mathpix": b.needs_mathpix,
        "source": b.source,
    }


@router.post(
    "",
    summary="OCR preview — upload 1-5 page images, see Gemini analysis instantly",
)
async def ocr_preview(
    images: list[UploadFile] = File(..., description="1–5 page images (JPEG/PNG/WEBP)"),
):
    """
    Upload tối đa 5 ảnh trang sách → Gemini OCR → trả về JSON blocks.
    - Ảnh lưu vào  storage/demo/<session_id>/
    - Kết quả lưu vào MongoDB collection  demo_analyses
    - Dùng để kiểm tra context trước khi chạy pipeline sách thật.
    """
    if not images:
        raise HTTPException(status_code=400, detail="Phải upload ít nhất 1 ảnh.")
    if len(images) > _MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"Tối đa {_MAX_IMAGES} ảnh mỗi lần.")

    try:
        gemini = GeminiOCRService()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    session_id = uuid.uuid4().hex[:12]
    demo_dir = Path(settings.storage_path) / "demo" / session_id
    demo_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for idx, upload in enumerate(images, start=1):
        # Validate content type
        if upload.content_type not in _ALLOWED_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Ảnh #{idx}: chỉ hỗ trợ JPEG/PNG/WEBP, nhận được '{upload.content_type}'.",
            )

        data = await upload.read()
        size_mb = len(data) / (1024 * 1024)
        if size_mb > _MAX_SIZE_MB:
            raise HTTPException(
                status_code=400,
                detail=f"Ảnh #{idx}: vượt quá {_MAX_SIZE_MB} MB ({size_mb:.1f} MB).",
            )

        # Save image to demo folder
        suffix = os.path.splitext(upload.filename or "page.jpg")[1] or ".jpg"
        img_filename = f"page_{idx:02d}{suffix}"
        img_path = demo_dir / img_filename
        img_path.write_bytes(data)
        logger.info("[ocr-preview][%s] Saved image #%d → %s (%.1f MB)", session_id, idx, img_path, size_mb)

        # Call Gemini OCR
        try:
            analysis: PageAnalysis = await gemini.analyze_page(str(img_path), page_num=idx)
        except Exception as exc:
            logger.exception("[ocr-preview][%s] Gemini failed for image #%d", session_id, idx)
            raise HTTPException(status_code=502, detail=f"Gemini lỗi ở ảnh #{idx}: {exc}")

        result = {
            "image_index": idx,
            "filename": upload.filename,
            "saved_path": str(img_path),
            "page_num": analysis.page_num,
            "processing_time_ms": analysis.processing_time_ms,
            "num_blocks": len(analysis.blocks),
            "blocks": [_block_to_dict(b) for b in analysis.blocks],
        }
        results.append(result)
        logger.info(
            "[ocr-preview][%s] Image #%d done — %d blocks, %d ms",
            session_id, idx, len(analysis.blocks), analysis.processing_time_ms,
        )

    # Persist to demo_analyses collection
    doc = {
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc),
        "num_images": len(images),
        "pages": results,
    }
    try:
        await mongo_db[_DEMO_COLLECTION].insert_one(doc)
        logger.info("[ocr-preview][%s] Saved to demo_analyses.", session_id)
    except Exception:
        logger.warning("[ocr-preview][%s] Failed to save to demo_analyses.", session_id, exc_info=True)

    return {"session_id": session_id, "demo_folder": str(demo_dir), "pages": results}


@router.get(
    "/{session_id}",
    summary="Lấy lại kết quả demo theo session_id",
)
async def get_demo_session(session_id: str):
    """Xem lại kết quả OCR của 1 session demo đã chạy trước đó."""
    doc = await mongo_db[_DEMO_COLLECTION].find_one(
        {"session_id": session_id}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' không tồn tại.")
    # Convert datetime for JSON
    if "created_at" in doc and hasattr(doc["created_at"], "isoformat"):
        doc["created_at"] = doc["created_at"].isoformat()
    return doc


@router.get(
    "",
    summary="Liệt kê các session demo gần nhất",
)
async def list_demo_sessions(limit: int = 20):
    """Danh sách các session demo gần nhất (tối đa 20)."""
    cursor = mongo_db[_DEMO_COLLECTION].find(
        {}, {"_id": 0, "session_id": 1, "created_at": 1, "num_images": 1}
    ).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    for d in docs:
        if "created_at" in d and hasattr(d["created_at"], "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
    return docs
