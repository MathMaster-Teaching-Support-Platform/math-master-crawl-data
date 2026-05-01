from pydantic import BaseModel, Field
from typing import Optional


class LessonCreate(BaseModel):
    chapter_id: str
    lesson_index: int
    title: str
    page_start: int = 0


class LessonDB(LessonCreate):
    id: str = Field(alias="_id")
