"""
Channel router
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.deps import get_db, require_scope
from app.schemas.channel import (
    ChannelCreate,
    ChannelUpdate,
    ChannelResponse,
    ChannelListResponse,
)
from app.services.channel_service import ChannelService

router = APIRouter(prefix="/channels", tags=["Channels"])


@router.get("", response_model=ChannelListResponse)
async def list_channels(
    tenant_id: str = Depends(require_scope("config")),
    page: int = 1,
    per_page: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """List channels for a tenant"""
    return await ChannelService.get_paginated(db, tenant_id, page=page, per_page=per_page)


@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: ChannelCreate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new channel"""
    body.tenant_id = tenant_id
    return await ChannelService.create(db, body)


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: int,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Get channel by ID"""
    channel = await ChannelService.get_by_id(db, channel_id)
    if channel.tenant_id != tenant_id:
        raise NotFoundError("Channel not found")
    return channel


@router.put("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: int,
    body: ChannelUpdate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Update channel"""
    channel = await ChannelService.get_by_id(db, channel_id)
    if channel.tenant_id != tenant_id:
        raise NotFoundError("Channel not found")
    return await ChannelService.update(db, channel_id, body)


@router.delete("/{channel_id}", status_code=status.HTTP_200_OK)
async def delete_channel(
    channel_id: int,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Delete channel"""
    channel = await ChannelService.get_by_id(db, channel_id)
    if channel.tenant_id != tenant_id:
        raise NotFoundError("Channel not found")
    await ChannelService.delete(db, channel_id)
    return {"message": "Deleted successfully"}


@router.post("/{channel_id}/secret-key", response_model=ChannelResponse)
async def generate_secret_key(
    channel_id: int,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Generate or rotate the channel secret key (used for embed token signing)."""
    channel = await ChannelService.get_by_id(db, channel_id)
    if channel.tenant_id != tenant_id:
        raise NotFoundError("Channel not found")
    return await ChannelService.generate_secret_key(db, channel_id)
