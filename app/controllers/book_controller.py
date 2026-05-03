import json
import os
import shutil
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.core.config import settings
from app.repositories.book_repository import book_repository
from app.repositories.chapter_repository import chapter_repository
from app.repositories.content_repository import content_repository
from app.repositories.lesson_repository import lesson_repository
from app.schemas.book import BookCreate, BookDB
from app.services.processing_pipeline import run_pipeline, reprocess_from_cache
from app.utils.response import success_response

router = APIRouter(prefix="/books", tags=["books"])

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class BookSummary(BaseModel):
    id: str
    title: str
    grade: int
    publisher: str
    academic_year: str
    status: str
    progress: int
    total_pages: int
    processed_pages: int
    created_at: str


class BookDetail(BookSummary):
    current_phase: str
    file_path: str
    error_message: str
    gemini_calls: int
    mathpix_calls: int
    updated_at: str


class BookStatusResponse(BaseModel):
    status: str
    progress: int
    current_phase: str
    processed_pages: int
    total_pages: int


def _to_summary(book: BookDB) -> BookSummary:
    return BookSummary(
        id=book.id,
        title=book.title,
        grade=book.grade,
        publisher=book.publisher,
        academic_year=book.academic_year,
        status=book.status,
        progress=book.progress,
        total_pages=book.total_pages,
        processed_pages=book.processed_pages,
        created_at=book.created_at.isoformat(),
    )


def _to_detail(book: BookDB) -> BookDetail:
    return BookDetail(
        id=book.id,
        title=book.title,
        grade=book.grade,
        publisher=book.publisher,
        academic_year=book.academic_year,
        status=book.status,
        progress=book.progress,
        total_pages=book.total_pages,
        processed_pages=book.processed_pages,
        current_phase=book.current_phase,
        file_path=book.file_path,
        error_message=book.error_message,
        gemini_calls=book.gemini_calls,
        mathpix_calls=book.mathpix_calls,
        created_at=book.created_at.isoformat(),
        updated_at=book.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_book(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    grade: int = Form(..., ge=1, le=12),
    publisher: str = Form(default=""),
    title: str = Form(...),
    academic_year: str = Form(default=""),
):
    """Upload a PDF and start background processing."""
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Validate file size
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.max_file_size_mb} MB.",
        )

    # Create book record first (to get book_id)
    book_data = BookCreate(
        title=title,
        grade=grade,
        publisher=publisher,
        academic_year=academic_year,
    )
    # Temporary placeholder path; we update after we know the book_id
    book_id = await book_repository.create(book_data, file_path="")

    # Save PDF to storage
    book_dir = os.path.join("data", "books", book_id)
    os.makedirs(book_dir, exist_ok=True)
    pdf_path = os.path.join(book_dir, "original.pdf")
    with open(pdf_path, "wb") as f:
        f.write(contents)

    # Update file_path in DB
    from bson import ObjectId
    from datetime import datetime, timezone
    await book_repository.collection.update_one(
        {"_id": ObjectId(book_id)},
        {"$set": {"file_path": pdf_path, "updated_at": datetime.now(timezone.utc)}},
    )

    # Trigger background processing
    background_tasks.add_task(run_pipeline, book_id, pdf_path)

    return success_response(
        data={"book_id": book_id, "status": "pending"},
        message="Book uploaded. Processing started.",
    )


@router.get("/")
async def list_books(grade: Optional[int] = None, status: Optional[str] = None):
    """List all books, optionally filtered by grade and/or status."""
    books = await book_repository.list_all(grade=grade, status=status)
    return success_response(data=[_to_summary(b) for b in books])


