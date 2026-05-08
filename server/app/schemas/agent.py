"""
Agent Pydantic schemas
"""
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.base import TimestampSchema, PaginatedResponse


class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(None, max_length=256)


class AgentCreate(AgentBase):
    tenant_id: str | None = Field(None, max_length=32)


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    description: str | None = Field(None, max_length=256)


class AgentStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(active|inactive)$")


class ModelConfig(BaseModel):
    model_name: str = "gpt-4o"
    first_round_thinking: bool = False
    subsequent_rounds_thinking: bool = False
    temperature: float = Field(default=0.01, ge=0, le=2)
    top_p: float = Field(default=0.85, ge=0, le=1)
    max_tokens: int = Field(default=4096, gt=0)

    @model_validator(mode="before")
    @classmethod
    def _migrate_thinking_mode(cls, data: Any) -> Any:
        """Backward compat: map legacy `thinking_mode` to the new split fields."""
        if not isinstance(data, dict):
            return data
        legacy = data.pop("thinking_mode", None)
        if legacy is not None:
            if "first_round_thinking" not in data:
                data["first_round_thinking"] = bool(legacy)
            if "subsequent_rounds_thinking" not in data:
                data["subsequent_rounds_thinking"] = bool(legacy)
        return data


class ContextConfig(BaseModel):
    max_rounds: int = Field(default=0, ge=0)
    history_tool_rounds: int = Field(default=0, ge=0, le=5)
    recent_full_tool_responses: int = Field(default=1, ge=1, le=5)


class PreRecallConfig(BaseModel):
    enabled: bool = False
    tool_id: int | None = None


class EngineConfig(BaseModel):
    system_prompt: str = Field(default="", max_length=10000)
    model: ModelConfig = Field(default_factory=ModelConfig)
    selected_tool_ids: list[int] = Field(default_factory=list)
    context: ContextConfig = Field(default_factory=ContextConfig)
    pre_recall: PreRecallConfig = Field(default_factory=PreRecallConfig)


class EngineConfigUpdate(BaseModel):
    """Partial update — all fields optional; only provided keys are merged."""
    system_prompt: str | None = Field(None, max_length=10000)
    model: ModelConfig | None = None
    selected_tool_ids: list[int] | None = None
    context: ContextConfig | None = None
    pre_recall: PreRecallConfig | None = None


class AgentResponse(AgentBase, TimestampSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    status: str = "active"
    engine_config: dict[str, Any] = Field(default_factory=dict)


class AgentListResponse(PaginatedResponse):
    items: list[AgentResponse]
