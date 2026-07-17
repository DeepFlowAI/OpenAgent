"""Knowledge-base QA directory management router."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import (
    AuthContext,
    get_db,
    require_admin_session_or_scope,
    require_user_session_or_scope,
)
from app.schemas.knowledge_base_qa_directory import (
    KnowledgeBaseQaDirectoryCreate,
    KnowledgeBaseQaDirectoryListResponse,
    KnowledgeBaseQaDirectoryResponse,
    KnowledgeBaseQaDirectoryUpdate,
)
from app.services.knowledge_base_qa_directory_service import (
    KnowledgeBaseQaDirectoryService,
)

router = APIRouter(
    prefix="/knowledge-bases/{kb_id}/qa-directories",
    tags=["KnowledgeBaseQaDirectories"],
)

require_qa_directory_read = require_user_session_or_scope("config")
require_qa_directory_write = require_admin_session_or_scope("config")


@router.get("", response_model=KnowledgeBaseQaDirectoryListResponse)
async def list_qa_directories(
    kb_id: int,
    auth: AuthContext = Depends(require_qa_directory_read),
    db: AsyncSession = Depends(get_db),
):
    return await KnowledgeBaseQaDirectoryService.list_directories(
        db, auth.tenant_id, kb_id
    )


@router.post(
    "",
    response_model=KnowledgeBaseQaDirectoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_qa_directory(
    kb_id: int,
    body: KnowledgeBaseQaDirectoryCreate,
    auth: AuthContext = Depends(require_qa_directory_write),
    db: AsyncSession = Depends(get_db),
):
    return await KnowledgeBaseQaDirectoryService.create(
        db, auth.tenant_id, kb_id, body
    )


@router.put("/{directory_id}", response_model=KnowledgeBaseQaDirectoryResponse)
async def update_qa_directory(
    kb_id: int,
    directory_id: int,
    body: KnowledgeBaseQaDirectoryUpdate,
    auth: AuthContext = Depends(require_qa_directory_write),
    db: AsyncSession = Depends(get_db),
):
    return await KnowledgeBaseQaDirectoryService.update(
        db, auth.tenant_id, kb_id, directory_id, body
    )


@router.delete("/{directory_id}")
async def delete_qa_directory(
    kb_id: int,
    directory_id: int,
    auth: AuthContext = Depends(require_qa_directory_write),
    db: AsyncSession = Depends(get_db),
):
    await KnowledgeBaseQaDirectoryService.delete(
        db, auth.tenant_id, kb_id, directory_id
    )
    return {"message": "Deleted successfully"}
