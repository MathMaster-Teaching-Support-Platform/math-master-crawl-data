from fastapi import APIRouter, HTTPException

from app.repositories.chapter_repository import chapter_repository
from app.repositories.lesson_repository import lesson_repository
from app.utils.response import success_response

router = APIRouter(prefix="/chapters", tags=["chapters"])


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