@router.get("/{book_id}/status")
async def get_book_status(book_id: str):
    """Return real-time processing status (for frontend polling)."""
    book = await book_repository.get_by_id(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found.")
    return success_response(
        data=BookStatusResponse(
            status=book.status,
            progress=book.progress,
            current_phase=book.current_phase,
            processed_pages=book.processed_pages,
            total_pages=book.total_pages,
        )
    )


@router.get("/{book_id}/chapters")
async def get_book_chapters(book_id: str):
    """List all chapters belonging to a book."""
    book = await book_repository.get_by_id(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found.")
    chapters = await chapter_repository.list_by_book(book_id)
    data = [
        {
            "id": c.id,
            "book_id": c.book_id,
            "chapter_index": c.chapter_index,
            "roman_index": c.roman_index,
            "title": c.title,
            "page_start": c.page_start,
        }
        for c in chapters
    ]
    return success_response(data=data)


@router.get("/{book_id}/export/json")
async def export_book_json(book_id: str):
    """Export the full book tree as JSON."""
    book = await book_repository.get_by_id(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found.")

    chapters = await chapter_repository.list_by_book(book_id)
    result = {
        "id": book.id,
        "title": book.title,
        "grade": book.grade,
        "publisher": book.publisher,
        "academic_year": book.academic_year,
        "chapters": [],
    }

    for chap in chapters:
        lessons = await lesson_repository.list_by_chapter(chap.id)
        chap_data = {
            "id": chap.id,
            "chapter_index": chap.chapter_index,
            "roman_index": chap.roman_index,
            "title": chap.title,
            "lessons": [],
        }
        for les in lessons:
            blocks = await content_repository.list_by_lesson(les.id)
            lesson_data = {
                "id": les.id,
                "lesson_index": les.lesson_index,
                "title": les.title,
                "content_blocks": [
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
                        "source": b.source,
                    }
                    for b in blocks
                ],
            }
            chap_data["lessons"].append(lesson_data)
        result["chapters"].append(chap_data)

    return success_response(data=result)


@router.get("/{book_id}/export/md", response_class=PlainTextResponse)
async def export_book_markdown(book_id: str):
    """Export the full book tree as Markdown."""
    book = await book_repository.get_by_id(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found.")

    lines: list[str] = [f"# [Lớp {book.grade}] {book.title} — {book.publisher}", ""]
    chapters = await chapter_repository.list_by_book(book_id)

    for chap in chapters:
        lines.append(f"## Chương {chap.roman_index or chap.chapter_index}: {chap.title}")
        lines.append("")
        lessons = await lesson_repository.list_by_chapter(chap.id)

        for les in lessons:
            lines.append(f"### {les.title}")
            lines.append("")
            blocks = await content_repository.list_by_lesson(les.id)

            for b in blocks:
                if b.type == "formula":
                    if b.content:
                        lines.append(b.content)
                    if b.latex:
                        lines.append(f"$${b.latex}$$")
                elif b.type == "image":
                    caption = b.caption or ""
                    lines.append(f"![{caption}]({b.image_url})")
                elif b.type in ("exercise", "definition", "note"):
                    prefix_map = {
                        "exercise": "**Bài tập:**",
                        "definition": "**Định nghĩa:**",
                        "note": "**Ghi nhớ:**",
                    }
                    if b.exercise_type:
                        lines.append(f"**{b.exercise_type.replace('_', ' ').title()}:**")
                    else:
                        lines.append(prefix_map.get(b.type, ""))
                    if b.content:
                        lines.append(b.content)
                else:
                    if b.content:
                        lines.append(b.content)
                lines.append("")

    return "\n".join(lines)


@router.get("/{book_id}/export/chunks")
async def export_book_chunks(book_id: str):
    """Export book as RAG-ready chunks with metadata."""
    book = await book_repository.get_by_id(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found.")

    chunks: list[dict] = []
    chapters = await chapter_repository.list_by_book(book_id)

    for chap in chapters:
        lessons = await lesson_repository.list_by_chapter(chap.id)
        for les in lessons:
            blocks = await content_repository.list_by_lesson(les.id)
            for b in blocks:
                text_parts = [
                    f"[Lớp {book.grade}]",
                    f"[Chương {chap.roman_index or chap.chapter_index}]",
                    f"[{les.title}]",
                ]
                if b.content:
                    text_parts.append(b.content)
                if b.latex:
                    text_parts.append(b.latex)
                chunk_id = f"book{book.grade}_ch{chap.chapter_index}_l{les.lesson_index}_c{b.order:03d}"
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "text": " ".join(text_parts),
                        "metadata": {
                            "grade": book.grade,
                            "chapter": f"Chương {chap.roman_index or chap.chapter_index}",
                            "lesson": les.title,
                            "type": b.type,
                            "source": b.source,
                        },
                    }
                )

    return success_response(data=chunks)


@router.get("/{book_id}")
async def get_book(book_id: str):
    """Return full book detail including stats."""
    book = await book_repository.get_by_id(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found.")
    return success_response(data=_to_detail(book))


@router.delete("/{book_id}")
async def delete_book(book_id: str):
    """Delete a book and all associated data including storage files."""
    book = await book_repository.get_by_id(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found.")

    # Delete contents → lessons → chapters → book (cascade)
    chapters = await chapter_repository.list_by_book(book_id)
    for chap in chapters:
        lessons = await lesson_repository.list_by_chapter(chap.id)
        for les in lessons:
            await content_repository.delete_by_lesson(les.id)
        await lesson_repository.delete_by_chapter(chap.id)
    await chapter_repository.delete_by_book(book_id)
    await book_repository.delete(book_id)

    # Remove storage directory
    book_storage_dir = os.path.join(settings.storage_path, "images", book_id)
    if os.path.isdir(book_storage_dir):
        shutil.rmtree(book_storage_dir, ignore_errors=True)

    return success_response(data={"deleted": book_id}, message="Book deleted.")


@router.post("/{book_id}/reprocess")
async def reprocess_book(
    book_id: str,
    background_tasks: BackgroundTasks,
    title: str = "",
    grade: int = 0,
    publisher: str = "",
    academic_year: str = "",
    file_path: str = "",
):
    """Re-run STEP 3+4 (parse + save) using cached page_analyses.
    Use this when the pipeline failed after Gemini OCR was already completed.
    Pass title/grade/publisher/academic_year/file_path if the book record was deleted.
    """
    cache_path = os.path.join("data", "books", book_id, "page_analyses.json")
    if not os.path.exists(cache_path):
        raise HTTPException(
            status_code=404,
            detail=f"No cache found for book_id={book_id}. You must upload the PDF first.",
        )
    # If book exists, reset its status so polling works
    book = await book_repository.get_by_id(book_id)
    if book is not None:
        await book_repository.update_status(book_id, "processing", 80, "reprocessing")

    meta_override = {"title": title, "grade": grade, "publisher": publisher, "academic_year": academic_year, "file_path": file_path}
    background_tasks.add_task(reprocess_from_cache, book_id, meta_override)
    return success_response(
        data={"book_id": book_id, "status": "reprocessing"},
        message="Reprocessing started from cache (STEP 3+4 only).",
    )
