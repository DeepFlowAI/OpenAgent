"""
KnowledgeBase service
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate


class KnowledgeBaseService:

    @staticmethod
    async def get_paginated(
        db: AsyncSession, tenant_id: str, page: int = 1, per_page: int = 10
    ) -> dict:
        items, total = await KnowledgeBaseRepository.get_paginated(
            db, tenant_id, page, per_page
        )
        pages = (total + per_page - 1) // per_page
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, kb_id: int) -> dict:
        item = await KnowledgeBaseRepository.get_by_id(db, kb_id)
        if not item or item.status == "deleted":
            raise NotFoundError("Knowledge base not found")
        return item

    @staticmethod
    async def create(db: AsyncSession, data: KnowledgeBaseCreate) -> dict:
        existing = await KnowledgeBaseRepository.get_by_tenant_and_name(
            db, data.tenant_id, data.name
        )
        if existing:
            raise ValidationError(
                f"Knowledge base with name '{data.name}' already exists"
            )

        create_data = data.model_dump()
        if create_data.get("auth_type") == "none":
            create_data["auth_token"] = None

        return await KnowledgeBaseRepository.create(db, create_data)

    @staticmethod
    async def update(
        db: AsyncSession, kb_id: int, data: KnowledgeBaseUpdate
    ) -> dict:
        item = await KnowledgeBaseRepository.get_by_id(db, kb_id)
        if not item or item.status == "deleted":
            raise NotFoundError("Knowledge base not found")

        update_data = data.model_dump(exclude_unset=True)

        if "name" in update_data and update_data["name"] != item.name:
            existing = await KnowledgeBaseRepository.get_by_tenant_and_name(
                db, item.tenant_id, update_data["name"]
            )
            if existing:
                raise ValidationError(
                    f"Knowledge base with name '{update_data['name']}' already exists"
                )

        if update_data.get("auth_type") == "none":
            update_data["auth_token"] = None

        return await KnowledgeBaseRepository.update(db, item, update_data)

    @staticmethod
    async def delete(db: AsyncSession, kb_id: int) -> None:
        item = await KnowledgeBaseRepository.get_by_id(db, kb_id)
        if not item or item.status == "deleted":
            raise NotFoundError("Knowledge base not found")
        await KnowledgeBaseRepository.soft_delete(db, item)
