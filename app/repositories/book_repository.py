from app.core.mongo import mongo_db
from app.schemas.book import BookCreate, BookDB
from bson import ObjectId
from datetime import datetime, timezone
from typing import Optional


class BookRepository:
    def __init__(self):
        self.collection = mongo_db["books"]

    async def create(self, book: BookCreate, file_path: str) -> str:
        now = datetime.now(timezone.utc)
        doc = {
            **book.model_dump(),
            "status": "pending",
            "progress": 0,
            "current_phase": "",
            "total_pages": 0,
            "processed_pages": 0,
            "file_path": file_path,
            "error_message": "",
            "created_at": now,
            "updated_at": now,
            "gemini_calls": 0,
            "mathpix_calls": 0,
        }
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def get_by_id(self, book_id: str) -> Optional[BookDB]:
        try:
            doc = await self.collection.find_one({"_id": ObjectId(book_id)})
        except Exception:
            return None
        if doc is None:
            return None
        doc["_id"] = str(doc["_id"])
        return BookDB(**doc)

    async def list_all(self, grade: int = None, status: str = None) -> list[BookDB]:
        query = {}
        if grade is not None:
            query["grade"] = grade
        if status is not None:
            query["status"] = status
        cursor = self.collection.find(query).sort("created_at", -1)
        books = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            books.append(BookDB(**doc))
        return books

    async def update_status(
        self,
        book_id: str,
        status: str,
        progress: int = None,
        phase: str = None,
        error: str = "",
    ) -> None:
        update: dict = {
            "status": status,
            "updated_at": datetime.now(timezone.utc),
        }
        if progress is not None:
            update["progress"] = progress
        if phase is not None:
            update["current_phase"] = phase
        if error:
            update["error_message"] = error
        await self.collection.update_one(
            {"_id": ObjectId(book_id)}, {"$set": update}
        )

    async def update_total_pages(self, book_id: str, total_pages: int) -> None:
        await self.collection.update_one(
            {"_id": ObjectId(book_id)},
            {"$set": {"total_pages": total_pages, "updated_at": datetime.now(timezone.utc)}},
        )

    async def increment_processed_pages(self, book_id: str) -> None:
        await self.collection.update_one(
            {"_id": ObjectId(book_id)},
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
            {"_id": ObjectId(book_id)},
            {
                "$inc": inc,
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )

    async def delete(self, book_id: str) -> bool:
        result = await self.collection.delete_one({"_id": ObjectId(book_id)})
        return result.deleted_count == 1

    async def restore_with_id(self, book_id: str, book: BookCreate, file_path: str) -> str:
        """Re-insert a book record with a specific _id (e.g. after accidental delete)."""
        now = datetime.now(timezone.utc)
        doc = {
            "_id": ObjectId(book_id),
            **book.model_dump(),
            "status": "pending",
            "progress": 0,
            "current_phase": "",
            "total_pages": 0,
            "processed_pages": 0,
            "file_path": file_path,
            "error_message": "",
            "created_at": now,
            "updated_at": now,
            "gemini_calls": 0,
            "mathpix_calls": 0,
        }
        await self.collection.insert_one(doc)
        return book_id


book_repository = BookRepository()
