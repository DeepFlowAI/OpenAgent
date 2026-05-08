"""
Document repository
"""
import logging

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document

logger = logging.getLogger(__name__)


class DocumentRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, doc_id: int) -> Document | None:
        return await db.get(Document, doc_id)

    @staticmethod
    async def get_by_kb_and_path(
        db: AsyncSession, kb_id: int, file_path: str
    ) -> Document | None:
        result = await db.execute(
            select(Document).where(
                Document.knowledge_base_id == kb_id,
                Document.file_path == file_path,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        kb_id: int,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[Document], int]:
        base_filter = (Document.knowledge_base_id == kb_id,)

        total_result = await db.execute(
            select(func.count()).select_from(Document).where(*base_filter)
        )
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            select(Document)
            .where(*base_filter)
            .order_by(Document.file_path.asc())
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> Document:
        item = Document(**data)
        db.add(item)
        await db.flush()
        logger.info(
            "DB insert document: id=%s knowledge_base_id=%s file_path=%s (single-row flush)",
            item.id,
            item.knowledge_base_id,
            item.file_path,
        )
        return item

    @staticmethod
    async def get_hash_map_by_kb(db: AsyncSession, kb_id: int) -> dict[str, tuple[int, str | None]]:
        """Return {file_path: (doc_id, content_hash)} for all docs in a KB."""
        result = await db.execute(
            select(Document.id, Document.file_path, Document.content_hash)
            .where(Document.knowledge_base_id == kb_id)
        )
        return {row.file_path: (row.id, row.content_hash) for row in result}

    @staticmethod
    async def update_document(db: AsyncSession, doc: Document, data: dict) -> Document:
        for key, value in data.items():
            if hasattr(doc, key):
                setattr(doc, key, value)
        await db.flush()
        return doc

    @staticmethod
    async def delete_by_id(db: AsyncSession, doc_id: int) -> None:
        await db.execute(delete(Document).where(Document.id == doc_id))

    @staticmethod
    async def delete_by_kb_id(db: AsyncSession, kb_id: int) -> int:
        result = await db.execute(
            delete(Document).where(Document.knowledge_base_id == kb_id)
        )
        return result.rowcount
