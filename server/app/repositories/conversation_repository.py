"""
Conversation repository — data access for conversations table
"""
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation


class ConversationRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, conversation_id: int) -> Conversation | None:
        return await db.get(Conversation, conversation_id)

    @staticmethod
    async def get_by_external_id(
        db: AsyncSession, external_id: str
    ) -> Conversation | None:
        result = await db.execute(
            select(Conversation).where(Conversation.external_id == external_id)
        )
        return result.scalar_one_or_none()

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
    ) -> tuple[list[Conversation], int]:
        conditions = [
            Conversation.tenant_id == tenant_id,
            Conversation.agent_id == agent_id,
        ]

        if start_time:
            conditions.append(Conversation.started_at >= start_time)
        if end_time:
            conditions.append(Conversation.started_at <= end_time)
        if status:
            conditions.append(Conversation.status == status)
        if source:
            conditions.append(Conversation.source == source)
        if conversation_id:
            conditions.append(Conversation.external_id == conversation_id.strip())
        if external_user_id:
            conditions.append(Conversation.external_user_id.ilike(f"%{external_user_id}%"))
        if search:
            conditions.append(Conversation.title.ilike(f"%{search}%"))

        total_result = await db.execute(
            select(func.count()).select_from(Conversation).where(*conditions)
        )
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            select(Conversation)
            .where(*conditions)
            .order_by(Conversation.started_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_by_external_user_id(
        db: AsyncSession,
        tenant_id: str,
        agent_id: int,
        external_user_id: str,
        *,
        limit: int = 50,
    ) -> list[Conversation]:
        """Get conversations for a specific external_user_id (exact match), newest first."""
        result = await db.execute(
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.agent_id == agent_id,
                Conversation.external_user_id == external_user_id,
            )
            .order_by(Conversation.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> Conversation:
        if "metadata" in data:
            data["metadata_"] = data.pop("metadata")
        item = Conversation(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(
        db: AsyncSession, item: Conversation, data: dict
    ) -> Conversation:
        if "metadata" in data:
            data["metadata_"] = data.pop("metadata")
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def increment_counters(
        db: AsyncSession,
        conversation_id: int,
        *,
        round_count: int = 0,
        llm_call_count: int = 0,
        tool_call_count: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """Atomically increment denormalized counters on a conversation."""
        item = await db.get(Conversation, conversation_id)
        if not item:
            return
        if round_count:
            item.round_count = (item.round_count or 0) + round_count
        if llm_call_count:
            item.llm_call_count = (item.llm_call_count or 0) + llm_call_count
        if tool_call_count:
            item.tool_call_count = (item.tool_call_count or 0) + tool_call_count
        if input_tokens:
            item.total_input_tokens = (item.total_input_tokens or 0) + input_tokens
        if output_tokens:
            item.total_output_tokens = (item.total_output_tokens or 0) + output_tokens
        if total_tokens:
            item.total_tokens = (item.total_tokens or 0) + total_tokens
        await db.commit()
        await db.refresh(item)
