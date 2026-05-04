from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


class BookCreate(BaseModel):
    title: str
    grade: int = Field(..., ge=1, le=12)
    publisher: str = ""
    academic_year: str = ""


class BookDB(BookCreate):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    status: str = "pending"
    progress: int = 0
    current_phase: str = ""
    total_pages: int = 0
    processed_pages: int = 0
    file_path: str = ""
    error_message: str = ""
    created_at: datetime
    updated_at: datetime
    gemini_calls: int = 0
    mathpix_calls: int = 0
    thumbnail_url: str = ""
