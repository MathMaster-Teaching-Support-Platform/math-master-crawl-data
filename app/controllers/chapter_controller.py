from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from app.repositories.chapter_repository import chapter_repository
from app.repositories.content_repository import content_repository
from app.repositories.lesson_repository import lesson_repository
from app.repositories.history_repository import history_repository
from app.schemas.chapter import ChapterCreate
from app.utils.response import success_response

router = APIRouter(prefix="/chapters", tags=["chapters"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chapter_to_dict(ch) -> dict:
    return {
        "id": ch.id,
        "book_id": ch.book_id,
        "chapter_index": ch.chapter_index,
        "roman_index": ch.roman_index,
        "title": ch.title,
        "page_start": ch.page_start,
        "updated_at": getattr(ch, "updated_at", None),
        "updated_by": getattr(ch, "updated_by", None),
    }


@router.get("/{chapter_id}")
async def get_chapter(chapter_id: str):
    """Return a single chapter by ID."""
    chapter = await chapter_repository.get_by_id(chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found.")
    return success_response(data=_chapter_to_dict(chapter))


@router.get("/{chapter_id}/lessons")
async def get_lessons_by_chapter(chapter_id: str):
    """List all lessons belonging to a chapter."""
    chapter = await chapter_repository.get_by_id(chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found.")
    lessons = await lesson_repository.list_by_chapter(chapter_id)
    data = [
        {
            "id": les.id,
            "chapter_id": les.chapter_id,
            "lesson_index": les.lesson_index,
            "title": les.title,
            "page_start": les.page_start,
            "updated_at": getattr(les, "updated_at", None),
            "updated_by": getattr(les, "updated_by", None),
        }
        for les in lessons
    ]
    return success_response(data=data)


@router.get("/{chapter_id}/history")
async def get_chapter_history(chapter_id: str):
    """Return change history for a chapter."""
    entries = await history_repository.list_by_entity(chapter_id)
    return success_response(data=[e.model_dump(by_alias=False) for e in entries])


# ─── Create ───────────────────────────────────────────────────────────────────

class ChapterCreateRequest(BaseModel):
    book_id: str
    title: str
    roman_index: str = ""
    chapter_index: Optional[int] = None   # auto-increment if omitted


@router.post("")
async def create_chapter(
    body: ChapterCreateRequest,
    x_changed_by: str = Header(default="unknown"),
):
    """Create a new chapter in a book. chapter_index auto-increments if not given."""
    chapter_index = body.chapter_index
    if chapter_index is None:
        existing = await chapter_repository.list_by_book(body.book_id)
        chapter_index = (max((c.chapter_index for c in existing), default=0) + 1)

    create = ChapterCreate(
        book_id=body.book_id,
        chapter_index=chapter_index,
        roman_index=body.roman_index,
        title=body.title.strip(),
    )
    chapter_id = await chapter_repository.create(create)
    created = await chapter_repository.get_by_id(chapter_id)

    await history_repository.record(
        entity_type="chapter",
        entity_id=chapter_id,
        book_id=body.book_id,
        action="create",
        changed_by=x_changed_by,
        before=None,
        after=_chapter_to_dict(created),
        summary=f"Tạo chương [{chapter_index}] '{body.title}'",
    )
    return success_response(data=_chapter_to_dict(created), message="Chapter created.")


# ─── Update ───────────────────────────────────────────────────────────────────

class ChapterUpdateRequest(BaseModel):
    title: Optional[str] = None
    roman_index: Optional[str] = None


@router.patch("/{chapter_id}")
async def update_chapter(
    chapter_id: str,
    body: ChapterUpdateRequest,
    x_changed_by: str = Header(default="unknown"),
):
    """Rename a chapter title or update its roman numeral."""
    from bson import ObjectId
    chapter = await chapter_repository.get_by_id(chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found.")

    before = _chapter_to_dict(chapter)
    fields: dict = {"updated_at": _now_iso(), "updated_by": x_changed_by}
    changes = []

    if body.title is not None:
        fields["title"] = body.title.strip()
        changes.append(f"title: '{chapter.title}'→'{body.title.strip()}'")
    if body.roman_index is not None:
        fields["roman_index"] = body.roman_index.strip()
        changes.append(f"roman_index: '{chapter.roman_index}'→'{body.roman_index.strip()}'")

    if len(fields) <= 2:
        raise HTTPException(status_code=422, detail="No updatable fields provided.")

    await chapter_repository.collection.update_one(
        {"_id": ObjectId(chapter_id)}, {"$set": fields}
    )
    updated = await chapter_repository.get_by_id(chapter_id)

    await history_repository.record(
        entity_type="chapter",
        entity_id=chapter_id,
        book_id=chapter.book_id,
        action="update",
        changed_by=x_changed_by,
        before=before,
        after=_chapter_to_dict(updated),
        summary="; ".join(changes),
    )
    return success_response(data=_chapter_to_dict(updated), message="Chapter updated.")


# ─── Delete ───────────────────────────────────────────────────────────────────

@router.delete("/{chapter_id}")
async def delete_chapter(
    chapter_id: str,
    x_changed_by: str = Header(default="unknown"),
):
    """Delete a chapter and cascade delete all its lessons and content blocks."""
    chapter = await chapter_repository.get_by_id(chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found.")

    before = _chapter_to_dict(chapter)
    lessons = await lesson_repository.list_by_chapter(chapter_id)
    for les in lessons:
        await content_repository.delete_by_lesson(les.id)
    await lesson_repository.delete_by_chapter(chapter_id)
    await chapter_repository.delete(chapter_id)

    await history_repository.record(
        entity_type="chapter",
        entity_id=chapter_id,
        book_id=chapter.book_id,
        action="delete",
        changed_by=x_changed_by,
        before=before,
        after=None,
        summary=f"Xóa chương '{chapter.title}' (cascade {len(lessons)} bài)",
    )
    return success_response(data={"deleted": chapter_id}, message="Chapter deleted.")



@router.get("/{chapter_id}")
async def get_chapter(chapter_id: str):
    """Return a single chapter by ID."""
    chapter = await chapter_repository.get_by_id(chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found.")
    return success_response(
        data={
            "id": chapter.id,
            "book_id": chapter.book_id,
            "chapter_index": chapter.chapter_index,
            "roman_index": chapter.roman_index,
            "title": chapter.title,
            "page_start": chapter.page_start,
        }
    )


@router.get("/{chapter_id}/lessons")
async def get_lessons_by_chapter(chapter_id: str):
    """List all lessons belonging to a chapter."""
    chapter = await chapter_repository.get_by_id(chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found.")
    lessons = await lesson_repository.list_by_chapter(chapter_id)
    data = [
        {
            "id": les.id,
            "chapter_id": les.chapter_id,
            "lesson_index": les.lesson_index,
            "title": les.title,
            "page_start": les.page_start,
        }
        for les in lessons
    ]
    return success_response(data=data)


class ChapterUpdateRequest(BaseModel):
    title: Optional[str] = None
    roman_index: Optional[str] = None


@router.patch("/{chapter_id}")
async def update_chapter(chapter_id: str, body: ChapterUpdateRequest):
    """Rename a chapter title or update its roman numeral."""
    from datetime import datetime, timezone
    from bson import ObjectId
    chapter = await chapter_repository.get_by_id(chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found.")
    fields: dict = {}
    if body.title is not None:
        fields["title"] = body.title.strip()
    if body.roman_index is not None:
        fields["roman_index"] = body.roman_index.strip()
    if not fields:
        raise HTTPException(status_code=422, detail="No updatable fields provided.")
    await chapter_repository.collection.update_one(
        {"_id": ObjectId(chapter_id)}, {"$set": fields}
    )
    updated = await chapter_repository.get_by_id(chapter_id)
    return success_response(
        data={
            "id": updated.id,
            "book_id": updated.book_id,
            "chapter_index": updated.chapter_index,
            "roman_index": updated.roman_index,
            "title": updated.title,
            "page_start": updated.page_start,
        },
        message="Chapter updated.",
    )


@router.delete("/{chapter_id}")
async def delete_chapter(chapter_id: str):
    """Delete a chapter and cascade delete all its lessons and content blocks."""
    chapter = await chapter_repository.get_by_id(chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found.")
    lessons = await lesson_repository.list_by_chapter(chapter_id)
    for les in lessons:
        await content_repository.delete_by_lesson(les.id)
    await lesson_repository.delete_by_chapter(chapter_id)
    await chapter_repository.delete(chapter_id)
    return success_response(data={"deleted": chapter_id}, message="Chapter deleted.")
