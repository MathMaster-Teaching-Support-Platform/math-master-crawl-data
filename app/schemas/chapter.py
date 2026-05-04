from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class ChapterCreate(BaseModel):
    book_id: str
    chapter_index: int
    roman_index: str = ""
    title: str
    page_start: int = 0
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class ChapterDB(ChapterCreate):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
