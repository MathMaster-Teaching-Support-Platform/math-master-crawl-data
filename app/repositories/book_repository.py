"""OCR job state per book.

After the Phase 3 refactor Postgres owns book metadata (title/grade/...);
Mongo only tracks the OCR pipeline's state for a given book. The `_id` is
the Postgres book UUID, stored as a string — no ObjectId conversion.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.mongo import mongo_db


class BookOcrState(BaseModel):
    """Mongo's view of a book — purely OCR pipeline state."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    status: str = "pending"  # pending | processing | done | error
    progress: int = 0
    current_phase: str = ""
    total_pages: int = 0
    processed_pages: int = 0
    pdf_path: str = ""
    ocr_page_from: int = 0
    ocr_page_to: int = 0
    error_message: str = ""
    gemini_calls: int = 0
    mathpix_calls: int = 0
    created_at: datetime
    updated_at: datetime


class BookRepository:
    def __init__(self) -> None:
        self.collection = mongo_db["books"]

    async def upsert_for_ocr(
        self,
        book_id: str,
        pdf_path: str,
        ocr_page_from: int,
        ocr_page_to: int,
    ) -> None:
        """Initialize (or reset) the OCR job row for a book. Called at the top
        of `ocr-with-mapping` so a re-trigger replays cleanly: counters reset,
        status returns to `pending`, error clears."""
        now = datetime.now(timezone.utc)
        await self.collection.update_one(
            {"_id": book_id},
            {
                "$set": {
                    "status": "pending",
                    "progress": 0,
                    "current_phase": "",
                    "processed_pages": 0,
                    "pdf_path": pdf_path,
                    "ocr_page_from": ocr_page_from,
                    "ocr_page_to": ocr_page_to,
                    "error_message": "",
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "_id": book_id,
                    "total_pages": 0,
                    "gemini_calls": 0,
                    "mathpix_calls": 0,
                    "created_at": now,
                },
            },
            upsert=True,
        )

    async def get_by_id(self, book_id: str) -> Optional[BookOcrState]:
        doc = await self.collection.find_one({"_id": book_id})
        if doc is None:
            return None
        return BookOcrState.model_validate(doc)

    async def update_status(
        self,
        book_id: str,
        status: str,
        progress: Optional[int] = None,
        phase: Optional[str] = None,
        error: str = "",
    ) -> None:
        update: dict = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if progress is not None:
            update["progress"] = progress
        if phase is not None:
            update["current_phase"] = phase
        if error:
            update["error_message"] = error
        await self.collection.update_one({"_id": book_id}, {"$set": update})

    async def update_total_pages(self, book_id: str, total_pages: int) -> None:
        await self.collection.update_one(
            {"_id": book_id},
            {"$set": {"total_pages": total_pages, "updated_at": datetime.now(timezone.utc)}},
        )

    async def increment_processed_pages(self, book_id: str) -> None:
        await self.collection.update_one(
            {"_id": book_id},
            {
                "$inc": {"processed_pages": 1},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )

    async def increment_api_calls(
        self, book_id: str, gemini: int = 0, mathpix: int = 0
    ) -> None:
        inc: dict = {}
        if gemini:
            inc["gemini_calls"] = gemini
        if mathpix:
            inc["mathpix_calls"] = mathpix
        if not inc:
            return
        await self.collection.update_one(
            {"_id": book_id},
            {"$inc": inc, "$set": {"updated_at": datetime.now(timezone.utc)}},
        )

    async def delete(self, book_id: str) -> bool:
        result = await self.collection.delete_one({"_id": book_id})
        return result.deleted_count == 1


book_repository = BookRepository()
