"""Knowledge-base QA management router."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import (
    AuthContext,
    get_db,
    require_admin_session_or_scope,
    require_user_session_or_scope,
)
from app.schemas.knowledge_base_qa import (
    KnowledgeBaseQaCreate,
    KnowledgeBaseQaListResponse,
    KnowledgeBaseQaResponse,
    KnowledgeBaseQaUpdate,
)
from app.services.knowledge_base_qa_service import KnowledgeBaseQaService

router = APIRouter(
    prefix="/knowledge-bases/{kb_id}/qas",
    tags=["KnowledgeBaseQAs"],
)

require_qa_read = require_user_session_or_scope("config")
require_qa_write = require_admin_session_or_scope("config")


@router.get("", response_model=KnowledgeBaseQaListResponse)
async def list_qas(
    kb_id: int,
    search: str | None = Query(default=None, max_length=7000),
    enabled: bool | None = None,
    process_status: Literal["processing", "ready", "failed"] | None = None,
    directory_id: int | None = Query(default=None, ge=1),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    auth: AuthContext = Depends(require_qa_read),
    db: AsyncSession = Depends(get_db),
):
    return await KnowledgeBaseQaService.list_paginated(
        db,
        auth.tenant_id,
        kb_id,
        search=search,
        enabled=enabled,
        process_status=process_status,
        directory_id=directory_id,
        page=page,
        per_page=per_page,
    )


@router.post(
    "", response_model=KnowledgeBaseQaResponse, status_code=status.HTTP_201_CREATED
)
async def create_qa(
    kb_id: int,
    body: KnowledgeBaseQaCreate,
    auth: AuthContext = Depends(require_qa_write),
    db: AsyncSession = Depends(get_db),
):
    return await KnowledgeBaseQaService.create(
        db, auth.tenant_id, kb_id, body
    )


@router.get("/{qa_id}", response_model=KnowledgeBaseQaResponse)
async def get_qa(
    kb_id: int,
    qa_id: int,
    auth: AuthContext = Depends(require_qa_read),
    db: AsyncSession = Depends(get_db),
):
    return await KnowledgeBaseQaService.get_by_id(
        db, auth.tenant_id, kb_id, qa_id
    )


@router.put("/{qa_id}", response_model=KnowledgeBaseQaResponse)
async def update_qa(
    kb_id: int,
    qa_id: int,
    body: KnowledgeBaseQaUpdate,
    auth: AuthContext = Depends(require_qa_write),
    db: AsyncSession = Depends(get_db),
):
    return await KnowledgeBaseQaService.update(
        db, auth.tenant_id, kb_id, qa_id, body
    )


@router.delete("/{qa_id}")
async def delete_qa(
    kb_id: int,
    qa_id: int,
    auth: AuthContext = Depends(require_qa_write),
    db: AsyncSession = Depends(get_db),
):
    await KnowledgeBaseQaService.delete(
        db, auth.tenant_id, kb_id, qa_id
    )
    return {"message": "Deleted successfully"}


@router.patch("/{qa_id}/toggle", response_model=KnowledgeBaseQaResponse)
async def toggle_qa(
    kb_id: int,
    qa_id: int,
    auth: AuthContext = Depends(require_qa_write),
    db: AsyncSession = Depends(get_db),
):
    return await KnowledgeBaseQaService.toggle(
        db, auth.tenant_id, kb_id, qa_id
    )


@router.post("/{qa_id}/retry", response_model=KnowledgeBaseQaResponse)
async def retry_qa(
    kb_id: int,
    qa_id: int,
    auth: AuthContext = Depends(require_qa_write),
    db: AsyncSession = Depends(get_db),
):
    return await KnowledgeBaseQaService.retry(
        db, auth.tenant_id, kb_id, qa_id
    )
