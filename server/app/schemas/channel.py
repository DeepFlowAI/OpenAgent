"""
Channel Pydantic schemas
"""
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.agent import ConversationSettingsConfig
from app.schemas.base import TimestampSchema, PaginatedResponse


SAME_PAGE_NAVIGATION_ALLOWLIST_KEY = "samePageNavigationUrlAllowlist"
MAX_SAME_PAGE_NAVIGATION_PATTERNS = 50
MAX_SAME_PAGE_NAVIGATION_PATTERN_LENGTH = 512
MATCH_ALL_PATTERNS = {"*", "http://*", "https://*"}


def _normalize_url_pattern(pattern: str) -> str:
    match = pattern.split("://", 1)
    if len(match) != 2:
        return pattern

    scheme, rest = match
    boundary = len(rest)
    for marker in ("/", "?", "#"):
        idx = rest.find(marker)
        if idx != -1:
            boundary = min(boundary, idx)

    host = rest[:boundary]
    suffix = rest[boundary:]
    return f"{scheme.lower()}://{host.lower()}{suffix}"


def normalize_same_page_navigation_allowlist(config: dict[str, Any]) -> dict[str, Any]:
    if SAME_PAGE_NAVIGATION_ALLOWLIST_KEY not in config:
        return config

    raw_value = config[SAME_PAGE_NAVIGATION_ALLOWLIST_KEY]
    if raw_value is None:
        values: list[str] = []
    elif isinstance(raw_value, str):
        values = raw_value.splitlines()
    elif isinstance(raw_value, list):
        values = raw_value
    else:
        raise ValueError("samePageNavigationUrlAllowlist must be a list of strings")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            raise ValueError("samePageNavigationUrlAllowlist must be a list of strings")

        pattern = item.strip()
        if not pattern:
            continue

        if len(pattern) > MAX_SAME_PAGE_NAVIGATION_PATTERN_LENGTH:
            raise ValueError("Each pattern must be 512 characters or fewer.")

        lowered = pattern.lower()
        if not (lowered.startswith("http://") or lowered.startswith("https://")):
            raise ValueError("Enter a URL pattern that starts with http:// or https://.")

        normalized_pattern = _normalize_url_pattern(pattern)
        if normalized_pattern.lower() in MATCH_ALL_PATTERNS:
            raise ValueError("The allowlist pattern cannot match every URL.")

        if normalized_pattern not in seen:
            normalized.append(normalized_pattern)
            seen.add(normalized_pattern)

    if len(normalized) > MAX_SAME_PAGE_NAVIGATION_PATTERNS:
        raise ValueError("Add up to 50 patterns.")

    return {
        **config,
        SAME_PAGE_NAVIGATION_ALLOWLIST_KEY: normalized,
    }


class ChannelBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(None, max_length=500)


class ChannelCreate(ChannelBase):
    tenant_id: str | None = Field(None, max_length=32)
    channel_type: str = Field(default="web-sdk", max_length=32)
    agent_id: int | None = None
    access_mode: str = Field(default="url", pattern=r"^(url|embed)$")
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def validate_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        return normalize_same_page_navigation_allowlist(value)


class ChannelUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    description: str | None = Field(None, max_length=500)
    agent_id: int | None = None
    access_mode: str | None = Field(None, pattern=r"^(url|embed)$")
    config: dict[str, Any] | None = None

    @field_validator("config")
    @classmethod
    def validate_config(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return value
        return normalize_same_page_navigation_allowlist(value)


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


class ChannelOptionResponse(BaseModel):
    """Lightweight channel option for filter dropdowns."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ChannelOptionListResponse(BaseModel):
    items: list[ChannelOptionResponse]


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
    conversation_settings: ConversationSettingsConfig = Field(
        default_factory=ConversationSettingsConfig
    )


class EmbedTokenRequest(BaseModel):
    """Request body for signing an embed token."""
    external_user_id: str | None = Field(None, max_length=128)
    display_name: str | None = Field(None, max_length=128)
    email: str | None = Field(None, max_length=256)
    phone: str | None = Field(None, max_length=32)
    avatar_url: str | None = Field(None, max_length=1024)
    source: str = Field(default="websdk", pattern=r"^(websdk|chat|embed)$")
    title: str | None = None
    metadata: dict[str, Any] | None = Field(default=None)
    ttl: int = Field(default=86400, ge=60, le=604800)


class EmbedTokenResponse(BaseModel):
    """Response for embed token signing."""
    token: str
    expires_in: int
