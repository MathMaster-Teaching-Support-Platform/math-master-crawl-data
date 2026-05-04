from app.core.mongo import mongo_db
from app.schemas.history import HistoryEntry
from typing import Optional
from datetime import datetime, timezone


class HistoryRepository:
    def __init__(self):
        self.collection = mongo_db["edit_history"]

    async def record(
        self,
        entity_type: str,
        entity_id: str,
        book_id: str,
        action: str,
        changed_by: str,
        before: Optional[dict] = None,
        after: Optional[dict] = None,
        summary: str = "",
    ) -> str:
        doc = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "book_id": book_id,
            "action": action,
            "changed_by": changed_by,
            "changed_at": datetime.now(timezone.utc).isoformat(),
            "before": before,
            "after": after,
            "summary": summary,
        }
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def list_by_entity(self, entity_id: str, limit: int = 50) -> list[HistoryEntry]:
        cursor = self.collection.find(
            {"entity_id": entity_id}
        ).sort("changed_at", -1).limit(limit)
        entries = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            entries.append(HistoryEntry(**doc))
        return entries

    async def list_by_book(self, book_id: str, limit: int = 100) -> list[HistoryEntry]:
        cursor = self.collection.find(
            {"book_id": book_id}
        ).sort("changed_at", -1).limit(limit)
        entries = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            entries.append(HistoryEntry(**doc))
        return entries


history_repository = HistoryRepository()
