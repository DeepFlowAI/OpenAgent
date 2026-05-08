"""
KnowledgeBase Pydantic schemas
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import TimestampSchema, PaginatedResponse


class KnowledgeBaseBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(None, max_length=256)
    git_url: str = Field(..., min_length=1, max_length=512)
    git_branch: str = Field("main", max_length=128)
    auth_type: str = Field("none", pattern=r"^(none|token)$")
    auth_token: str | None = None


class KnowledgeBaseCreate(KnowledgeBaseBase):
    tenant_id: str = Field(..., min_length=1, max_length=32)


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    description: str | None = Field(None, max_length=256)
    git_url: str | None = Field(None, min_length=1, max_length=512)
    git_branch: str | None = Field(None, max_length=128)
    auth_type: str | None = Field(None, pattern=r"^(none|token)$")
    auth_token: str | None = None


class KnowledgeBaseResponse(KnowledgeBaseBase, TimestampSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    last_synced_at: datetime | None = None
    document_count: int = 0
    status: str = "active"


class KnowledgeBaseListResponse(PaginatedResponse):
    items: list[KnowledgeBaseResponse]
