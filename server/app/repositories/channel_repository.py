"""
Channel repository
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel


class ChannelRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, channel_id: int) -> Channel | None:
        return await db.get(Channel, channel_id)

    @staticmethod
    async def get_by_token(db: AsyncSession, token: str) -> Channel | None:
        result = await db.execute(
            select(Channel).where(Channel.token == token)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_names_by_ids(
        db: AsyncSession, tenant_id: str, channel_ids: list[int]
    ) -> dict[int, str]:
        if not channel_ids:
            return {}
        result = await db.execute(
            select(Channel.id, Channel.name).where(
                Channel.tenant_id == tenant_id,
                Channel.id.in_(channel_ids),
            )
        )
        return {row.id: row.name for row in result.all()}

    @staticmethod
    async def get_web_sdk_options_by_agent(
        db: AsyncSession, tenant_id: str, agent_id: int
    ) -> list[Channel]:
        result = await db.execute(
            select(Channel)
            .where(
                Channel.tenant_id == tenant_id,
                Channel.agent_id == agent_id,
                Channel.channel_type == "web-sdk",
            )
            .order_by(Channel.updated_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_tenant_and_name(
        db: AsyncSession, tenant_id: str, name: str
    ) -> Channel | None:
        result = await db.execute(
            select(Channel).where(
                Channel.tenant_id == tenant_id,
                Channel.name == name,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: str,
        page: int = 1,
        per_page: int = 10,
    ) -> tuple[list[Channel], int]:
        base_filter = (Channel.tenant_id == tenant_id,)

        total_result = await db.execute(
            select(func.count()).select_from(Channel).where(*base_filter)
        )
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            select(Channel)
            .where(*base_filter)
            .order_by(Channel.updated_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> Channel:
        item = Channel(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(db: AsyncSession, item: Channel, data: dict) -> Channel:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete(db: AsyncSession, item: Channel) -> None:
        await db.delete(item)
        await db.commit()
