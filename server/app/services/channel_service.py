"""
Channel service
"""
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.channel_repository import ChannelRepository
from app.schemas.channel import ChannelCreate, ChannelUpdate


def _generate_channel_token() -> str:
    return secrets.token_urlsafe(16)[:22]


class ChannelService:

    @staticmethod
    async def get_paginated(
        db: AsyncSession, tenant_id: str, page: int = 1, per_page: int = 10
    ) -> dict:
        items, total = await ChannelRepository.get_paginated(
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
    async def get_by_id(db: AsyncSession, channel_id: int):
        item = await ChannelRepository.get_by_id(db, channel_id)
        if not item:
            raise NotFoundError("Channel not found")
        return item

    @staticmethod
    async def get_by_token(db: AsyncSession, token: str):
        item = await ChannelRepository.get_by_token(db, token)
        if not item:
            raise NotFoundError("Channel not found")
        return item

    @staticmethod
    async def create(db: AsyncSession, data: ChannelCreate):
        existing = await ChannelRepository.get_by_tenant_and_name(
            db, data.tenant_id, data.name
        )
        if existing:
            raise ValidationError(
                f"Channel with name '{data.name}' already exists in this tenant"
            )
        payload = data.model_dump()
        payload["token"] = _generate_channel_token()
        return await ChannelRepository.create(db, payload)

    @staticmethod
    async def update(db: AsyncSession, channel_id: int, data: ChannelUpdate):
        item = await ChannelRepository.get_by_id(db, channel_id)
        if not item:
            raise NotFoundError("Channel not found")

        update_data = data.model_dump(exclude_unset=True)
        if "name" in update_data and update_data["name"] != item.name:
            existing = await ChannelRepository.get_by_tenant_and_name(
                db, item.tenant_id, update_data["name"]
            )
            if existing:
                raise ValidationError(
                    f"Channel with name '{update_data['name']}' already exists"
                )

        return await ChannelRepository.update(db, item, update_data)

    @staticmethod
    async def generate_secret_key(db: AsyncSession, channel_id: int):
        """Generate or rotate the channel secret_key."""
        item = await ChannelRepository.get_by_id(db, channel_id)
        if not item:
            raise NotFoundError("Channel not found")
        new_key = f"csk_{secrets.token_urlsafe(32)}"
        return await ChannelRepository.update(db, item, {"secret_key": new_key})

    @staticmethod
    async def delete(db: AsyncSession, channel_id: int) -> None:
        item = await ChannelRepository.get_by_id(db, channel_id)
        if not item:
            raise NotFoundError("Channel not found")
        await ChannelRepository.delete(db, item)
