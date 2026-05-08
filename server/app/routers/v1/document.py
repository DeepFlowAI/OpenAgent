"""
Document & Slice query router
"""
import logging
from urllib.parse import quote, unquote, urlparse

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_scope
from app.core.exceptions import NotFoundError
from app.libs.doc_parser.parser import clean_markdown_for_reading
from app.repositories.document_repository import DocumentRepository
from app.repositories.slice_repository import SliceRepository
from app.repositories.sync_log_repository import SyncLogRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.schemas.document import (
    DocumentResponse,
    DocumentListResponse,
    SliceListResponse,
    SyncLogListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-bases", tags=["Documents"])

_ORIGINAL_FETCH_TIMEOUT = httpx.Timeout(120.0, connect=30.0)
_ORIGINAL_CHUNK = 64 * 1024


@router.get("/{kb_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    kb_id: int,
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List documents for a knowledge base"""
    items, total = await DocumentRepository.get_paginated(db, kb_id, page, per_page)
    pages = (total + per_page - 1) // per_page
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("/{kb_id}/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    kb_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get document detail"""
    doc = await DocumentRepository.get_by_id(db, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise NotFoundError("Document not found")
    return doc


@router.get("/{kb_id}/documents/{doc_id}/slices", response_model=SliceListResponse)
async def list_slices(
    kb_id: int,
    doc_id: int,
    page: int = 1,
    per_page: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List slices for a document"""
    doc = await DocumentRepository.get_by_id(db, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise NotFoundError("Document not found")

    items, total = await SliceRepository.get_paginated(db, doc_id, page, per_page)
    pages = (total + per_page - 1) // per_page
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("/{kb_id}/documents/{doc_id}/original-file")
async def stream_document_original_file(
    kb_id: int,
    doc_id: int,
    download: bool = Query(
        False,
        description="If true, Content-Disposition is attachment (force download).",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Proxy the document's source_url through the API so the browser can inline-preview PDFs.

    Object storage often responds with Content-Disposition: attachment or blocks iframes;
    we re-stream with inline disposition and application/pdf for embedding.
    """
    doc = await DocumentRepository.get_by_id(db, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise NotFoundError("Document not found")

    raw_url = (doc.source_url or "").strip()
    if not raw_url and doc.doc_meta and isinstance(doc.doc_meta.get("source"), str):
        raw_url = doc.doc_meta["source"].strip()
    if not raw_url.startswith(("http://", "https://")):
        raise NotFoundError("Document has no valid source URL")

    try:
        url_path = urlparse(raw_url).path
        url_basename = unquote(url_path.rsplit("/", 1)[-1] or "")
    except Exception:
        url_basename = ""
    if url_basename.lower().endswith(".pdf"):
        filename = url_basename
    else:
        filename = "original.pdf"

    disposition_type = "attachment" if download else "inline"
    safe_name = quote(filename)

    async def byte_iter():
        async with httpx.AsyncClient(
            timeout=_ORIGINAL_FETCH_TIMEOUT,
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", raw_url) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    logger.warning(
                        "Original file upstream error doc_id=%s status=%s",
                        doc_id,
                        exc.response.status_code,
                    )
                    raise NotFoundError("Could not fetch original file") from exc
                async for chunk in response.aiter_bytes(_ORIGINAL_CHUNK):
                    yield chunk

    return StreamingResponse(
        byte_iter(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition_type}; filename="{filename}"; filename*=UTF-8\'\'{safe_name}',
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/{kb_id}/documents/{doc_id}/markdown",
    response_class=PlainTextResponse,
    responses={200: {"content": {"text/markdown": {}}}},
)
async def get_document_markdown(
    kb_id: int,
    doc_id: int,
    tenant_id: str = Depends(require_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Return the readable markdown content for a document.

    Strips frontmatter, <slice-meta> blocks and +++ separators so the
    response is clean markdown suitable for reading / rendering.
    """
    kb = await KnowledgeBaseRepository.get_by_id(db, kb_id)
    if not kb or kb.status == "deleted" or kb.tenant_id != tenant_id:
        raise NotFoundError("Knowledge base not found")
    doc = await DocumentRepository.get_by_id(db, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise NotFoundError("Document not found")
    readable = clean_markdown_for_reading(doc.markdown_content or "")
    return PlainTextResponse(
        content=readable,
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/{kb_id}/sync-logs", response_model=SyncLogListResponse)
async def list_sync_logs(
    kb_id: int,
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List sync logs for a knowledge base"""
    items, total = await SyncLogRepository.get_paginated(db, kb_id, page, per_page)
    pages = (total + per_page - 1) // per_page
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }
