"""
AgentTool Pydantic schemas
"""
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import TimestampSchema


DOC_GREP_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "brief": {
            "type": "string",
            "description": "One-line summary for session log display; distinct from doc_id/pattern content",
        },
        "doc_id": {
            "type": "string",
            "description": "Document ID to search within. Obtain from prior search or doc_query results.",
        },
        "pattern": {
            "type": "string",
            "description": (
                "Python re module regular expression. For literal text, use plain string without "
                "special characters. Common syntax: . * + ? [] () | ^ $ \\d \\w \\s"
            ),
        },
        "ignore_case": {
            "type": "boolean",
            "description": "Case-insensitive matching (re.IGNORECASE). Default true.",
            "default": True,
        },
        "context_lines": {
            "type": "integer",
            "description": "Number of lines to show before and after each match (like grep -C). Default 5.",
            "default": 5,
            "minimum": 0,
            "maximum": 100,
        },
    },
    "required": ["brief", "doc_id", "pattern"],
}


class AgentToolBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    tool_type: str = Field(..., pattern=r"^(search|doc_query|doc_grep|notebook|tool_response_fetch|python_code)$")


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
