"""
Slice repository
"""
import logging

from sqlalchemy import select, func, delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.slice import Slice

logger = logging.getLogger(__name__)


class SliceRepository:

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        document_id: int,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[Slice], int]:
        base_filter = (Slice.document_id == document_id,)

        total_result = await db.execute(
            select(func.count()).select_from(Slice).where(*base_filter)
        )
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            select(Slice)
            .where(*base_filter)
            .order_by(Slice.slice_order.asc())
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create_batch(db: AsyncSession, items: list[dict]) -> list[Slice]:
        if not items:
            return []
        slices = [Slice(**data) for data in items]
        kb_id = items[0].get("knowledge_base_id")
        doc_id = items[0].get("document_id")
        db.add_all(slices)
        await db.flush()
        logger.info(
            "DB batch insert slices: count=%s knowledge_base_id=%s document_id=%s "
            "(add_all + single flush)",
            len(slices),
            kb_id,
            doc_id,
        )
        return slices

    @staticmethod
    async def delete_by_document_id(db: AsyncSession, document_id: int) -> int:
        result = await db.execute(
            delete(Slice).where(Slice.document_id == document_id)
        )
        return result.rowcount

    @staticmethod
    async def delete_by_kb_id(db: AsyncSession, kb_id: int) -> int:
        result = await db.execute(
            delete(Slice).where(Slice.knowledge_base_id == kb_id)
        )
        return result.rowcount

    @staticmethod
    async def get_meta_fields(db: AsyncSession, kb_id: int) -> dict[str, list[str]]:
        """Extract distinct JSONB key names from doc_meta and slice_meta for a KB."""
        doc_meta_sql = text(
            "SELECT DISTINCT jsonb_object_keys(doc_meta) AS field "
            "FROM slices WHERE knowledge_base_id = :kb_id "
            "AND doc_meta IS NOT NULL AND jsonb_typeof(doc_meta) = 'object'"
        )
        slice_meta_sql = text(
            "SELECT DISTINCT jsonb_object_keys(slice_meta) AS field "
            "FROM slices WHERE knowledge_base_id = :kb_id "
            "AND slice_meta IS NOT NULL AND jsonb_typeof(slice_meta) = 'object'"
        )
        doc_result = await db.execute(doc_meta_sql, {"kb_id": kb_id})
        slice_result = await db.execute(slice_meta_sql, {"kb_id": kb_id})
        return {
            "doc_meta": sorted([row[0] for row in doc_result]),
            "slice_meta": sorted([row[0] for row in slice_result]),
        }
