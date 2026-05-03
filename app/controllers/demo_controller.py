"""Demo OCR — upload 1-5 page images, get Gemini analysis instantly.

Hoàn toàn tách biệt với pipeline sách thật.
- Ảnh lưu vào  storage/demo/<session_id>/
- Kết quả lưu vào MongoDB collection  demo_analyses
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import settings
from app.core.mongo import mongo_db
from app.services.gemini_service import GeminiOCRService, PageAnalysis, TocAnalysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/demo", tags=["demo"])

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
    "/ocr",
    summary="Demo OCR — upload 1 ảnh trang SGK, nhận JSON blocks từ Gemini",
)
async def demo_ocr(
    image: UploadFile = File(..., description="1 page image (JPEG/PNG/WEBP)"),
):
    """
    Upload 1 ảnh trang sách → Gemini OCR → trả về JSON blocks.
    Không chạy pipeline, không ảnh hưởng DB sách thật.
    """
    if image is None:
        raise HTTPException(status_code=400, detail="Phải upload 1 ảnh.")

    try:
        gemini = GeminiOCRService()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    session_id = uuid.uuid4().hex[:12]
    demo_dir = Path(settings.storage_path) / "demo" / session_id
    demo_dir.mkdir(parents=True, exist_ok=True)

    if image.content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Chỉ hỗ trợ JPEG/PNG/WEBP, nhận được '{image.content_type}'.",
        )

    data = await image.read()
    size_mb = len(data) / (1024 * 1024)
    if size_mb > _MAX_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"Vượt quá {_MAX_SIZE_MB} MB ({size_mb:.1f} MB).",
        )

    suffix = os.path.splitext(image.filename or "page.jpg")[1] or ".jpg"
    img_path = demo_dir / f"page_01{suffix}"
    img_path.write_bytes(data)
    logger.info("[demo][%s] Saved → %s (%.1f MB)", session_id, img_path, size_mb)

    try:
        analysis: PageAnalysis = await gemini.analyze_page(str(img_path), page_num=1)
    except Exception as exc:
        logger.exception("[demo][%s] Gemini failed", session_id)
        raise HTTPException(status_code=502, detail=f"Gemini lỗi: {exc}")

    # If Gemini flagged this as a TOC page, extract actual TOC entries
    toc_data: dict | None = None
    is_toc = (
        len(analysis.blocks) == 1
        and getattr(analysis.blocks[0], "type", "") == "toc"
    )
    if is_toc:
        try:
            toc_result: TocAnalysis | None = await gemini.analyze_toc_page(str(img_path), page_num=1)
            if toc_result:
                toc_data = {
                    "toc_page_num": toc_result.toc_page_num,
                    "entries": [
                        {
                            "type": e.type,
                            "chapter_index": e.chapter_index,
                            "chapter_roman": e.chapter_roman,
                            "lesson_index": e.lesson_index,
                            "title": e.title,
                            "page_start": e.page_start,
                        }
                        for e in toc_result.entries
                    ],
                }
                logger.info("[demo][%s] TOC extracted: %d entries", session_id, len(toc_result.entries))
        except Exception:
            logger.warning("[demo][%s] TOC extraction failed, skipping", session_id, exc_info=True)

    result = {
        "image_index": 1,
        "filename": image.filename,
        "saved_path": str(img_path),
        "page_num": analysis.page_num,
        "processing_time_ms": analysis.processing_time_ms,
        "is_toc": is_toc,
        "num_blocks": len(analysis.blocks),
        "blocks": [_block_to_dict(b) for b in analysis.blocks],
        "toc": toc_data,
    }
    logger.info("[demo][%s] Done — %d blocks, %d ms", session_id, len(analysis.blocks), analysis.processing_time_ms)

    doc = {
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc),
        "num_images": 1,
        "pages": [result],
    }
    try:
        await mongo_db[_DEMO_COLLECTION].insert_one(doc)
    except Exception:
        logger.warning("[demo][%s] Failed to save to demo_analyses.", session_id, exc_info=True)

    return {"session_id": session_id, "demo_folder": str(demo_dir), "pages": [result]}


@router.get(
    "/ocr",
    summary="Liệt kê các session demo gần nhất",
)
async def list_demo_sessions(limit: int = 20):
    """Danh sách các session demo gần nhất."""
    cursor = mongo_db[_DEMO_COLLECTION].find(
        {}, {"_id": 0, "session_id": 1, "created_at": 1, "num_images": 1}
    ).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    for d in docs:
        if "created_at" in d and hasattr(d["created_at"], "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
    return docs


@router.get(
    "/ocr/{session_id}",
    summary="Xem lại kết quả 1 session demo",
)
async def get_demo_session(session_id: str):
    """Xem lại kết quả OCR của session đã chạy."""
    doc = await mongo_db[_DEMO_COLLECTION].find_one(
        {"session_id": session_id}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' không tồn tại.")
    if "created_at" in doc and hasattr(doc["created_at"], "isoformat"):
        doc["created_at"] = doc["created_at"].isoformat()
    return doc
