from pydantic import BaseModel, Field
from typing import Optional


class ChapterCreate(BaseModel):
    book_id: str
    chapter_index: int
    roman_index: str = ""
    title: str
    page_start: int = 0


class ChapterDB(ChapterCreate):
    id: str = Field(alias="_id")
