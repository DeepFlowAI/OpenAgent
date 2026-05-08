"""
ConversationStep Pydantic schemas — timeline, detail, and write schemas
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Timeline (lightweight, for log page left panel) ──

class StepTimelineItem(BaseModel):
    """Lightweight step representation for the conversation timeline.
    Excludes large fields (request_messages, request_tools) to keep payload small.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    round_number: int
    step_order: int
    step_type: str
    content: str | None = None

    # LLM summary fields (no request_messages / request_tools)
    model_name: str | None = None
    provider: str | None = None
    thinking_enabled: bool | None = None
    thinking_content: str | None = None
    finish_reason: str | None = None
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    duration_ms: int | None = None
    response_tool_calls: Any | None = None

    # Tool call summary fields
    tool_name: str | None = None
    tool_type: str | None = None
    tool_call_id: str | None = None
    brief: str | None = None

    # Relationships
    parent_step_id: int | None = None

    # Sub-req 3: client-supplied idempotency key (carried by user_message only).
    client_message_id: str | None = None

    # Common
    status: str = "success"
    error_message: str | None = None
    created_at: datetime | None = None


class ConversationTimelineResponse(BaseModel):
    """Full conversation timeline grouped for rendering"""
    conversation_id: int
    steps: list[StepTimelineItem]
    total_steps: int


# ── Step detail (full data, for LLM request/response modal) ──

class ToolCallStepItem(BaseModel):
    """Tool call step detail embedded in LLM step response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_order: int
    tool_name: str | None = None
    tool_type: str | None = None
    tool_call_id: str | None = None
    tool_arguments: Any | None = None
    tool_response: str | None = None
    brief: str | None = None
    status: str = "success"
    error_message: str | None = None
    duration_ms: int | None = None
    created_at: datetime | None = None


class StepDetailResponse(BaseModel):
    """Complete step data including large fields for LLM modal"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    round_number: int
    step_order: int
    step_type: str
    content: str | None = None

    # Full LLM call fields
    model_name: str | None = None
    provider: str | None = None
    thinking_enabled: bool | None = None
    thinking_content: str | None = None
    request_messages: Any | None = None
    request_tools: Any | None = None
    request_params: Any | None = None
    response_tool_calls: Any | None = None
    finish_reason: str | None = None
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    duration_ms: int | None = None

    # Full tool call fields
    tool_name: str | None = None
    tool_type: str | None = None
    tool_call_id: str | None = None
    tool_arguments: Any | None = None
    tool_response: str | None = None
    brief: str | None = None

    # Relationships
    parent_step_id: int | None = None

    # Sub-req 3: client-supplied idempotency key (carried by user_message only).
    client_message_id: str | None = None

    # Child tool call steps (populated when step_type == 'llm_call')
    tool_call_steps: list[ToolCallStepItem] = []

    # Common
    status: str = "success"
    error_message: str | None = None
    created_at: datetime | None = None


# ── Write schemas (used by Agent engine) ──

class StepCreate(BaseModel):
    """Create a new step in a conversation"""
    round_number: int = Field(..., ge=1)
    step_type: str = Field(..., pattern=r"^(user_message|llm_call|tool_call|assistant_message)$")
    content: str | None = None

    # LLM call fields
    model_name: str | None = None
    provider: str | None = None
    thinking_enabled: bool | None = None
    thinking_content: str | None = None
    request_messages: Any | None = None
    request_tools: Any | None = None
    request_params: Any | None = None
    response_tool_calls: Any | None = None
    finish_reason: str | None = None
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    duration_ms: int | None = None

    # Tool call fields
    tool_name: str | None = None
    tool_type: str | None = None
    tool_call_id: str | None = None
    tool_arguments: Any | None = None
    tool_response: str | None = None
    brief: str | None = None

    # Relationships
    parent_step_id: int | None = None

    # Sub-req 3: client-supplied idempotency key (carried by user_message only).
    client_message_id: str | None = Field(None, max_length=64)

    # Common
    # `incomplete` (sub-req 2): set on llm_call steps whose stream was cut off
    # mid-flight (GIVE_UP / client disconnect / provider api_error). The partial
    # content is preserved on the step but the resume/timeline/history paths
    # treat them as discardable.
    status: str = Field(default="success", pattern=r"^(pending|running|success|error|incomplete)$")
    error_message: str | None = None
    metadata: dict | None = Field(default_factory=dict)


class StepUpdate(BaseModel):
    """Update an existing step (e.g. when LLM response arrives)"""
    content: str | None = None
    thinking_content: str | None = None
    response_tool_calls: Any | None = None
    finish_reason: str | None = None
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    duration_ms: int | None = None
    tool_response: str | None = None
    brief: str | None = None
    status: str | None = Field(None, pattern=r"^(pending|running|success|error|incomplete)$")
    error_message: str | None = None
