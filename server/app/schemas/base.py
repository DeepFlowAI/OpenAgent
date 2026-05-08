from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TimestampSchema(BaseModel):
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaginatedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list
    total: int
    page: int
    per_page: int
    pages: int
