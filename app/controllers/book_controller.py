"""HTTP surface consumed by the Java BE's `PythonCrawlerClient`.

Contract is specified on the Java side; do not rename, restructure, or add
fields without updating the BE in lockstep. The endpoints intentionally
return raw JSON shapes (camelCase keys via Pydantic aliases) instead of the
`success_response` envelope used by other controllers — the BE deserializes
directly into typed records.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.repositories.book_repository import book_repository
from app.repositories.lesson_page_repository import lesson_page_repository
from app.schemas.lesson_page import (
    PageHistoryEntry,
    LessonPageDB,
    OcrSinglePageRequest,
    OcrStatusResponse,
    OcrTriggerRequest,
    OcrTriggerResult,
    UpdateLessonPageRequest,
    VerifyState,
)
from app.services.processing_pipeline import run_pipeline_with_mapping, run_single_page_with_mapping

router = APIRouter(prefix="/books", tags=["books"])


# ---------------------------------------------------------------------------
# OCR trigger + status
# ---------------------------------------------------------------------------


@router.post("/{book_id}/ocr-with-mapping", response_model=OcrTriggerResult)
async def trigger_ocr_with_mapping(
    book_id: str,
    request: OcrTriggerRequest,
    background_tasks: BackgroundTasks,
) -> OcrTriggerResult:
    """Kick off OCR using the BE-supplied lesson→page mapping. The BE has
    already validated mapping shape (page bounds, ordering, overlap rules);
    we trust the input and only re-check the bookId-in-path matches the
    body (defense-in-depth in case of a typo on the BE)."""
    if request.book_id != book_id:
        raise HTTPException(
            status_code=400,
            detail="bookId in path does not match bookId in body.",
        )
    if not request.mappings:
        raise HTTPException(
            status_code=400,
            detail="At least one lesson→page mapping is required.",
        )
    if request.ocr_page_to < request.ocr_page_from:
        raise HTTPException(
            status_code=400,
            detail="ocrPageTo must be >= ocrPageFrom.",
        )

    await book_repository.upsert_for_ocr(
        book_id=book_id,
        pdf_path=request.pdf_path,
        ocr_page_from=request.ocr_page_from,
        ocr_page_to=request.ocr_page_to,
    )

    # Hand the pipeline plain dicts so it doesn't depend on the controller's
    # request schema (lets the entry point be reused from a CLI later).
    mappings_payload = [
        {
            "lesson_id": m.lesson_id,
            "page_start": m.page_start,
            "page_end": m.page_end,
        }
        for m in request.mappings
    ]
    background_tasks.add_task(
        run_pipeline_with_mapping,
        book_id,
        request.pdf_path,
        request.ocr_page_from,
        request.ocr_page_to,
        mappings_payload,
    )

    pages_queued = max(0, request.ocr_page_to - request.ocr_page_from + 1)
    return OcrTriggerResult(
        status="ACCEPTED",
        message="OCR job queued.",
        total_pages_queued=pages_queued,
    )


@router.post("/{book_id}/ocr-single-page", response_model=OcrTriggerResult)
async def trigger_ocr_single_page(
    book_id: str,
    request: OcrSinglePageRequest,
    background_tasks: BackgroundTasks,
) -> OcrTriggerResult:
    """Re-run Gemini+Mathpix for one mapped PDF page (verify wizard). Does not reset full-book OCR state."""
    if request.book_id != book_id:
        raise HTTPException(
            status_code=400,
            detail="bookId in path does not match bookId in body.",
        )
    if request.ocr_page_to < request.ocr_page_from:
        raise HTTPException(
            status_code=400,
            detail="ocrPageTo must be >= ocrPageFrom.",
        )
    if not request.mappings:
        raise HTTPException(
            status_code=400,
            detail="At least one lesson→page mapping is required.",
        )

    mappings_payload = [
        {
            "lesson_id": m.lesson_id,
            "page_start": m.page_start,
            "page_end": m.page_end,
        }
        for m in request.mappings
    ]
    background_tasks.add_task(
        run_single_page_with_mapping,
        book_id,
        request.lesson_id,
        request.page_number,
        request.pdf_path,
        request.ocr_page_from,
        request.ocr_page_to,
        mappings_payload,
    )

    return OcrTriggerResult(
        status="ACCEPTED",
        message="Single-page OCR queued.",
        total_pages_queued=1,
    )


@router.post("/{book_id}/ocr-cancel")
async def cancel_ocr(book_id: str) -> dict:
    """Ask the background pipeline to stop cooperatively (Mongo cancel flag).

    Safe if no job exists — matched_count will be 0. The Java BE still resets
    Postgres book.status so the admin UI can unblock immediately."""
    matched = await book_repository.request_cancel(book_id)
    return {"accepted": True, "mongoMatched": matched}


@router.get("/{book_id}/ocr-status", response_model=OcrStatusResponse)
async def get_ocr_status(book_id: str) -> OcrStatusResponse:
    """The BE polls this to drive its `book.status` column."""
    state = await book_repository.get_by_id(book_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Book has no OCR run yet.")
    return OcrStatusResponse(
        status=state.status,
        processed_pages=state.processed_pages,
        total_pages=state.total_pages,
        error_message=state.error_message or None,
        progress_percent=state.progress,
        current_phase=state.current_phase or "",
    )


# ---------------------------------------------------------------------------
# Page reads
# ---------------------------------------------------------------------------


@router.get("/{book_id}/lessons/{lesson_id}/pages", response_model=List[LessonPageDB])
async def list_pages_by_book_and_lesson(
    book_id: str, lesson_id: str
) -> List[LessonPageDB]:
    return await lesson_page_repository.list_by_book_and_lesson(book_id, lesson_id)


@router.get(
    "/{book_id}/lessons/{lesson_id}/pages/{page_number}",
    response_model=LessonPageDB,
)
async def get_page(book_id: str, lesson_id: str, page_number: int) -> LessonPageDB:
    page = await lesson_page_repository.get_page(book_id, lesson_id, page_number)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    return page


@router.patch(
    "/{book_id}/lessons/{lesson_id}/pages/{page_number}",
    response_model=LessonPageDB,
)
async def update_page(
    book_id: str,
    lesson_id: str,
    page_number: int,
    request: UpdateLessonPageRequest,
    actor_id: Optional[str] = Query(default=None, alias="actor_id"),
) -> LessonPageDB:
    if request.content_blocks is None and request.verified is None:
        raise HTTPException(
            status_code=422,
            detail="At least one of content_blocks or verified must be set.",
        )
    updated = await lesson_page_repository.update_page(
        book_id, lesson_id, page_number, request, actor_id
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    return updated


@router.get(
    "/{book_id}/lessons/{lesson_id}/pages/{page_number}/history",
    response_model=List[PageHistoryEntry],
)
async def get_page_history(
    book_id: str,
    lesson_id: str,
    page_number: int,
    limit: int = Query(default=50, ge=1, le=200),
) -> List[PageHistoryEntry]:
    entries = await lesson_page_repository.list_page_history(
        book_id, lesson_id, page_number, limit=limit
    )
    return [
        PageHistoryEntry.model_validate(entry.model_dump(by_alias=False))
        for entry in entries
    ]


@router.delete("/{book_id}/pages")
async def delete_all_pages_for_book(book_id: str) -> dict:
    """Called when the BE soft-deletes a book — drops every OCR'd page."""
    deleted = await lesson_page_repository.delete_by_book(book_id)
    await book_repository.delete(book_id)
    return {"deleted": deleted}


@router.get("/{book_id}/verification", response_model=VerifyState)
async def get_book_verification(book_id: str) -> VerifyState:
    """Cheap rollup used to refresh the BE's `book.verified` cache. Returns
    `fully_verified=true` only when there's at least one page and every page
    has `verified=true`."""
    total, verified = await lesson_page_repository.count_pages_for_book(book_id)
    return VerifyState(
        fully_verified=total > 0 and total == verified,
        total_pages=total,
        verified_pages=verified,
    )


# ---------------------------------------------------------------------------
# Lesson-scoped (book-agnostic) — used by the Gemini prompt builder
# ---------------------------------------------------------------------------


lesson_scoped_router = APIRouter(prefix="/lessons", tags=["lesson-pages"])


@lesson_scoped_router.get("/{lesson_id}/pages", response_model=List[LessonPageDB])
async def list_pages_by_lesson(
    lesson_id: str,
    book_id: Optional[str] = Query(default=None, alias="book_id"),
) -> List[LessonPageDB]:
    return await lesson_page_repository.list_by_lesson(lesson_id, book_id=book_id)
