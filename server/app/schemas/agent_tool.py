"""
AgentTool Pydantic schemas
"""
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import TimestampSchema


class AgentToolBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    tool_type: str = Field(..., pattern=r"^(search|doc_query|notebook|tool_response_fetch|python_code)$")


class AgentToolCreate(AgentToolBase):
    config: dict[str, Any] = Field(default_factory=dict)


class AgentToolUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = None
    config: dict[str, Any] | None = None


class AgentToolToggle(BaseModel):
    is_enabled: bool


class AgentToolResponse(AgentToolBase, TimestampSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: int
    tenant_id: str
    is_system: bool
    is_enabled: bool
    parameters_schema: dict[str, Any] | None = None
    config: dict[str, Any]


class AgentToolListResponse(BaseModel):
    items: list[AgentToolResponse]


class ToolExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="allow")


class ToolExecuteResponse(BaseModel):
    tool_name: str
    tool_type: str
    arguments: dict[str, Any]
    result: str
    duration_ms: int
