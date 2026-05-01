from fastapi import APIRouter, HTTPException

from app.repositories.content_repository import content_repository
from app.repositories.lesson_repository import lesson_repository
from app.utils.response import success_response

router = APIRouter(prefix="/lessons", tags=["lessons"])


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
