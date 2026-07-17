"""Knowledge-base QA directory request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class KnowledgeBaseQaDirectoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    parent_id: int | None = Field(default=None, ge=1)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Directory name must not be blank")
        return value


class KnowledgeBaseQaDirectoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    parent_id: int | None = Field(default=None, ge=1)
    sort_order: int | None = Field(default=None, ge=0)

    @field_validator("name", mode="before")
    @classmethod
    def strip_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Directory name must not be blank")
        return value


class KnowledgeBaseQaDirectoryResponse(BaseModel):
    id: int
    tenant_id: str
    knowledge_base_id: int
    parent_id: int | None
    name: str
    sort_order: int
    depth: int
    path: list[str]
    qa_count: int
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseQaDirectoryListResponse(BaseModel):
    items: list[KnowledgeBaseQaDirectoryResponse]
    total_qa_count: int
