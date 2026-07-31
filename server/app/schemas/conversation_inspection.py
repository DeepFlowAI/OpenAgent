"""Schemas for human conversation quality inspection."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator

InspectionTag = Literal["good", "pass", "bad"]
ISSUE_TYPES = {"factual_error", "intent_misunderstood", "irrelevant", "unresolved", "tool_error", "incomplete", "expression", "safety", "other"}


class InspectionSave(BaseModel):
    tag: InspectionTag
    issue_types: list[str] = Field(default_factory=list)
    issue_description: str | None = Field(None, max_length=500)

    @field_validator("issue_types")
    @classmethod
    def valid_issue_types(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(item not in ISSUE_TYPES for item in value):
            raise ValueError("Invalid issue type")
        return value


class InspectionResponse(BaseModel):
    step_id: int
    tag: InspectionTag
    issue_types: list[str] = Field(default_factory=list)
    issue_description: str | None = None
    updated_at: datetime | None = None


class QualityConversationItem(BaseModel):
    id: int
    external_id: str
    external_user_id: str | None = None
    source: str
    channel_id: int | None = None
    channel_name: str | None = None
    channel_source: str | None = None
    started_at: datetime | None = None
    round_count: int = 0
    inspection_status: Literal["pending", "in_progress", "completed"]
    inspection_tag: InspectionTag | None = None
    assistant_reply_count: int = 0
    inspected_count: int = 0


class QualityQueueResponse(BaseModel):
    items: list[QualityConversationItem]
    total: int
