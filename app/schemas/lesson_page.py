"""Pydantic models for the `lesson_pages` collection.

Each document represents one PDF page worth of OCR'd content for a specific
(book, lesson). The Postgres BE owns the lesson hierarchy; Mongo only stores
per-page content. Keys are stringified UUIDs from Postgres.
"""

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class ContentBlock(BaseModel):
    """One OCR-extracted block within a page. Variable-shape — only the
    fields relevant to the block's `type` are populated. Mirrors
    `com.fptu.math_master.dto.response.ContentBlockDto` on the BE side."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    order: Optional[int] = None
    type: Optional[str] = None
    content: Optional[str] = None
    latex: Optional[str] = None
    label: Optional[str] = None
    image_url: Optional[str] = Field(default=None, validation_alias="imageUrl", serialization_alias="imageUrl")
    image_path: Optional[str] = Field(default=None, validation_alias="imagePath", serialization_alias="imagePath")
    thumbnail_url: Optional[str] = Field(default=None, validation_alias="thumbnailUrl", serialization_alias="thumbnailUrl")
    caption: Optional[str] = None
    exercise_type: Optional[str] = Field(default=None, validation_alias="exerciseType", serialization_alias="exerciseType")
    exercise_num: Optional[str] = Field(default=None, validation_alias="exerciseNum", serialization_alias="exerciseNum")
    confidence: Optional[float] = None
    source: Optional[str] = None


class LessonPageDB(BaseModel):
    """One OCR'd page document — what we read from `lesson_pages`."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(validation_alias="_id", serialization_alias="_id")
    book_id: str = Field(validation_alias="bookId", serialization_alias="bookId")
    lesson_id: str = Field(validation_alias="lessonId", serialization_alias="lessonId")
    page_number: int = Field(validation_alias="pageNumber", serialization_alias="pageNumber")
    content_blocks: List[ContentBlock] = Field(
        default_factory=list,
        validation_alias="contentBlocks",
        serialization_alias="contentBlocks",
    )
    raw_image_url: Optional[str] = Field(default=None, validation_alias="rawImageUrl", serialization_alias="rawImageUrl")
    ocr_confidence: Optional[float] = Field(default=None, validation_alias="ocrConfidence", serialization_alias="ocrConfidence")
    ocr_source: Optional[str] = Field(default=None, validation_alias="ocrSource", serialization_alias="ocrSource")
    verified: bool = False
    verified_by: Optional[str] = Field(default=None, validation_alias="verifiedBy", serialization_alias="verifiedBy")
    verified_at: Optional[datetime] = Field(default=None, validation_alias="verifiedAt", serialization_alias="verifiedAt")
    updated_at: Optional[datetime] = Field(default=None, validation_alias="updatedAt", serialization_alias="updatedAt")

    @field_serializer("verified_at", "updated_at", when_used="json")
    def _serialize_instant_utc_z(self, value: Optional[datetime]) -> Optional[str]:
        """Java `Instant` expects ISO-8601 instant form (…Z or offset). Naive
        datetimes from Mongo are treated as UTC."""
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat().replace("+00:00", "Z")


class UpdateLessonPageRequest(BaseModel):
    """PATCH body — null fields = leave unchanged. Mirrors the BE DTO so the
    BE can pass it through without translation."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    content_blocks: Optional[List[ContentBlock]] = Field(
        default=None,
        validation_alias="contentBlocks",
        serialization_alias="contentBlocks",
    )
    verified: Optional[bool] = None


class PageHistoryEntry(BaseModel):
    """One persisted edit-history entry for a lesson page."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(validation_alias="_id", serialization_alias="_id")
    entity_type: str = Field(validation_alias="entity_type", serialization_alias="entityType")
    entity_id: str = Field(validation_alias="entity_id", serialization_alias="entityId")
    book_id: str = Field(validation_alias="book_id", serialization_alias="bookId")
    action: str
    changed_by: str = Field(validation_alias="changed_by", serialization_alias="changedBy")
    changed_at: str = Field(validation_alias="changed_at", serialization_alias="changedAt")
    before: Optional[dict] = None
    after: Optional[dict] = None
    summary: str = ""


class MappingItem(BaseModel):
    """One lesson→page-range mapping in an OCR trigger request."""

    model_config = ConfigDict(populate_by_name=True)

    lesson_id: str = Field(validation_alias="lessonId", serialization_alias="lessonId")
    page_start: int = Field(ge=1, validation_alias="pageStart", serialization_alias="pageStart")
    page_end: int = Field(ge=1, validation_alias="pageEnd", serialization_alias="pageEnd")


class OcrTriggerRequest(BaseModel):
    """Request body for POST /books/{bookId}/ocr-with-mapping. Field names use
    camelCase so the Java BE's record (`OcrTriggerRequest`) round-trips
    cleanly without a custom ObjectMapper config."""

    model_config = ConfigDict(populate_by_name=True)

    book_id: str = Field(validation_alias="bookId", serialization_alias="bookId")
    pdf_path: str = Field(validation_alias="pdfPath", serialization_alias="pdfPath")
    ocr_page_from: int = Field(ge=1, validation_alias="ocrPageFrom", serialization_alias="ocrPageFrom")
    ocr_page_to: int = Field(ge=1, validation_alias="ocrPageTo", serialization_alias="ocrPageTo")
    mappings: List[MappingItem]


class OcrTriggerResult(BaseModel):
    """Synchronous response — the actual work runs in a BackgroundTask."""

    model_config = ConfigDict(populate_by_name=True)

    status: str
    message: Optional[str] = None
    total_pages_queued: int = Field(validation_alias="totalPagesQueued", serialization_alias="totalPagesQueued")


class OcrStatusResponse(BaseModel):
    """GET /books/{bookId}/ocr-status — what the BE polls."""

    model_config = ConfigDict(populate_by_name=True)

    status: str
    processed_pages: int = Field(validation_alias="processedPages", serialization_alias="processedPages")
    total_pages: int = Field(validation_alias="totalPages", serialization_alias="totalPages")
    error_message: Optional[str] = Field(
        default=None,
        validation_alias="errorMessage",
        serialization_alias="errorMessage",
    )
    progress_percent: int = Field(
        default=0,
        validation_alias="progressPercent",
        serialization_alias="progressPercent",
    )
    current_phase: str = Field(
        default="",
        validation_alias="currentPhase",
        serialization_alias="currentPhase",
    )


class VerifyState(BaseModel):
    """GET /books/{bookId}/verification — quick summary for the BE's
    `book.verified` cache. `fully_verified` is true iff every saved page has
    `verified=true`."""

    model_config = ConfigDict(populate_by_name=True)

    fully_verified: bool = Field(validation_alias="fullyVerified", serialization_alias="fullyVerified")
    total_pages: int = Field(validation_alias="totalPages", serialization_alias="totalPages")
    verified_pages: int = Field(validation_alias="verifiedPages", serialization_alias="verifiedPages")
