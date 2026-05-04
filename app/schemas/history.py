from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class HistoryEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    entity_type: str   # "chapter" | "lesson" | "content"
    entity_id: str
    book_id: str
    action: str        # "create" | "update" | "delete"
    changed_by: str
    changed_at: str    # ISO datetime string
    before: Optional[dict] = None
    after: Optional[dict] = None
    summary: str = ""
