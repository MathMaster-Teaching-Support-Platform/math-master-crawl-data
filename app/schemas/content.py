from pydantic import BaseModel, Field
from typing import Optional


class ContentBlockCreate(BaseModel):
    lesson_id: str
    order: int
    type: str
    content: str = ""
    latex: str = ""
    image_url: str = ""
    thumbnail_url: str = ""
    caption: str = ""
    exercise_type: str = ""
    exercise_num: int = 0
    confidence: float = 0.0
    source: str = "gemini"


class ContentBlockDB(ContentBlockCreate):
    id: str = Field(alias="_id")
