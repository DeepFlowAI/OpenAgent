"""
Conversation service — business logic for conversation management
"""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.conversation import ConversationCreate


class ConversationService:

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: str,
        agent_id: int,
        *,
        page: int = 1,
        per_page: int = 10,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        status: str | None = None,
        source: str | None = None,
        conversation_id: str | None = None,
        external_user_id: str | None = None,
        search: str | None = None,
    ) -> dict:
        items, total = await ConversationRepository.get_paginated(
            db,
            tenant_id,
            agent_id,
            page=page,
            per_page=per_page,
            start_time=start_time,
            end_time=end_time,
            status=status,
            source=source,
            conversation_id=conversation_id,
            external_user_id=external_user_id,
            search=search,
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
    async def get_by_id(db: AsyncSession, conversation_id: int) -> dict:
        item = await ConversationRepository.get_by_id(db, conversation_id)
        if not item:
            raise NotFoundError("Conversation not found")

        duration_seconds = None
        if item.started_at:
            end = item.ended_at or datetime.now(timezone.utc)
            if item.started_at.tzinfo is None:
                started = item.started_at.replace(tzinfo=timezone.utc)
            else:
                started = item.started_at
            duration_seconds = int((end - started).total_seconds())

        return {
            **{c.key: getattr(item, c.key) for c in item.__table__.columns},
            "duration_seconds": duration_seconds,
        }

    @staticmethod
    async def create(db: AsyncSession, data: ConversationCreate):
        create_data = data.model_dump()
        return await ConversationRepository.create(db, create_data)

    @staticmethod
    async def end_conversation(db: AsyncSession, conversation_id: int):
        item = await ConversationRepository.get_by_id(db, conversation_id)
        if not item:
            raise NotFoundError("Conversation not found")
        if item.status == "ended":
            return item
        return await ConversationRepository.update(
            db,
            item,
            {"status": "ended", "ended_at": datetime.now(timezone.utc)},
        )
