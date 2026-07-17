"""Knowledge-base QA request and response schemas."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ACCESS_KEYWORD_RE = re.compile(r"^[A-Za-z0-9_]+$")


def normalize_access_keywords(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.strip().lower()
        if not value or not _ACCESS_KEYWORD_RE.fullmatch(value):
            raise ValueError(
                "Access keywords may contain only ASCII letters, numbers, and underscores"
            )
        if value not in seen:
            normalized.append(value)
            seen.add(value)
    if len(normalized) > 50:
        raise ValueError("Access keywords may contain at most 50 items")
    return normalized


class KnowledgeBaseQaCreate(BaseModel):
    directory_id: int = Field(ge=1)
    question: str = Field(min_length=1, max_length=500)
    answer_markdown: str = Field(min_length=1, max_length=7000)
    access_keywords: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("question", "answer_markdown", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("access_keywords")
    @classmethod
    def validate_access_keywords(cls, value: list[str]) -> list[str]:
        return normalize_access_keywords(value)


class KnowledgeBaseQaUpdate(BaseModel):
    directory_id: int | None = Field(default=None, ge=1)
    question: str | None = Field(default=None, min_length=1, max_length=500)
    answer_markdown: str | None = Field(default=None, min_length=1, max_length=7000)
    access_keywords: list[str] | None = None
    enabled: bool | None = None

    @field_validator("question", "answer_markdown", mode="before")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("access_keywords")
    @classmethod
    def validate_optional_access_keywords(
        cls, value: list[str] | None
    ) -> list[str] | None:
        return normalize_access_keywords(value) if value is not None else None

    @model_validator(mode="after")
    def reject_explicit_null_directory(self) -> "KnowledgeBaseQaUpdate":
        if "directory_id" in self.model_fields_set and self.directory_id is None:
            raise ValueError("Directory must not be null")
        return self


class KnowledgeBaseQaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    knowledge_base_id: int
    directory_id: int
    directory_path: list[str]
    question: str
    answer_markdown: str
    enabled: bool
    access_keywords: list[str]
    process_status: Literal["processing", "ready", "failed"]
    process_error: str | None
    document_id: int | None
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseQaListResponse(BaseModel):
    items: list[KnowledgeBaseQaResponse]
    total: int
    page: int
    per_page: int
    pages: int
