"""
Document reference query router
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.db.deps import AuthContext, get_db, resolve_auth
from app.repositories.account_repository import AccountRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentQueryRequest, DocumentQueryResponse
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/query", response_model=DocumentQueryResponse)
async def query_document_reference(
    body: DocumentQueryRequest,
    auth: AuthContext = Depends(resolve_auth),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a document reference parsed from an LLM response."""
    if auth.scopes is not None and "chat" not in auth.scopes:
        raise ForbiddenError("API key lacks required scope: chat")
    if auth.role == "quality_inspector":
        document = await DocumentRepository.get_by_id_for_tenant(
            db, body.doc_id, auth.tenant_id
        )
        if (
            document is None
            or auth.account_id is None
            or not await AccountRepository.has_knowledge_base_access(
                db, auth.account_id, document.knowledge_base_id
            )
        ):
            raise ForbiddenError(
                "You do not have access to this knowledge base"
            )
    return await DocumentService.query_reference(db, auth.tenant_id, body)
