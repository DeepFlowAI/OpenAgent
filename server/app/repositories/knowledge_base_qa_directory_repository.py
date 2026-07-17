"""Knowledge-base QA directory data access."""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base_qa import KnowledgeBaseQa
from app.models.knowledge_base_qa_directory import KnowledgeBaseQaDirectory


class KnowledgeBaseQaDirectoryRepository:
    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        tenant_id: str,
        knowledge_base_id: int,
        directory_id: int,
    ) -> KnowledgeBaseQaDirectory | None:
        result = await db.execute(
            select(KnowledgeBaseQaDirectory).where(
                KnowledgeBaseQaDirectory.id == directory_id,
                KnowledgeBaseQaDirectory.tenant_id == tenant_id,
                KnowledgeBaseQaDirectory.knowledge_base_id == knowledge_base_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession, tenant_id: str, knowledge_base_id: int
    ) -> list[KnowledgeBaseQaDirectory]:
        result = await db.execute(
            select(KnowledgeBaseQaDirectory)
            .where(
                KnowledgeBaseQaDirectory.tenant_id == tenant_id,
                KnowledgeBaseQaDirectory.knowledge_base_id == knowledge_base_id,
            )
            .order_by(
                KnowledgeBaseQaDirectory.parent_id.asc().nullsfirst(),
                KnowledgeBaseQaDirectory.sort_order.asc(),
                KnowledgeBaseQaDirectory.id.asc(),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_siblings(
        db: AsyncSession,
        tenant_id: str,
        knowledge_base_id: int,
        parent_id: int | None,
        *,
        exclude_id: int | None = None,
    ) -> list[KnowledgeBaseQaDirectory]:
        parent_condition = (
            KnowledgeBaseQaDirectory.parent_id.is_(None)
            if parent_id is None
            else KnowledgeBaseQaDirectory.parent_id == parent_id
        )
        stmt = select(KnowledgeBaseQaDirectory).where(
            KnowledgeBaseQaDirectory.tenant_id == tenant_id,
            KnowledgeBaseQaDirectory.knowledge_base_id == knowledge_base_id,
            parent_condition,
        )
        if exclude_id is not None:
            stmt = stmt.where(KnowledgeBaseQaDirectory.id != exclude_id)
        result = await db.execute(
            stmt.order_by(
                KnowledgeBaseQaDirectory.sort_order.asc(),
                KnowledgeBaseQaDirectory.id.asc(),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def name_exists(
        db: AsyncSession,
        knowledge_base_id: int,
        parent_id: int | None,
        name: str,
        *,
        exclude_id: int | None = None,
    ) -> bool:
        parent_condition = (
            KnowledgeBaseQaDirectory.parent_id.is_(None)
            if parent_id is None
            else KnowledgeBaseQaDirectory.parent_id == parent_id
        )
        stmt = select(KnowledgeBaseQaDirectory.id).where(
            KnowledgeBaseQaDirectory.knowledge_base_id == knowledge_base_id,
            parent_condition,
            KnowledgeBaseQaDirectory.name == name,
        )
        if exclude_id is not None:
            stmt = stmt.where(KnowledgeBaseQaDirectory.id != exclude_id)
        return (await db.execute(stmt.limit(1))).scalar_one_or_none() is not None

    @staticmethod
    async def count_qas(db: AsyncSession, knowledge_base_id: int) -> int:
        return int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(KnowledgeBaseQa)
                    .where(KnowledgeBaseQa.knowledge_base_id == knowledge_base_id)
                )
            ).scalar_one()
        )

    @staticmethod
    async def count_qas_by_directory(
        db: AsyncSession, knowledge_base_id: int
    ) -> dict[int, int]:
        result = await db.execute(
            select(KnowledgeBaseQa.directory_id, func.count())
            .where(KnowledgeBaseQa.knowledge_base_id == knowledge_base_id)
            .group_by(KnowledgeBaseQa.directory_id)
        )
        return {int(directory_id): int(count) for directory_id, count in result.all()}

    @staticmethod
    async def create(
        db: AsyncSession, data: dict
    ) -> KnowledgeBaseQaDirectory:
        item = KnowledgeBaseQaDirectory(**data)
        db.add(item)
        await db.flush()
        return item

    @staticmethod
    async def update_fields(
        db: AsyncSession, item: KnowledgeBaseQaDirectory, data: dict
    ) -> None:
        for key, value in data.items():
            setattr(item, key, value)

    @staticmethod
    async def apply_order(
        db: AsyncSession,
        items: list[KnowledgeBaseQaDirectory],
        parent_id: int | None,
    ) -> None:
        for index, item in enumerate(items):
            item.parent_id = parent_id
            item.sort_order = index
        await db.flush()

    @staticmethod
    async def has_children(db: AsyncSession, directory_id: int) -> bool:
        result = await db.execute(
            select(KnowledgeBaseQaDirectory.id)
            .where(KnowledgeBaseQaDirectory.parent_id == directory_id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def has_direct_qas(db: AsyncSession, directory_id: int) -> bool:
        result = await db.execute(
            select(KnowledgeBaseQa.id)
            .where(KnowledgeBaseQa.directory_id == directory_id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def delete(
        db: AsyncSession, directory_id: int
    ) -> None:
        await db.execute(
            delete(KnowledgeBaseQaDirectory).where(
                KnowledgeBaseQaDirectory.id == directory_id
            )
        )
        await db.flush()
