"""
Conversation Pydantic schemas
"""
import unicodedata
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.base import PaginatedResponse

MAX_CHANNEL_SOURCE_LENGTH = 64
SOURCE_WEBSDK = "websdk"
SOURCE_API = "api"
SOURCE_TESTCHAT = "testchat"
CONVERSATION_SOURCE_VALUES = (SOURCE_WEBSDK, SOURCE_API, SOURCE_TESTCHAT)
LEGACY_SOURCE_MAP = {
    "chat": SOURCE_WEBSDK,
    "embed": SOURCE_WEBSDK,
    "SDK_test": SOURCE_TESTCHAT,
}


def normalize_channel_source(value: Any) -> str | None:
    """Return a valid channel_source value, or None when it should be ignored."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_CHANNEL_SOURCE_LENGTH:
        return None
    if any(unicodedata.category(ch) == "Cc" for ch in normalized):
        return None
    return normalized


def normalize_conversation_source(value: Any, *, default: str = SOURCE_API) -> str:
    """Return a supported source value for new writes."""
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError("Invalid conversation source")

    normalized = value.strip()
    if not normalized:
        return default
    if normalized in CONVERSATION_SOURCE_VALUES:
        return normalized
    if normalized in LEGACY_SOURCE_MAP:
        return LEGACY_SOURCE_MAP[normalized]
    raise ValueError("Invalid conversation source")


class ConversationResponse(BaseModel):
    """Conversation item for list and detail responses"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    agent_id: int
    external_id: str
    external_user_id: str | None = None
    source: str = SOURCE_API
    channel_id: int | None = None
    channel_name: str | None = None
    channel_source: str | None = None
    is_test: bool = False
    status: str = "active"
    title: str | None = None
    display_name: str | None = None
    email: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    round_count: int = 0
    llm_call_count: int = 0
    tool_call_count: int = 0
    total_input_tokens: int = 0
    total_cached_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConversationListResponse(PaginatedResponse):
    items: list[ConversationResponse]


class ConversationDetailResponse(ConversationResponse):
    """Extended detail with computed fields"""
    duration_seconds: int | None = None


class ConversationCreate(BaseModel):
    """Used by the engine to create a new conversation"""
    tenant_id: str | None = Field(None, max_length=32)
    agent_id: int
    external_user_id: str | None = Field(None, max_length=128)
    source: str = SOURCE_API
    channel_id: int | None = Field(None, ge=1)
    channel_source: Any | None = None
    is_test: bool = False
    title: str | None = None
    display_name: str | None = Field(None, max_length=128)
    email: str | None = Field(None, max_length=256)
    phone: str | None = Field(None, max_length=32)
    avatar_url: str | None = Field(None, max_length=1024)
    metadata: dict | None = Field(default_factory=dict)

    @field_validator("source", mode="before")
    @classmethod
    def validate_source(cls, value: Any) -> str:
        return normalize_conversation_source(value, default=SOURCE_API)


class ConversationEndRequest(BaseModel):
    """Used by the engine to mark a conversation as ended"""
    pass
