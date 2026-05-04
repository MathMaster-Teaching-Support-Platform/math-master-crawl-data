from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from app.repositories.content_repository import content_repository
from app.repositories.lesson_repository import lesson_repository
from app.repositories.chapter_repository import chapter_repository
from app.repositories.history_repository import history_repository
from app.schemas.lesson import LessonCreate
from app.utils.response import success_response

router = APIRouter(prefix="/lessons", tags=["lessons"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lesson_to_dict(les) -> dict:
    return {
        "id": les.id,
        "chapter_id": les.chapter_id,
        "lesson_index": les.lesson_index,
        "title": les.title,
        "page_start": les.page_start,
        "updated_at": getattr(les, "updated_at", None),
        "updated_by": getattr(les, "updated_by", None),
    }


@router.get("/{lesson_id}")
async def get_lesson(lesson_id: str):
    """Return a single lesson by ID."""
    lesson = await lesson_repository.get_by_id(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    return success_response(data=_lesson_to_dict(lesson))


@router.get("/{lesson_id}/content")
async def get_lesson_content(lesson_id: str):
    """Return all content blocks for a lesson, ordered by position."""
    lesson = await lesson_repository.get_by_id(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    blocks = await content_repository.list_by_lesson(lesson_id)
    data = [
        {
            "id": b.id,
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
        for b in blocks
    ]
    return success_response(data=data)


@router.get("/{lesson_id}/history")
async def get_lesson_history(lesson_id: str):
    """Return change history for a lesson."""
    entries = await history_repository.list_by_entity(lesson_id)
    return success_response(data=[e.model_dump(by_alias=False) for e in entries])


# ─── Create ───────────────────────────────────────────────────────────────────

class LessonCreateRequest(BaseModel):
    chapter_id: str
    title: str
    lesson_index: Optional[int] = None   # auto-increment if omitted


@router.post("")
async def create_lesson(
    body: LessonCreateRequest,
    x_changed_by: str = Header(default="unknown"),
):
    """Create a new lesson in a chapter."""
    chapter = await chapter_repository.get_by_id(body.chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found.")

    lesson_index = body.lesson_index
    if lesson_index is None:
        existing = await lesson_repository.list_by_chapter(body.chapter_id)
        lesson_index = (max((l.lesson_index for l in existing), default=0) + 1)

    create = LessonCreate(
        chapter_id=body.chapter_id,
        lesson_index=lesson_index,
        title=body.title.strip(),
    )
    lesson_id = await lesson_repository.create(create)
    created = await lesson_repository.get_by_id(lesson_id)

    await history_repository.record(
        entity_type="lesson",
        entity_id=lesson_id,
        book_id=chapter.book_id,
        action="create",
        changed_by=x_changed_by,
        before=None,
        after=_lesson_to_dict(created),
        summary=f"Tạo bài [{lesson_index}] '{body.title}'",
    )
    return success_response(data=_lesson_to_dict(created), message="Lesson created.")


# ─── Update ───────────────────────────────────────────────────────────────────

class LessonUpdateRequest(BaseModel):
    title: Optional[str] = None


@router.patch("/{lesson_id}")
async def update_lesson(
    lesson_id: str,
    body: LessonUpdateRequest,
    x_changed_by: str = Header(default="unknown"),
):
    """Rename a lesson title."""
    from bson import ObjectId
    lesson = await lesson_repository.get_by_id(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    if not body.title or not body.title.strip():
        raise HTTPException(status_code=422, detail="title is required.")

    before = _lesson_to_dict(lesson)
    fields = {
        "title": body.title.strip(),
        "updated_at": _now_iso(),
        "updated_by": x_changed_by,
    }
    await lesson_repository.collection.update_one(
        {"_id": ObjectId(lesson_id)}, {"$set": fields}
    )
    updated = await lesson_repository.get_by_id(lesson_id)

    ch = await chapter_repository.get_by_id(lesson.chapter_id)
    book_id = ch.book_id if ch else ""
    await history_repository.record(
        entity_type="lesson",
        entity_id=lesson_id,
        book_id=book_id,
        action="update",
        changed_by=x_changed_by,
        before=before,
        after=_lesson_to_dict(updated),
        summary=f"title: '{lesson.title}'→'{body.title.strip()}'",
    )
    return success_response(data=_lesson_to_dict(updated), message="Lesson updated.")


# ─── Delete ───────────────────────────────────────────────────────────────────

@router.delete("/{lesson_id}")
async def delete_lesson(
    lesson_id: str,
    x_changed_by: str = Header(default="unknown"),
):
    """Delete a lesson and all its content blocks."""
    lesson = await lesson_repository.get_by_id(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found.")

    before = _lesson_to_dict(lesson)
    await content_repository.delete_by_lesson(lesson_id)
    await lesson_repository.delete(lesson_id)

    ch = await chapter_repository.get_by_id(lesson.chapter_id)
    book_id = ch.book_id if ch else ""
    await history_repository.record(
        entity_type="lesson",
        entity_id=lesson_id,
        book_id=book_id,
        action="delete",
        changed_by=x_changed_by,
        before=before,
        after=None,
        summary=f"Xóa bài '{lesson.title}'",
    )
    return success_response(data={"deleted": lesson_id}, message="Lesson deleted.")



@router.get("/{lesson_id}")
async def get_lesson(lesson_id: str):
    """Return a single lesson by ID."""
    lesson = await lesson_repository.get_by_id(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    return success_response(
        data={
            "id": lesson.id,
            "chapter_id": lesson.chapter_id,
            "lesson_index": lesson.lesson_index,
            "title": lesson.title,
            "page_start": lesson.page_start,
        }
    )


@router.get("/{lesson_id}/content")
async def get_lesson_content(lesson_id: str):
    """Return all content blocks for a lesson, ordered by position."""
    lesson = await lesson_repository.get_by_id(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    blocks = await content_repository.list_by_lesson(lesson_id)
    data = [
        {
            "id": b.id,
            "order": b.order,
            "type": b.type,
            "content": b.content,
            "latex": b.latex,
            "image_url": b.image_url,
            "thumbnail_url": b.thumbnail_url,
            "caption": b.caption,
            "exercise_type": b.exercise_type,
            "exercise_num": b.exercise_num,
            "confidence": b.confidence,
            "source": b.source,
        }
        for b in blocks
    ]
    return success_response(data=data)


class LessonUpdateRequest(BaseModel):
    title: Optional[str] = None


@router.patch("/{lesson_id}")
async def update_lesson(lesson_id: str, body: LessonUpdateRequest):
    """Rename a lesson title."""
    from bson import ObjectId
    lesson = await lesson_repository.get_by_id(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    if not body.title or not body.title.strip():
        raise HTTPException(status_code=422, detail="title is required.")
    await lesson_repository.collection.update_one(
        {"_id": ObjectId(lesson_id)}, {"$set": {"title": body.title.strip()}}
    )
    updated = await lesson_repository.get_by_id(lesson_id)
    return success_response(
        data={
            "id": updated.id,
            "chapter_id": updated.chapter_id,
            "lesson_index": updated.lesson_index,
            "title": updated.title,
            "page_start": updated.page_start,
        },
        message="Lesson updated.",
    )


@router.delete("/{lesson_id}")
async def delete_lesson(lesson_id: str):
    """Delete a lesson and all its content blocks."""
    lesson = await lesson_repository.get_by_id(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    await content_repository.delete_by_lesson(lesson_id)
    await lesson_repository.delete(lesson_id)
    return success_response(data={"deleted": lesson_id}, message="Lesson deleted.")
