"""
Search router — POST /api/v1/knowledge-bases/{kb_id}/search
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.deps import get_db, require_scope
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.schemas.search import SearchRequest, SearchResponse
from app.services.search_service import SearchService

router = APIRouter(prefix="/knowledge-bases", tags=["Search"])


@router.post("/{kb_id}/search", response_model=SearchResponse)
async def search_knowledge_base(
    kb_id: int,
    body: SearchRequest,
    tenant_id: str = Depends(require_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Search slices in a knowledge base (hybrid: BM25 + vector + reranker).

    Permission engine deny rules are applied when subject_context is provided
    in the request body.  For chat-initiated searches via tool executors,
    subject_context is loaded automatically from the conversation.
    """
    kb = await KnowledgeBaseRepository.get_by_id(db, kb_id)
    if not kb or kb.status == "deleted" or kb.tenant_id != tenant_id:
        raise NotFoundError("Knowledge base not found")

    subject_context = None
    if body.subject_context:
        subject_context = body.subject_context.model_dump()

    return await SearchService.search(db, kb_id, body, subject_context)
