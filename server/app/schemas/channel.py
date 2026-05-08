"""
Channel Pydantic schemas
"""
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import TimestampSchema, PaginatedResponse


class ChannelBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(None, max_length=500)


class ChannelCreate(ChannelBase):
    tenant_id: str | None = Field(None, max_length=32)
    channel_type: str = Field(default="web-sdk", max_length=32)
    agent_id: int | None = None
    access_mode: str = Field(default="url", pattern=r"^(url|embed)$")
    config: dict[str, Any] = Field(default_factory=dict)


class ChannelUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    description: str | None = Field(None, max_length=500)
    agent_id: int | None = None
    access_mode: str | None = Field(None, pattern=r"^(url|embed)$")
    config: dict[str, Any] | None = None


class ChannelResponse(ChannelBase, TimestampSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    token: str
    channel_type: str = "web-sdk"
    agent_id: int | None = None
    access_mode: str = "url"
    secret_key: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class ChannelListResponse(PaginatedResponse):
    items: list[ChannelResponse]


class PublicChannelResponse(ChannelBase, TimestampSchema):
    """Channel response for public (browser-facing) endpoints.

    Excludes sensitive fields: ``secret_key`` (HMAC key for embed-token signing)
    and ``tenant_id`` (internal isolation key). Browser SDK / chat page only
    needs ``id``, ``token``, ``agent_id``, ``access_mode`` and ``config``.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    token: str
    channel_type: str = "web-sdk"
    agent_id: int | None = None
    access_mode: str = "url"
    config: dict[str, Any] = Field(default_factory=dict)


class EmbedTokenRequest(BaseModel):
    """Request body for signing an embed token."""
    external_user_id: str | None = Field(None, max_length=128)
    display_name: str | None = Field(None, max_length=128)
    email: str | None = Field(None, max_length=256)
    phone: str | None = Field(None, max_length=32)
    avatar_url: str | None = Field(None, max_length=1024)
    source: str = Field(default="embed", pattern=r"^(embed|chat)$")
    title: str | None = None
    metadata: dict[str, Any] | None = Field(default=None)
    ttl: int = Field(default=86400, ge=60, le=604800)


class EmbedTokenResponse(BaseModel):
    """Response for embed token signing."""
    token: str
    expires_in: int
