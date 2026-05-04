from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class ContentBlockCreate(BaseModel):
    lesson_id: str
    order: int
    type: str
    content: str = ""
    label: str = ""          # for definition/example/exercise/heading
    latex: str = ""
    image_url: str = ""
    image_path: str = ""     # alternate field name used by OCR pipeline
    thumbnail_url: str = ""
    caption: str = ""
    exercise_type: str = ""
    exercise_num: int = 0
    confidence: float = 0.0
    source: str = "gemini"
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class ContentBlockDB(ContentBlockCreate):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
