import os
import uuid as uuid_mod

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from app.core.config import settings
from app.repositories.content_repository import content_repository
from app.repositories.lesson_repository import lesson_repository
from app.repositories.chapter_repository import chapter_repository
from app.repositories.history_repository import history_repository
from app.schemas.content import ContentBlockCreate
from app.utils.response import success_response

router = APIRouter(prefix="/content", tags=["content"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _block_to_dict(b) -> dict:
    return {
        "id": b.id,
        "lesson_id": b.lesson_id,
        "order": b.order,
        "type": b.type,
        "content": b.content,
        "label": getattr(b, "label", ""),
        "latex": b.latex,
        "image_url": b.image_url,
        "image_path": getattr(b, "image_path", ""),
        "thumbnail_url": b.thumbnail_url,
        "caption": b.caption,
        "exercise_type": b.exercise_type,
        "exercise_num": b.exercise_num,
        "confidence": b.confidence,
        "source": b.source,
        "updated_at": getattr(b, "updated_at", None),
        "updated_by": getattr(b, "updated_by", None),
    }


async def _get_book_id_for_lesson(lesson_id: str) -> str:
    lesson = await lesson_repository.get_by_id(lesson_id)
    if not lesson:
        return ""
    ch = await chapter_repository.get_by_id(lesson.chapter_id)
    return ch.book_id if ch else ""


# ─── Request models ───────────────────────────────────────────────────────────

class ContentCreateRequest(BaseModel):
    lesson_id: str
    type: str
    content: str = ""
    label: str = ""
    latex: str = ""
    image_url: str = ""
    caption: str = ""
    exercise_type: str = ""
    exercise_num: int = 0
    order: Optional[int] = None   # auto-append if omitted


class ContentUpdateRequest(BaseModel):
    type: Optional[str] = None
    content: Optional[str] = None
    label: Optional[str] = None
    latex: Optional[str] = None
    image_url: Optional[str] = None
    caption: Optional[str] = None
    exercise_type: Optional[str] = None
    exercise_num: Optional[int] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/upload-image")
async def upload_content_image(file: UploadFile = File(...)):
    """Upload an image for a content block. Returns { image_url } stored under /static/content-images/."""
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, or WebP images are accepted.")

    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image exceeds 20 MB limit.")

    ext = (file.filename or "image.jpg").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"

    img_dir = os.path.join(settings.storage_path, "content-images")
    os.makedirs(img_dir, exist_ok=True)
    filename = f"{uuid_mod.uuid4().hex}.{ext}"
    with open(os.path.join(img_dir, filename), "wb") as f:
        f.write(contents)

    image_url = f"/static/content-images/{filename}"
    return success_response(data={"image_url": image_url})


@router.get("/{content_id}")
async def get_content(content_id: str):
    block = await content_repository.get_by_id(content_id)
    if block is None:
        raise HTTPException(status_code=404, detail="Content block not found.")
    return success_response(data=_block_to_dict(block))


@router.post("")
async def create_content(
    body: ContentCreateRequest,
    x_changed_by: str = Header(default="unknown"),
):
    order = body.order
    if order is None:
        existing = await content_repository.list_by_lesson(body.lesson_id)
        order = (max((b.order for b in existing), default=-1) + 1)

    create = ContentBlockCreate(
        lesson_id=body.lesson_id,
        order=order,
        type=body.type,
        content=body.content,
        label=body.label,
        latex=body.latex,
        image_url=body.image_url,
        caption=body.caption,
        exercise_type=body.exercise_type,
        exercise_num=body.exercise_num,
        source="manual",
    )
    content_id = await content_repository.create(create)
    created = await content_repository.get_by_id(content_id)
    book_id = await _get_book_id_for_lesson(body.lesson_id)

    await history_repository.record(
        entity_type="content",
        entity_id=content_id,
        book_id=book_id,
        action="create",
        changed_by=x_changed_by,
        before=None,
        after=_block_to_dict(created),
        summary=f"Tạo mới block [{body.type}]",
    )
    return success_response(data=_block_to_dict(created), message="Content block created.")


@router.patch("/{content_id}")
async def update_content(
    content_id: str,
    body: ContentUpdateRequest,
    x_changed_by: str = Header(default="unknown"),
):
    from bson import ObjectId
    block = await content_repository.get_by_id(content_id)
    if block is None:
        raise HTTPException(status_code=404, detail="Content block not found.")

    before = _block_to_dict(block)
    fields: dict = {"updated_at": _now_iso(), "updated_by": x_changed_by}
    changes = []

    if body.type is not None:
        fields["type"] = body.type
        changes.append(f"type: '{block.type}'→'{body.type}'")
    if body.content is not None:
        old = (block.content or "")[:40]
        new = body.content[:40]
        fields["content"] = body.content
        changes.append(f"content: '{old}'→'{new}'")
    if body.label is not None:
        fields["label"] = body.label
        changes.append(f"label: '{getattr(block, 'label', '')}'→'{body.label}'")
    if body.latex is not None:
        fields["latex"] = body.latex
        changes.append("latex updated")
    if body.image_url is not None:
        fields["image_url"] = body.image_url
        changes.append("image_url updated")
    if body.caption is not None:
        fields["caption"] = body.caption
        changes.append(f"caption: '{block.caption}'→'{body.caption}'")
    if body.exercise_type is not None:
        fields["exercise_type"] = body.exercise_type
    if body.exercise_num is not None:
        fields["exercise_num"] = body.exercise_num

    if len(fields) <= 2:
        raise HTTPException(status_code=422, detail="No updatable fields provided.")

    await content_repository.collection.update_one(
        {"_id": ObjectId(content_id)}, {"$set": fields}
    )
    updated = await content_repository.get_by_id(content_id)
    book_id = await _get_book_id_for_lesson(block.lesson_id)

    await history_repository.record(
        entity_type="content",
        entity_id=content_id,
        book_id=book_id,
        action="update",
        changed_by=x_changed_by,
        before=before,
        after=_block_to_dict(updated),
        summary="; ".join(changes) if changes else "Đã cập nhật",
    )
    return success_response(data=_block_to_dict(updated), message="Content block updated.")


@router.delete("/{content_id}")
async def delete_content(
    content_id: str,
    x_changed_by: str = Header(default="unknown"),
):
    block = await content_repository.get_by_id(content_id)
    if block is None:
        raise HTTPException(status_code=404, detail="Content block not found.")

    before = _block_to_dict(block)
    book_id = await _get_book_id_for_lesson(block.lesson_id)
    await content_repository.delete(content_id)

    await history_repository.record(
        entity_type="content",
        entity_id=content_id,
        book_id=book_id,
        action="delete",
        changed_by=x_changed_by,
        before=before,
        after=None,
        summary=f"Xóa block [{block.type}]: '{(block.content or '')[:30]}'",
    )
    return success_response(data={"deleted": content_id}, message="Content block deleted.")


@router.get("/{content_id}/history")
async def get_content_history(content_id: str):
    entries = await history_repository.list_by_entity(content_id)
    return success_response(data=[e.model_dump(by_alias=False) for e in entries])
