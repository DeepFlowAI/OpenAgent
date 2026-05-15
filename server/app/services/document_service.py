"""
Document service
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository


class DocumentService:

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
