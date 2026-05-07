"""MongoDB access layer for the `lesson_pages` collection.

Ownership: pages are owned by Postgres (book + lesson UUIDs); Mongo stores
only the OCR'd content. The unique key is `(book_id, lesson_id, page_number)`
— the same physical PDF page can belong to two adjacent lessons when the
admin's mapping shares a single page boundary, so uniqueness is per-lesson,
not per-page.
"""

from datetime import datetime, timezone
from typing import List, Optional

from app.core.mongo import mongo_db
from app.schemas.lesson_page import ContentBlock, LessonPageDB, UpdateLessonPageRequest


class LessonPageRepository:
    def __init__(self) -> None:
        self.collection = mongo_db["lesson_pages"]

    # ---------------------------------------------------------------------
    # Writes
    # ---------------------------------------------------------------------

    async def upsert_page(
        self,
        book_id: str,
        lesson_id: str,
        page_number: int,
        content_blocks: List[ContentBlock],
        raw_image_url: Optional[str] = None,
        ocr_confidence: Optional[float] = None,
        ocr_source: Optional[str] = None,
    ) -> None:
        """Insert or replace one OCR'd page. Re-running OCR for the same
        (book, lesson, page) overwrites content but preserves verify state —
        an admin's manual verification shouldn't get blown away by a re-OCR."""
        now = datetime.now(timezone.utc)
        await self.collection.update_one(
            {"book_id": book_id, "lesson_id": lesson_id, "page_number": page_number},
            {
                "$set": {
                    "content_blocks": [b.model_dump(by_alias=False, exclude_none=True) for b in content_blocks],
                    "raw_image_url": raw_image_url,
                    "ocr_confidence": ocr_confidence,
                    "ocr_source": ocr_source,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "book_id": book_id,
                    "lesson_id": lesson_id,
                    "page_number": page_number,
                    "verified": False,
                    "verified_by": None,
                    "verified_at": None,
                },
            },
            upsert=True,
        )

    async def update_page(
        self,
        book_id: str,
        lesson_id: str,
        page_number: int,
        request: UpdateLessonPageRequest,
        actor_id: Optional[str],
    ) -> Optional[LessonPageDB]:
        """Apply a partial update from the verify wizard. Null fields are left
        unchanged so the FE can flip just `verified` without resending the
        whole content array."""
        now = datetime.now(timezone.utc)
        update: dict = {"updated_at": now}

        if request.content_blocks is not None:
            update["content_blocks"] = [
                b.model_dump(by_alias=False, exclude_none=True) for b in request.content_blocks
            ]

        if request.verified is not None:
            update["verified"] = request.verified
            if request.verified:
                update["verified_by"] = actor_id
                update["verified_at"] = now
            else:
                update["verified_by"] = None
                update["verified_at"] = None

        result = await self.collection.find_one_and_update(
            {"book_id": book_id, "lesson_id": lesson_id, "page_number": page_number},
            {"$set": update},
            return_document=True,
        )
        return self._to_model(result)

    async def delete_by_book(self, book_id: str) -> int:
        """Drop every page for a book — called when the BE deletes a book."""
        result = await self.collection.delete_many({"book_id": book_id})
        return result.deleted_count

    async def delete_by_book_and_lesson(self, book_id: str, lesson_id: str) -> int:
        """Drop every page for a (book, lesson) — used before a re-OCR run so
        stale pages from a previous mapping don't linger."""
        result = await self.collection.delete_many(
            {"book_id": book_id, "lesson_id": lesson_id}
        )
        return result.deleted_count

    # ---------------------------------------------------------------------
    # Reads
    # ---------------------------------------------------------------------

    async def get_page(
        self, book_id: str, lesson_id: str, page_number: int
    ) -> Optional[LessonPageDB]:
        doc = await self.collection.find_one(
            {"book_id": book_id, "lesson_id": lesson_id, "page_number": page_number}
        )
        return self._to_model(doc)

    async def list_by_book_and_lesson(
        self, book_id: str, lesson_id: str
    ) -> List[LessonPageDB]:
        cursor = self.collection.find(
            {"book_id": book_id, "lesson_id": lesson_id}
        ).sort("page_number", 1)
        return [self._to_model(d) for d in await cursor.to_list(length=None) if d]

    async def list_by_lesson(
        self, lesson_id: str, book_id: Optional[str] = None
    ) -> List[LessonPageDB]:
        query: dict = {"lesson_id": lesson_id}
        if book_id:
            query["book_id"] = book_id
        cursor = self.collection.find(query).sort([("book_id", 1), ("page_number", 1)])
        return [self._to_model(d) for d in await cursor.to_list(length=None) if d]

    async def count_pages_for_book(self, book_id: str) -> tuple[int, int]:
        """Returns (total_pages, verified_pages) for the book — used for the
        BE's verification rollup. Distinct-page count would double-count
        pages shared across two lessons; that's intentional, since each
        (lesson, page) needs to be verified separately."""
        pipeline = [
            {"$match": {"book_id": book_id}},
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "verified": {"$sum": {"$cond": ["$verified", 1, 0]}},
                }
            },
        ]
        async for doc in self.collection.aggregate(pipeline):
            return int(doc.get("total", 0)), int(doc.get("verified", 0))
        return 0, 0

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    @staticmethod
    def _to_model(doc: Optional[dict]) -> Optional[LessonPageDB]:
        if doc is None:
            return None
        # Mongo's `_id` is an ObjectId (auto-generated). We expose it as a
        # string so the JSON envelope is friendly to the BE; the BE only ever
        # round-trips it as `id` and never queries by it.
        doc = dict(doc)
        doc["_id"] = str(doc.get("_id"))
        return LessonPageDB.model_validate(doc)


lesson_page_repository = LessonPageRepository()
