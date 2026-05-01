from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class LessonCreate(BaseModel):
    chapter_id: str
    lesson_index: int
    title: str
    page_start: int = 0


class LessonDB(LessonCreate):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
