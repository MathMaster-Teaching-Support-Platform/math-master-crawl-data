from app.core.mongo import mongo_db
from app.schemas.chapter import ChapterCreate, ChapterDB
from bson import ObjectId
from typing import Optional


class ChapterRepository:
    def __init__(self):
        self.collection = mongo_db["chapters"]

    async def create(self, chapter: ChapterCreate) -> str:
        doc = chapter.model_dump()
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def get_by_id(self, chapter_id: str) -> Optional[ChapterDB]:
        try:
            doc = await self.collection.find_one({"_id": ObjectId(chapter_id)})
        except Exception:
            return None
        if doc is None:
            return None
        doc["_id"] = str(doc["_id"])
        return ChapterDB(**doc)

    async def list_by_book(self, book_id: str) -> list[ChapterDB]:
        cursor = self.collection.find({"book_id": book_id}).sort("chapter_index", 1)
        chapters = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            chapters.append(ChapterDB(**doc))
        return chapters

    async def delete_by_book(self, book_id: str) -> int:
        result = await self.collection.delete_many({"book_id": book_id})
        return result.deleted_count

    async def delete(self, chapter_id: str) -> bool:
        result = await self.collection.delete_one({"_id": ObjectId(chapter_id)})
        return result.deleted_count == 1


chapter_repository = ChapterRepository()
