"""
Conversation Pydantic schemas
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import PaginatedResponse


class ConversationResponse(BaseModel):
    """Conversation item for list and detail responses"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    agent_id: int
    external_id: str
    external_user_id: str | None = None
    source: str = "chat"
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
    source: str = Field(default="chat", pattern=r"^(chat|api|embed)$")
    title: str | None = None
    display_name: str | None = Field(None, max_length=128)
    email: str | None = Field(None, max_length=256)
    phone: str | None = Field(None, max_length=32)
    avatar_url: str | None = Field(None, max_length=1024)
    metadata: dict | None = Field(default_factory=dict)


class ConversationEndRequest(BaseModel):
    """Used by the engine to mark a conversation as ended"""
    pass
