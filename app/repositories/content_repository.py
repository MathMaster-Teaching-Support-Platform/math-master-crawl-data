from app.core.mongo import mongo_db
from app.schemas.content import ContentBlockCreate, ContentBlockDB
from bson import ObjectId
from typing import Optional


class ContentRepository:
    def __init__(self):
        self.collection = mongo_db["lesson_contents"]

    async def create(self, block: ContentBlockCreate) -> str:
        doc = block.model_dump()
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def bulk_create(self, blocks: list[ContentBlockCreate]) -> list[str]:
        if not blocks:
            return []
        docs = [b.model_dump() for b in blocks]
        result = await self.collection.insert_many(docs)
        return [str(oid) for oid in result.inserted_ids]

    async def get_by_id(self, content_id: str) -> Optional[ContentBlockDB]:
        try:
            doc = await self.collection.find_one({"_id": ObjectId(content_id)})
        except Exception:
            return None
        if doc is None:
            return None
        doc["_id"] = str(doc["_id"])
        return ContentBlockDB(**doc)

    async def list_by_lesson(self, lesson_id: str) -> list[ContentBlockDB]:
        cursor = self.collection.find({"lesson_id": lesson_id}).sort("order", 1)
        blocks = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            blocks.append(ContentBlockDB(**doc))
        return blocks

    async def search_text(self, query: str, limit: int = 20) -> list[ContentBlockDB]:
        cursor = (
            self.collection.find(
                {"$text": {"$search": query}},
                {"score": {"$meta": "textScore"}},
            )
            .sort([("score", {"$meta": "textScore"})])
            .limit(limit)
        )
        blocks = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            doc.pop("score", None)
            blocks.append(ContentBlockDB(**doc))
        return blocks

    async def delete_by_lesson(self, lesson_id: str) -> int:
        result = await self.collection.delete_many({"lesson_id": lesson_id})
        return result.deleted_count

    async def delete(self, content_id: str) -> bool:
        result = await self.collection.delete_one({"_id": ObjectId(content_id)})
        return result.deleted_count == 1


content_repository = ContentRepository()
