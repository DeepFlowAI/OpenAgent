"""
Agent message preprocessing rule Pydantic schemas
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import TimestampSchema


PreprocessingAction = Literal["prefix", "suffix"]


class AgentMessagePreprocessingRuleBase(BaseModel):
    condition: str = Field(..., min_length=1, max_length=1000)
    action: PreprocessingAction = "prefix"
    value: str = Field(default="", max_length=500)


class AgentMessagePreprocessingRuleCreate(AgentMessagePreprocessingRuleBase):
    pass


class AgentMessagePreprocessingRuleUpdate(BaseModel):
    condition: str | None = Field(None, min_length=1, max_length=1000)
    action: PreprocessingAction | None = None
    value: str | None = Field(None, max_length=500)


class AgentMessagePreprocessingRuleResponse(
    AgentMessagePreprocessingRuleBase, TimestampSchema
):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: int
    tenant_id: str


class AgentMessagePreprocessingRuleListResponse(BaseModel):
    items: list[AgentMessagePreprocessingRuleResponse]
    total: int
