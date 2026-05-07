"""Pydantic models for the `lesson_pages` collection.

Each document represents one PDF page worth of OCR'd content for a specific
(book, lesson). The Postgres BE owns the lesson hierarchy; Mongo only stores
per-page content. Keys are stringified UUIDs from Postgres.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ContentBlock(BaseModel):
    """One OCR-extracted block within a page. Variable-shape — only the
    fields relevant to the block's `type` are populated. Mirrors
    `com.fptu.math_master.dto.response.ContentBlockDto` on the BE side."""

    order: Optional[int] = None
    type: Optional[str] = None
    content: Optional[str] = None
    latex: Optional[str] = None
    label: Optional[str] = None
    image_url: Optional[str] = Field(default=None, alias="imageUrl")
    image_path: Optional[str] = Field(default=None, alias="imagePath")
    thumbnail_url: Optional[str] = Field(default=None, alias="thumbnailUrl")
    caption: Optional[str] = None
    exercise_type: Optional[str] = Field(default=None, alias="exerciseType")
    exercise_num: Optional[str] = Field(default=None, alias="exerciseNum")
    confidence: Optional[float] = None
    source: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class LessonPageDB(BaseModel):
    """One OCR'd page document — what we read from `lesson_pages`."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    book_id: str = Field(alias="bookId")
    lesson_id: str = Field(alias="lessonId")
    page_number: int = Field(alias="pageNumber")
    content_blocks: List[ContentBlock] = Field(default_factory=list, alias="contentBlocks")
    raw_image_url: Optional[str] = Field(default=None, alias="rawImageUrl")
    ocr_confidence: Optional[float] = Field(default=None, alias="ocrConfidence")
    ocr_source: Optional[str] = Field(default=None, alias="ocrSource")
    verified: bool = False
    verified_by: Optional[str] = Field(default=None, alias="verifiedBy")
    verified_at: Optional[datetime] = Field(default=None, alias="verifiedAt")
    updated_at: Optional[datetime] = Field(default=None, alias="updatedAt")


class UpdateLessonPageRequest(BaseModel):
    """PATCH body — null fields = leave unchanged. Mirrors the BE DTO so the
    BE can pass it through without translation."""

    content_blocks: Optional[List[ContentBlock]] = Field(default=None, alias="contentBlocks")
    verified: Optional[bool] = None

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class MappingItem(BaseModel):
    """One lesson→page-range mapping in an OCR trigger request."""

    lesson_id: str = Field(alias="lessonId")
    page_start: int = Field(alias="pageStart", ge=1)
    page_end: int = Field(alias="pageEnd", ge=1)

    model_config = ConfigDict(populate_by_name=True)


class OcrTriggerRequest(BaseModel):
    """Request body for POST /books/{bookId}/ocr-with-mapping. Field names use
    camelCase so the Java BE's record (`OcrTriggerRequest`) round-trips
    cleanly without a custom ObjectMapper config."""

    book_id: str = Field(alias="bookId")
    pdf_path: str = Field(alias="pdfPath")
    ocr_page_from: int = Field(alias="ocrPageFrom", ge=1)
    ocr_page_to: int = Field(alias="ocrPageTo", ge=1)
    mappings: List[MappingItem]

    model_config = ConfigDict(populate_by_name=True)


class OcrTriggerResult(BaseModel):
    """Synchronous response — the actual work runs in a BackgroundTask."""

    status: str
    message: Optional[str] = None
    total_pages_queued: int = Field(alias="totalPagesQueued")

    model_config = ConfigDict(populate_by_name=True)


class OcrStatusResponse(BaseModel):
    """GET /books/{bookId}/ocr-status — what the BE polls."""

    status: str
    processed_pages: int = Field(alias="processedPages")
    total_pages: int = Field(alias="totalPages")
    error_message: Optional[str] = Field(default=None, alias="errorMessage")

    model_config = ConfigDict(populate_by_name=True)


class VerifyState(BaseModel):
    """GET /books/{bookId}/verification — quick summary for the BE's
    `book.verified` cache. `fully_verified` is true iff every saved page has
    `verified=true`."""

    fully_verified: bool = Field(alias="fullyVerified")
    total_pages: int = Field(alias="totalPages")
    verified_pages: int = Field(alias="verifiedPages")

    model_config = ConfigDict(populate_by_name=True)
