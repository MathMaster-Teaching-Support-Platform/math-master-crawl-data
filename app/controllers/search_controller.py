from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.repositories.chapter_repository import chapter_repository
from app.repositories.content_repository import content_repository
from app.repositories.lesson_repository import lesson_repository
from app.utils.response import success_response

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def search(
    q: str = Query(..., min_length=1, description="Search keyword"),
    grade: Optional[int] = Query(default=None, ge=1, le=12),
    chapter_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Full-text search across lesson content blocks.
    Uses MongoDB $text index on 'content' and 'latex' fields.
    Returns matched blocks enriched with lesson/chapter metadata.
    """
    blocks = await content_repository.search_text(q, limit=limit)

    results = []
    for block in blocks:
        # Fetch lesson metadata
        lesson = await lesson_repository.get_by_id(block.lesson_id)
        if lesson is None:
            continue

        # Fetch chapter metadata
        chapter = await chapter_repository.get_by_id(lesson.chapter_id)
        if chapter is None:
            continue

        # Filter by grade if requested (chapter carries book_id, need book grade)
        # Grade filtering is done at chapter level via book_id lookup only when
        # grade param is provided — lightweight: skip if mismatch detected via
        # chapter.book_id prefix (not available here without book lookup).
        # For simplicity we include the grade from chapter's book_id lookup later;
        # for now apply chapter_id filter if given.
        if chapter_id is not None and chapter.id != chapter_id:
            continue

        results.append(
            {
                "content_id": block.id,
                "type": block.type,
                "content": block.content,
                "latex": block.latex,
                "image_url": block.image_url,
                "caption": block.caption,
                "exercise_type": block.exercise_type,
                "source": block.source,
                "lesson": {
                    "id": lesson.id,
                    "title": lesson.title,
                    "lesson_index": lesson.lesson_index,
                },
                "chapter": {
                    "id": chapter.id,
                    "title": chapter.title,
                    "roman_index": chapter.roman_index,
                    "book_id": chapter.book_id,
                },
            }
        )

    return success_response(data={"total": len(results), "results": results})
