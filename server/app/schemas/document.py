"""
Document & Slice query schemas
"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import PaginatedResponse


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_base_id: int
    tenant_id: str
    title: str | None = None
    description: str | None = None
    file_path: str
    source_url: str | None = None
    markdown_content: str | None = None
    doc_meta: dict[str, Any] | None = None
    toc: list[dict] | None = None
    slice_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentListResponse(PaginatedResponse):
    items: list[DocumentResponse]


class PublicDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_path: str
    title: str | None = None
    slice_count: int = 0
    updated_at: datetime | None = None
    doc_meta: dict[str, Any] | None = None
    markdown_url: str


class PublicDocumentListResponse(PaginatedResponse):
    items: list[PublicDocumentResponse]


class SliceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    knowledge_base_id: int
    content: str
    content_for_search: str | None = None
    toc_path: list[str] | None = None
    slice_meta: dict[str, Any] | None = None
    doc_meta: dict[str, Any] | None = None
    source_url: str | None = None
    markdown_url: str | None = None
    slice_order: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SliceListResponse(PaginatedResponse):
    items: list[SliceResponse]


class SyncLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_base_id: int
    tenant_id: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    total_files: int | None = None
    success_count: int | None = None
    error_count: int | None = None
    details: dict | list[dict] | None = None


class SyncLogListResponse(PaginatedResponse):
    items: list[SyncLogResponse]


DocumentQueryReason = Literal[
    "document_not_found",
    "slice_not_found",
    "line_not_found",
    "invalid_parameter",
]


class DocumentQueryRequest(BaseModel):
    doc_id: int = Field(..., gt=0)
    slice_id: int | None = Field(None, gt=0)
    line: int | None = Field(None, gt=0)


class DocumentQueryDocument(BaseModel):
    id: int
    knowledge_base_id: int
    title: str | None = None
    file_path: str
    doc_meta: dict[str, Any] | None = None
    markdown_url: str
    document_url: str


class DocumentQuerySlice(BaseModel):
    id: int
    content: str
    toc_path: list[str] | None = None
    slice_order: int = 0
    slice_meta: dict[str, Any] | None = None


class DocumentQueryResponse(BaseModel):
    resolved: bool
    reason: DocumentQueryReason | None = None
    doc_id: int
    slice_id: int | None = None
    line: int | None = None
    document: DocumentQueryDocument | None = None
    slice: DocumentQuerySlice | None = None
    line_text: str | None = None
    line_count: int | None = None
