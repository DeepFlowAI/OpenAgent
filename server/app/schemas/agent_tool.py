"""
AgentTool Pydantic schemas
"""
from typing import Any
from copy import deepcopy
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import TimestampSchema


NOTEBOOK_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "brief": {
            "type": "string",
            "description": "One-line summary for session log display",
        },
        "action": {
            "type": "string",
            "enum": ["add", "remove"],
            "description": "Operation type: add or remove items",
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slice_id": {
                        "type": "string",
                        "description": "Slice ID to add as a slice note.",
                    },
                    "doc_id": {
                        "type": "string",
                        "description": (
                            "Document ID to add as a doc note, or pair with line "
                            "for a grep_match note."
                        ),
                    },
                    "line": {
                        "type": "string",
                        "description": (
                            "Line number from a prior doc_grep <match>; pair with "
                            "doc_id to add a grep_match note."
                        ),
                    },
                    "text": {
                        "type": "string",
                        "description": "Free-form text content or annotation to save.",
                    },
                    "id": {
                        "type": "string",
                        "description": "Note entry ID (note_xxx). Used in remove action.",
                    },
                },
            },
            "description": (
                "List of items to add or remove. For add: use slice_id, doc_id, "
                "doc_id + line for grep_match, text, or a combination. For remove: use id."
            ),
        },
    },
    "required": ["brief", "action", "items"],
}


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

HUMAN_HANDOFF_TOOL_TYPE = "human_handoff"
HUMAN_HANDOFF_TOOL_NAME = "human_handoff"
HUMAN_HANDOFF_EVENT_STEP_TYPE = "human_handoff_event"
HUMAN_HANDOFF_EVENT_KIND = "human_handoff"
HUMAN_HANDOFF_SCHEMA_VERSION = 1

HUMAN_HANDOFF_ROUTE_FIELD_DEFAULTS: dict[str, bool] = {
    "agent_group_id": True,
    "agent_id": False,
    "business_type": True,
}

DEFAULT_HUMAN_HANDOFF_CONFIG: dict[str, Any] = {
    "service_hours_id": None,
    "route_fields": dict(HUMAN_HANDOFF_ROUTE_FIELD_DEFAULTS),
}

HUMAN_HANDOFF_FIELD_MAX_LENGTHS: dict[str, int] = {
    "brief": 200,
    "reason": 1000,
    "agent_group_id": 128,
    "agent_id": 128,
    "business_type": 128,
    "urgency": 16,
    "user_message": 1000,
}

_HUMAN_HANDOFF_FIXED_PROPERTIES: dict[str, dict[str, Any]] = {
    "brief": {
        "type": "string",
        "description": "One-line summary for session log display.",
        "maxLength": HUMAN_HANDOFF_FIELD_MAX_LENGTHS["brief"],
    },
    "reason": {
        "type": "string",
        "description": "Reason for requesting a human handoff, for support staff and audit.",
        "maxLength": HUMAN_HANDOFF_FIELD_MAX_LENGTHS["reason"],
    },
    "urgency": {
        "type": "string",
        "enum": ["normal", "high"],
        "description": "Priority hint. Use normal unless the user clearly needs urgent handling.",
    },
    "user_message": {
        "type": "string",
        "description": "Original user message excerpt or short summary for human support.",
        "maxLength": HUMAN_HANDOFF_FIELD_MAX_LENGTHS["user_message"],
    },
}

_HUMAN_HANDOFF_ROUTE_PROPERTIES: dict[str, dict[str, Any]] = {
    "agent_group_id": {
        "type": "string",
        "description": "Target human support group ID.",
        "maxLength": HUMAN_HANDOFF_FIELD_MAX_LENGTHS["agent_group_id"],
    },
    "agent_id": {
        "type": "string",
        "description": "Target human support agent ID, not the AI Agent ID.",
        "maxLength": HUMAN_HANDOFF_FIELD_MAX_LENGTHS["agent_id"],
    },
    "business_type": {
        "type": "string",
        "description": "Business line or routing type, such as complaint, after-sales, or technical support.",
        "maxLength": HUMAN_HANDOFF_FIELD_MAX_LENGTHS["business_type"],
    },
}


def normalize_human_handoff_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Return a normalized human handoff config with stable defaults."""
    raw = config if isinstance(config, dict) else {}
    route_raw = raw.get("route_fields")
    route_raw = route_raw if isinstance(route_raw, dict) else {}

    service_hours_id: int | None = None
    raw_service_hours_id = raw.get("service_hours_id")
    if isinstance(raw_service_hours_id, int) and raw_service_hours_id > 0:
        service_hours_id = raw_service_hours_id
    elif isinstance(raw_service_hours_id, str) and raw_service_hours_id.isdigit():
        parsed = int(raw_service_hours_id)
        service_hours_id = parsed if parsed > 0 else None

    return {
        "service_hours_id": service_hours_id,
        "route_fields": {
            key: bool(route_raw.get(key, default))
            for key, default in HUMAN_HANDOFF_ROUTE_FIELD_DEFAULTS.items()
        },
    }


def build_human_handoff_parameters_schema(
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the LLM-visible parameters schema from route field switches."""
    normalized = normalize_human_handoff_config(config)
    properties = deepcopy(_HUMAN_HANDOFF_FIXED_PROPERTIES)
    route_fields = normalized["route_fields"]

    for key, enabled in route_fields.items():
        if enabled:
            properties[key] = deepcopy(_HUMAN_HANDOFF_ROUTE_PROPERTIES[key])

    return {
        "type": "object",
        "properties": properties,
        "required": ["brief", "reason"],
        "additionalProperties": False,
    }


HUMAN_HANDOFF_PARAMETERS_SCHEMA = build_human_handoff_parameters_schema(
    DEFAULT_HUMAN_HANDOFF_CONFIG
)


def _trim_handoff_string(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    trimmed = value.strip()
    if required and not trimmed:
        raise ValueError(f"{field} is required")
    if not trimmed:
        return None
    return trimmed[:HUMAN_HANDOFF_FIELD_MAX_LENGTHS[field]]


def normalize_human_handoff_arguments(
    args: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Validate and trim tool arguments, dropping disabled route fields."""
    normalized_config = normalize_human_handoff_config(config)
    result: dict[str, str] = {
        "brief": _trim_handoff_string(args.get("brief"), "brief", required=True) or "",
        "reason": _trim_handoff_string(args.get("reason"), "reason", required=True) or "",
    }

    urgency = _trim_handoff_string(args.get("urgency"), "urgency")
    if urgency is not None:
        if urgency not in {"normal", "high"}:
            raise ValueError("urgency must be normal or high")
        result["urgency"] = urgency

    user_message = _trim_handoff_string(args.get("user_message"), "user_message")
    if user_message is not None:
        result["user_message"] = user_message

    for key, enabled in normalized_config["route_fields"].items():
        if not enabled:
            continue
        value = _trim_handoff_string(args.get(key), key)
        if value is not None:
            result[key] = value

    return result


class AgentToolBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    tool_type: str = Field(..., pattern=r"^(search|doc_query|doc_grep|notebook|tool_response_fetch|python_code|human_handoff)$")


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
