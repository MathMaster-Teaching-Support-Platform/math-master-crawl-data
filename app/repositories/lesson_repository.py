from app.core.mongo import mongo_db
from app.schemas.lesson import LessonCreate, LessonDB
from bson import ObjectId
from typing import Optional


class LessonRepository:
    def __init__(self):
        self.collection = mongo_db["lessons"]

    async def create(self, lesson: LessonCreate) -> str:
        doc = lesson.model_dump()
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def get_by_id(self, lesson_id: str) -> Optional[LessonDB]:
        try:
            doc = await self.collection.find_one({"_id": ObjectId(lesson_id)})
        except Exception:
            return None
        if doc is None:
            return None
        doc["_id"] = str(doc["_id"])
        return LessonDB(**doc)

    async def list_by_chapter(self, chapter_id: str) -> list[LessonDB]:
        cursor = self.collection.find({"chapter_id": chapter_id}).sort("lesson_index", 1)
        lessons = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            lessons.append(LessonDB(**doc))
        return lessons

    async def delete_by_chapter(self, chapter_id: str) -> int:
        result = await self.collection.delete_many({"chapter_id": chapter_id})
        return result.deleted_count

    async def delete(self, lesson_id: str) -> bool:
        result = await self.collection.delete_one({"_id": ObjectId(lesson_id)})
        return result.deleted_count == 1

    async def delete_by_chapter_ids(self, chapter_ids: list[str]) -> int:
        if not chapter_ids:
            return 0
        result = await self.collection.delete_many({"chapter_id": {"$in": chapter_ids}})
        return result.deleted_count

    async def list_ids_by_chapter_ids(self, chapter_ids: list[str]) -> list[str]:
        if not chapter_ids:
            return []
        cursor = self.collection.find({"chapter_id": {"$in": chapter_ids}}, {"_id": 1})
        ids = []
        async for doc in cursor:
            ids.append(str(doc["_id"]))
        return ids


lesson_repository = LessonRepository()
