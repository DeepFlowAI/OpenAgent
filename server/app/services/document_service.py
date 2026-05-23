"""
Document service
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.slice_repository import SliceRepository
from app.schemas.document import (
    DocumentQueryDocument,
    DocumentQueryRequest,
    DocumentQueryResponse,
    DocumentQuerySlice,
)


class DocumentService:

    @staticmethod
    async def query_reference(
        db: AsyncSession,
        tenant_id: str,
        body: DocumentQueryRequest,
    ) -> DocumentQueryResponse:
        doc = await DocumentRepository.get_by_id_for_tenant(
            db,
            body.doc_id,
            tenant_id,
        )
        if not doc:
            return DocumentQueryResponse(
                resolved=False,
                reason="document_not_found",
                doc_id=body.doc_id,
                slice_id=body.slice_id,
                line=body.line,
            )

        kb = await KnowledgeBaseRepository.get_by_id(db, doc.knowledge_base_id)
        if not kb or kb.status == "deleted" or kb.tenant_id != tenant_id:
            return DocumentQueryResponse(
                resolved=False,
                reason="document_not_found",
                doc_id=body.doc_id,
                slice_id=body.slice_id,
                line=body.line,
            )

        document = DocumentQueryDocument(
            id=doc.id,
            knowledge_base_id=doc.knowledge_base_id,
            title=doc.title,
            file_path=doc.file_path,
            doc_meta=doc.doc_meta,
            markdown_url=f"/api/v1/knowledge-bases/{doc.knowledge_base_id}/documents/{doc.id}/markdown",
            document_url=f"/knowledge-space/{doc.knowledge_base_id}/documents/{doc.id}",
        )

        resolved = True
        reason = None
        slice_data = None
        if body.slice_id is not None:
            slice_item = await SliceRepository.get_by_id_for_document(
                db,
                body.slice_id,
                doc.id,
                tenant_id,
            )
            if slice_item is None:
                resolved = False
                reason = "slice_not_found"
            else:
                slice_data = DocumentQuerySlice(
                    id=slice_item.id,
                    content=slice_item.content,
                    toc_path=slice_item.toc_path,
                    slice_order=slice_item.slice_order,
                    slice_meta=slice_item.slice_meta,
                )

        line_text = None
        line_count = None
        if body.line is not None:
            lines = (doc.markdown_content or "").splitlines()
            line_count = len(lines)
            if body.line <= line_count:
                line_text = lines[body.line - 1]
            else:
                resolved = False
                if reason is None:
                    reason = "line_not_found"

        return DocumentQueryResponse(
            resolved=resolved,
            reason=reason,
            doc_id=body.doc_id,
            slice_id=body.slice_id,
            line=body.line,
            document=document,
            slice=slice_data,
            line_text=line_text,
            line_count=line_count,
        )

    @staticmethod
    async def get_public_paginated(
        db: AsyncSession,
        kb_id: int,
        tenant_id: str,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        kb = await KnowledgeBaseRepository.get_by_id(db, kb_id)
        if not kb or kb.status == "deleted" or kb.tenant_id != tenant_id:
            raise NotFoundError("Knowledge base not found")

        items, total = await DocumentRepository.get_paginated(
            db, kb_id, page, per_page, nav_config=kb.nav_config
        )
        pages = (total + per_page - 1) // per_page
        return {
            "items": [
                {
                    "id": item.id,
                    "file_path": item.file_path,
                    "title": item.title,
                    "slice_count": item.slice_count,
                    "updated_at": item.updated_at,
                    "doc_meta": item.doc_meta,
                    "markdown_url": f"/api/v1/knowledge-bases/{kb_id}/documents/{item.id}/markdown",
                }
                for item in items
            ],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }
