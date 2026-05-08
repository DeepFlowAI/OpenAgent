"""
AgentTool service
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.agent_tool_repository import AgentToolRepository
from app.schemas.agent_tool import AgentToolCreate, AgentToolUpdate, AgentToolToggle

logger = logging.getLogger(__name__)

# Shown on filter root — stops models from splitting ranges into multiple tool calls
_FILTER_SINGLE_TOOL_CALL_HINT = (
    "CRITICAL — one search tool call per user request: numeric or date ranges (e.g. 3.6–4.4) must "
    "appear in the SAME filter: use slice_meta/doc_meta as an array of two leaf nodes (implicit AND), "
    "or one root {op:and,value:[...]}. Never invoke the tool twice for lower bound and upper bound alone."
)

# OData 4.01 $filter-aligned JSON AST for LLM tool params (see docs/Filter-OData范式.md)
_FILTER_AST_DEFS: dict[str, dict] = {
    "FilterNode": {
        "title": "FilterNode",
        "description": (
            "Filter AST node: leaf compare, boolean logic, string functions, or any/all on arrays. "
            "Do not use gte/lte/neq; use ge/le/ne. For OR across conditions use op or/not nested nodes. "
            "Combine range bounds (ge+le on the same field) inside one filter in a single tool call."
        ),
        "oneOf": [
            {"$ref": "#/$defs/LeafComparison"},
            {"$ref": "#/$defs/LogicAndOr"},
            {"$ref": "#/$defs/LogicNot"},
            {"$ref": "#/$defs/StringFn"},
            {"$ref": "#/$defs/CollectionLambda"},
        ],
    },
    "LeafComparison": {
        "type": "object",
        "description": (
            "Scalar field comparison. For closed intervals on the same field, emit two leaves "
            "(ge low + le high) inside one filter via implicit-AND array or op and — not two tool calls."
        ),
        "properties": {
            "field": {"type": "string"},
            "op": {
                "type": "string",
                "enum": ["eq", "ne", "gt", "ge", "lt", "le", "in"],
                "description": "OData comparison operator; use in with value as array",
            },
            "value": {"description": "Scalar, or array when op is in"},
        },
        "required": ["field", "op", "value"],
        "additionalProperties": True,
    },
    "LogicAndOr": {
        "type": "object",
        "description": "Combine child conditions with AND or OR",
        "properties": {
            "op": {"type": "string", "enum": ["and", "or"]},
            "value": {
                "type": "array",
                "items": {"$ref": "#/$defs/FilterNode"},
                "minItems": 1,
            },
        },
        "required": ["op", "value"],
        "additionalProperties": True,
    },
    "LogicNot": {
        "type": "object",
        "description": "Negate one child (e.g. not in list: not + child with op in)",
        "properties": {
            "op": {"type": "string", "const": "not"},
            "value": {"$ref": "#/$defs/FilterNode"},
        },
        "required": ["op", "value"],
        "additionalProperties": True,
    },
    "StringFn": {
        "type": "object",
        "description": "String match on a field (uses fn, not op)",
        "properties": {
            "fn": {
                "type": "string",
                "enum": ["contains", "startswith", "endswith", "matchesPattern"],
            },
            "field": {"type": "string"},
            "value": {"type": "string"},
        },
        "required": ["fn", "field", "value"],
        "additionalProperties": True,
    },
    "CollectionLambda": {
        "type": "object",
        "description": (
            "Array field: any (at least one element matches) or all. "
            "predicate is usually { field, op: eq, value } for membership in a JSON array field."
        ),
        "properties": {
            "op": {"type": "string", "enum": ["any", "all"]},
            "field": {"type": "string", "description": "Name of the array metadata field"},
            "predicate": {"$ref": "#/$defs/FilterNode"},
            "var": {
                "type": "string",
                "description": "Optional lambda variable name; if set, predicate.field should match it",
            },
        },
        "required": ["op", "field", "predicate"],
        "additionalProperties": True,
    },
}


def _meta_filter_schema(description: str) -> dict:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "field": {"type": "string"},
                "op": {
                    "type": "string",
                    "enum": ["eq", "ne", "gt", "ge", "lt", "le", "in"],
                    "description": "OData comparison operator; use ge/le (not gte/lte). Use in with value as array.",
                },
                "value": {"description": "Scalar, or array when op is in"},
            },
            "required": ["field", "op", "value"],
        },
        "description": description,
    }


_FILTER_DIMENSION_SCHEMAS: dict[str, dict] = {
    "doc_ids": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Limit search to specific document IDs",
    },
    "doc_meta": _meta_filter_schema(
        "Document-level metadata filters. Array of conditions combined with implicit AND."
    ),
    "slice_meta": _meta_filter_schema(
        "Slice-level metadata filters. Array of conditions combined with implicit AND."
    ),
}

DEFAULT_FILTER_DIMENSIONS = {"doc_ids": True, "doc_meta": True, "slice_meta": True}


def _resolved_filter_dimensions(filter_dimensions: dict | None) -> dict:
    """Merge saved filter_dimensions with defaults.

    JSON null must NOT wipe a default True (dict merge would set the key to None, and then
    ``if dims.get(k)`` would drop doc_ids/doc_meta from the schema). Only explicit booleans
    override; missing keys and null values keep the default.
    """
    out = dict(DEFAULT_FILTER_DIMENSIONS)
    if not filter_dimensions:
        return out
    for k in DEFAULT_FILTER_DIMENSIONS:
        if k not in filter_dimensions:
            continue
        v = filter_dimensions[k]
        if v is None:
            continue
        out[k] = bool(v)
    return out


def build_search_parameters_schema(
    filter_dimensions: dict | None = None,
) -> dict:
    """Build search tool parameters schema based on enabled filter dimensions."""
    dims = _resolved_filter_dimensions(filter_dimensions)

    schema: dict = {
        "type": "object",
        "properties": {
            "brief": {
                "type": "string",
                "description": "One-line summary for session log display; distinct from query/filter content",
            },
            "query": {
                "type": "string",
                "description": "Search keywords or natural language query",
            },
        },
        "required": ["query", "brief"],
    }

    filter_props = {
        k: v for k, v in _FILTER_DIMENSION_SCHEMAS.items() if dims.get(k, False)
    }

    if filter_props:
        schema["properties"]["filter"] = {
            "type": "object",
            "description": (
                "Structured filters. Multiple conditions in doc_meta/slice_meta arrays "
                "are combined with implicit AND. "
                + _FILTER_SINGLE_TOOL_CALL_HINT
            ),
            "properties": filter_props,
        }

    return schema


SEARCH_PARAMETERS_SCHEMA: dict = build_search_parameters_schema()

DOC_QUERY_PARAMETERS_SCHEMA: dict = {
    "$defs": dict(_FILTER_AST_DEFS),
    "type": "object",
    "properties": {
        "brief": {
            "type": "string",
            "description": "One-line summary for session log display; distinct from query/filter content",
        },
        "query": {
            "type": "string",
            "description": "Search keywords for title, description, or table of contents",
        },
        "filter": {
            "type": "object",
            "description": (
                "Document metadata filters; OData AST in doc_meta ($defs.FilterNode). "
                "Implicit AND when doc_meta is an array of nodes. "
                + _FILTER_SINGLE_TOOL_CALL_HINT
            ),
            "properties": {
                "doc_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Limit to specific document IDs",
                },
                "doc_meta": _meta_filter_schema(
                    "Document-level metadata filters (doc_meta JSON). Same AST as search tool."
                ),
            },
        },
    },
    "required": ["brief"],
    "anyOf": [{"required": ["query"]}, {"required": ["filter"]}],
}

TOOL_TYPE_PARAMETERS_MAP: dict[str, dict] = {
    "search": SEARCH_PARAMETERS_SCHEMA,
    "doc_query": DOC_QUERY_PARAMETERS_SCHEMA,
}


class AgentToolService:

    @staticmethod
    async def get_tools_by_agent(db: AsyncSession, agent_id: int, tenant_id: str) -> dict:
        items = await AgentToolRepository.get_by_agent_id(db, agent_id)
        has_system = any(t.is_system for t in items)
        if not has_system:
            try:
                system_tools = await AgentToolRepository.create_system_tools(db, agent_id, tenant_id)
                items = system_tools + items
            except Exception:
                logger.warning("Failed to auto-create system tools for agent %s, retrying read", agent_id)
                await db.rollback()
                items = await AgentToolRepository.get_by_agent_id(db, agent_id)
        return {"items": items}

    @staticmethod
    async def get_by_id(db: AsyncSession, tool_id: int, agent_id: int):
        item = await AgentToolRepository.get_by_id(db, tool_id)
        if not item or item.agent_id != agent_id:
            raise NotFoundError("Agent tool not found")
        return item

    @staticmethod
    async def create(
        db: AsyncSession, agent_id: int, tenant_id: str, data: AgentToolCreate
    ):
        existing = await AgentToolRepository.get_by_agent_and_name(
            db, agent_id, data.name
        )
        if existing:
            raise ValidationError("Tool name already exists for this agent")

        tool_data = data.model_dump()
        tool_data["agent_id"] = agent_id
        tool_data["tenant_id"] = tenant_id
        tool_data["is_system"] = False

        if data.tool_type == "search":
            dims = (tool_data.get("config") or {}).get("filter_dimensions")
            tool_data["parameters_schema"] = build_search_parameters_schema(dims)
        else:
            tool_data["parameters_schema"] = TOOL_TYPE_PARAMETERS_MAP.get(data.tool_type)

        return await AgentToolRepository.create(db, tool_data)

    @staticmethod
    async def update(
        db: AsyncSession, tool_id: int, agent_id: int, data: AgentToolUpdate
    ):
        item = await AgentToolRepository.get_by_id(db, tool_id)
        if not item or item.agent_id != agent_id:
            raise NotFoundError("Agent tool not found")
        if item.is_system:
            raise ValidationError("Cannot modify system tool configuration")

        update_data = data.model_dump(exclude_unset=True)

        if "name" in update_data and update_data["name"] != item.name:
            existing = await AgentToolRepository.get_by_agent_and_name(
                db, agent_id, update_data["name"]
            )
            if existing:
                raise ValidationError("Tool name already exists for this agent")

        if item.tool_type == "search" and "config" in update_data:
            dims = (update_data["config"] or {}).get("filter_dimensions")
            update_data["parameters_schema"] = build_search_parameters_schema(dims)

        return await AgentToolRepository.update(db, item, update_data)

    @staticmethod
    async def toggle(
        db: AsyncSession, tool_id: int, agent_id: int, data: AgentToolToggle
    ):
        item = await AgentToolRepository.get_by_id(db, tool_id)
        if not item or item.agent_id != agent_id:
            raise NotFoundError("Agent tool not found")
        return await AgentToolRepository.update(db, item, {"is_enabled": data.is_enabled})

    @staticmethod
    async def delete(db: AsyncSession, tool_id: int, agent_id: int) -> None:
        item = await AgentToolRepository.get_by_id(db, tool_id)
        if not item or item.agent_id != agent_id:
            raise NotFoundError("Agent tool not found")
        if item.is_system:
            raise ValidationError("Cannot remove system tool")
        await AgentToolRepository.delete(db, item)

    @staticmethod
    async def create_system_tools(
        db: AsyncSession, agent_id: int, tenant_id: str
    ) -> list:
        return await AgentToolRepository.create_system_tools(db, agent_id, tenant_id)
