"""
KnowledgeBase router
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.db.deps import AuthContext, get_db, resolve_auth
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseResponse,
    KnowledgeBaseListResponse,
    PublicKnowledgeBaseListResponse,
)
from app.services.knowledge_base_service import KnowledgeBaseService
from app.repositories.slice_repository import SliceRepository

router = APIRouter(prefix="/knowledge-bases", tags=["KnowledgeBases"])


@router.get("", response_model=KnowledgeBaseListResponse | PublicKnowledgeBaseListResponse)
async def list_knowledge_bases(
    auth: AuthContext = Depends(resolve_auth),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List knowledge bases for a tenant"""
    if auth.scopes is not None:
        if "chat" not in auth.scopes:
            raise ForbiddenError("API key lacks required scope: chat")
        return await KnowledgeBaseService.get_public_paginated(
            db, auth.tenant_id, page, per_page
        )
    return await KnowledgeBaseService.get_paginated(db, auth.tenant_id, page, per_page)


@router.post(
    "", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED
)
async def create_knowledge_base(
    body: KnowledgeBaseCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new knowledge base"""
    return await KnowledgeBaseService.create(db, body)


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get knowledge base by ID"""
    return await KnowledgeBaseService.get_by_id(db, kb_id)


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: int,
    body: KnowledgeBaseUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update knowledge base"""
    return await KnowledgeBaseService.update(db, kb_id, body)


@router.delete("/{kb_id}", status_code=status.HTTP_200_OK)
async def delete_knowledge_base(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Soft delete knowledge base"""
    await KnowledgeBaseService.delete(db, kb_id)
    return {"message": "Deleted successfully"}


@router.get("/{kb_id}/meta-fields")
async def get_kb_meta_fields(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get available doc_meta and slice_meta field names for a knowledge base."""
    kb = await KnowledgeBaseService.get_by_id(db, kb_id)
    if kb.schema_fields:
        result: dict[str, list[str]] = {"doc_meta": [], "slice_meta": []}
        sf = kb.schema_fields
        if isinstance(sf.get("doc_meta"), list):
            result["doc_meta"] = sf["doc_meta"]
        if isinstance(sf.get("slice_meta"), list):
            result["slice_meta"] = sf["slice_meta"]
        if result["doc_meta"] or result["slice_meta"]:
            return result
    return await SliceRepository.get_meta_fields(db, kb_id)


@router.get("/{kb_id}/meta-schema")
async def get_kb_meta_schema(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get full field definitions (name, type, values) for a knowledge base.

    Priority: stored definitions from schema YAML sync → fallback to field
    name lists with default type ``keyword`` → fallback to JSONB key inference.
    """
    kb = await KnowledgeBaseService.get_by_id(db, kb_id)
    sf = kb.schema_fields or {}

    doc_defs = sf.get("doc_meta_definitions")
    slice_defs = sf.get("slice_meta_definitions")

    if isinstance(doc_defs, list) or isinstance(slice_defs, list):
        return {
            "doc_meta": doc_defs if isinstance(doc_defs, list) else [],
            "slice_meta": slice_defs if isinstance(slice_defs, list) else [],
        }

    doc_names = sf.get("doc_meta", []) if isinstance(sf.get("doc_meta"), list) else []
    slice_names = sf.get("slice_meta", []) if isinstance(sf.get("slice_meta"), list) else []

    if doc_names or slice_names:
        return {
            "doc_meta": [{"name": n, "type": "keyword"} for n in doc_names],
            "slice_meta": [{"name": n, "type": "keyword"} for n in slice_names],
        }

    inferred = await SliceRepository.get_meta_fields(db, kb_id)
    return {
        "doc_meta": [{"name": n, "type": "keyword"} for n in inferred.get("doc_meta", [])],
        "slice_meta": [{"name": n, "type": "keyword"} for n in inferred.get("slice_meta", [])],
    }
