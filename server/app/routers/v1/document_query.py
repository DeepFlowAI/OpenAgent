"""
Document reference query router
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_scope
from app.schemas.document import DocumentQueryRequest, DocumentQueryResponse
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/query", response_model=DocumentQueryResponse)
async def query_document_reference(
    body: DocumentQueryRequest,
    tenant_id: str = Depends(require_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a document reference parsed from an LLM response."""
    return await DocumentService.query_reference(db, tenant_id, body)
