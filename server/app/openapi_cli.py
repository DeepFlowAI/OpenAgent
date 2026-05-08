"""
OpenAgent OpenAPI command line client.

PyPI package: `deepflow-openagent-cli` (console script `deepflow_openagent_cli`).
Repo usage:

    python -m app.openapi_cli docs list
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_HOST = "http://localhost:5001"
ENV_HOST = "OPENAGENT_HOST"
ENV_API_KEY = "OPENAGENT_API_KEY"
# Legacy env names from before the OpenAgent rename. Read-only fallback so
# existing local shells / CI configs keep working; new docs only mention
# the OPENAGENT_* names.
LEGACY_ENV_HOST = "NEWAGENT_HOST"
LEGACY_ENV_API_KEY = "NEWAGENT_API_KEY"


class CliError(Exception):
    """Expected CLI error with a user-facing message."""


@dataclass(frozen=True)
class ParamDoc:
    name: str
    type: str
    required: bool
    description: str


@dataclass(frozen=True)
class EndpointDoc:
    key: str
    method: str
    path: str
    scope: str | None
    summary: str
    path_params: list[ParamDoc] = field(default_factory=list)
    query_params: list[ParamDoc] = field(default_factory=list)
    body_fields: list[ParamDoc] = field(default_factory=list)
    response: str = ""
    errors: list[str] = field(default_factory=list)
    example: str = ""


def _param(name: str, type_: str, required: bool, description: str) -> ParamDoc:
    return ParamDoc(name=name, type=type_, required=required, description=description)


ENDPOINTS: tuple[EndpointDoc, ...] = (
    EndpointDoc(
        key="knowledge.search",
        method="POST",
        path="/api/v1/knowledge-bases/{kb_id}/search",
        scope="chat",
        summary="Search slices in a knowledge base with hybrid, BM25, vector, optional reranker, and permission context.",
        path_params=[_param("kb_id", "integer", True, "Knowledge base ID.")],
        body_fields=[
            _param("query", "string", True, "Search query, 1-512 characters."),
            _param("filter", "object", False, "Optional doc_ids, doc_meta, and slice_meta filter AST."),
            _param("search", "object", False, "Search config: mode hybrid/bm25/vector and weights."),
            _param("reranker", "object", False, "Optional reranker config."),
            _param("highlight", "object", False, "Optional highlight config."),
            _param("pagination", "object", False, "Pagination config: limit 1-500, offset >= 0."),
            _param("subject_context", "object", False, "Optional customer context for permission evaluation."),
        ],
        response="JSON object with total and items[].",
        errors=["401 missing or invalid API key", "404 knowledge base not found", "422 validation error"],
        example="python -m app.openapi_cli knowledge search 1 --query 'pricing'",
    ),
    EndpointDoc(
        key="knowledge.markdown",
        method="GET",
        path="/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/markdown",
        scope="chat",
        summary="Fetch readable Markdown content for a document.",
        path_params=[
            _param("kb_id", "integer", True, "Knowledge base ID."),
            _param("doc_id", "integer", True, "Document ID."),
        ],
        response="Markdown text.",
        errors=["401 missing or invalid API key", "404 document not found"],
        example="python -m app.openapi_cli knowledge markdown 1 20 --raw",
    ),
    EndpointDoc(
        key="conversations.create",
        method="POST",
        path="/api/v1/agents/{agent_id}/conversations",
        scope="chat",
        summary="Create a conversation for an agent. tenant_id is injected by the server from the API key.",
        path_params=[_param("agent_id", "integer", True, "Agent ID.")],
        body_fields=[
            _param("agent_id", "integer", True, "Agent ID. The CLI fills this from the path when omitted."),
            _param("external_user_id", "string", False, "External user ID, max 128 chars."),
            _param("source", "string", False, "chat, api, or embed. Defaults to api in the CLI."),
            _param("title", "string", False, "Conversation title."),
            _param("display_name", "string", False, "Customer display name."),
            _param("email", "string", False, "Customer email."),
            _param("phone", "string", False, "Customer phone."),
            _param("avatar_url", "string", False, "Customer avatar URL."),
            _param("metadata", "object", False, "Arbitrary metadata."),
        ],
        response="ConversationResponse.",
        errors=["401 missing or invalid API key", "404 agent not found", "422 validation error"],
        example="python -m app.openapi_cli conversations create 1 --title 'Support' --source api",
    ),
    EndpointDoc(
        key="conversations.list",
        method="GET",
        path="/api/v1/agents/{agent_id}/conversations",
        scope="chat",
        summary="List conversations for an agent with pagination and filters.",
        path_params=[_param("agent_id", "integer", True, "Agent ID.")],
        query_params=[
            _param("page", "integer", False, "Page number."),
            _param("per_page", "integer", False, "Items per page."),
            _param("start_time", "string", False, "Start time filter."),
            _param("end_time", "string", False, "End time filter."),
            _param("status_filter", "string", False, "Conversation status."),
            _param("source", "string", False, "chat, api, or embed."),
            _param("conversation_id", "string", False, "Conversation external ID filter."),
            _param("external_user_id", "string", False, "External user ID filter."),
            _param("search", "string", False, "Keyword search."),
        ],
        response="ConversationListResponse.",
        errors=["401 missing or invalid API key", "404 agent not found"],
        example="python -m app.openapi_cli conversations list 1 --source api --page 1 --per-page 10",
    ),
    EndpointDoc(
        key="conversations.get",
        method="GET",
        path="/api/v1/agents/{agent_id}/conversations/{conversation_id}",
        scope="chat",
        summary="Get conversation detail.",
        path_params=[
            _param("agent_id", "integer", True, "Agent ID."),
            _param("conversation_id", "integer", True, "Conversation ID."),
        ],
        response="ConversationDetailResponse.",
        errors=["401 missing or invalid API key", "404 conversation not found"],
        example="python -m app.openapi_cli conversations get 1 42",
    ),
    EndpointDoc(
        key="conversations.end",
        method="POST",
        path="/api/v1/agents/{agent_id}/conversations/{conversation_id}/end",
        scope="chat",
        summary="Mark a conversation as ended.",
        path_params=[
            _param("agent_id", "integer", True, "Agent ID."),
            _param("conversation_id", "integer", True, "Conversation ID."),
        ],
        response="ConversationResponse.",
        errors=["401 missing or invalid API key", "404 conversation not found"],
        example="python -m app.openapi_cli conversations end 1 42",
    ),
    EndpointDoc(
        key="chat.stream",
        method="POST",
        path="/api/v1/agents/{agent_id}/chat",
        scope="chat",
        summary="Send a message to an agent and stream Server-Sent Events.",
        path_params=[_param("agent_id", "integer", True, "Agent ID.")],
        body_fields=[
            _param("message", "string", True, "User message, 1-32000 characters."),
            _param("conversation_id", "integer", False, "Existing conversation ID for continuation."),
            _param("conversation_external_id", "string", False, "External conversation ID for log correlation."),
            _param("request_id", "string", False, "Client request ID for log correlation."),
            _param("customer_context", "object", False, "Customer context used only when creating a conversation."),
            _param("resume", "boolean", False, "Resume an interrupted stream."),
        ],
        response="text/event-stream with conversation_created, content, thinking, tool_call, tool_result, done, and error events.",
        errors=["401 missing or invalid API key", "404 agent not found", "422 validation error"],
        example="python -m app.openapi_cli chat 1 --message 'Hello' --request-id req_001",
    ),
    EndpointDoc(
        key="steps.list",
        method="GET",
        path="/api/v1/agents/{agent_id}/conversations/{conversation_id}/steps",
        scope="chat",
        summary="List execution timeline steps for a conversation.",
        path_params=[
            _param("agent_id", "integer", True, "Agent ID."),
            _param("conversation_id", "integer", True, "Conversation ID."),
        ],
        response="Object with conversation_id, total_steps, and steps[].",
        errors=["401 missing or invalid API key", "404 conversation not found"],
        example="python -m app.openapi_cli steps 1 42",
    ),
    EndpointDoc(
        key="agents.list",
        method="GET",
        path="/api/v1/agents",
        scope="config",
        summary="List agents for the current tenant.",
        query_params=[
            _param("status_filter", "string", False, "active or inactive."),
            _param("page", "integer", False, "Page number."),
            _param("per_page", "integer", False, "Items per page."),
        ],
        response="AgentListResponse.",
        errors=["401 missing or invalid API key", "403 scope missing"],
        example="python -m app.openapi_cli agents list --status-filter active",
    ),
    EndpointDoc(
        key="agents.create",
        method="POST",
        path="/api/v1/agents",
        scope="config",
        summary="Create an agent for the current tenant.",
        body_fields=[
            _param("name", "string", True, "Agent name, 1-64 chars."),
            _param("description", "string", False, "Agent description, max 256 chars."),
        ],
        response="AgentResponse.",
        errors=["401 missing or invalid API key", "403 scope missing", "422 validation error"],
        example="python -m app.openapi_cli agents create --name 'Support Agent'",
    ),
    EndpointDoc(
        key="agents.get",
        method="GET",
        path="/api/v1/agents/{agent_id}",
        scope="config",
        summary="Get agent detail including engine_config.",
        path_params=[_param("agent_id", "integer", True, "Agent ID.")],
        response="AgentResponse.",
        errors=["401 missing or invalid API key", "403 scope missing", "404 agent not found"],
        example="python -m app.openapi_cli agents get 1",
    ),
    EndpointDoc(
        key="agents.update",
        method="PUT",
        path="/api/v1/agents/{agent_id}",
        scope="config",
        summary="Update agent name or description.",
        path_params=[_param("agent_id", "integer", True, "Agent ID.")],
        body_fields=[
            _param("name", "string", False, "Agent name, 1-64 chars."),
            _param("description", "string", False, "Agent description, max 256 chars."),
        ],
        response="AgentResponse.",
        errors=["401 missing or invalid API key", "403 scope missing", "404 agent not found", "422 validation error"],
        example="python -m app.openapi_cli agents update 1 --name 'New name'",
    ),
    EndpointDoc(
        key="agents.status",
        method="PUT",
        path="/api/v1/agents/{agent_id}/status",
        scope="config",
        summary="Set agent status to active or inactive.",
        path_params=[_param("agent_id", "integer", True, "Agent ID.")],
        body_fields=[_param("status", "string", True, "active or inactive.")],
        response="AgentResponse.",
        errors=["401 missing or invalid API key", "403 scope missing", "404 agent not found", "422 validation error"],
        example="python -m app.openapi_cli agents status 1 inactive",
    ),
    EndpointDoc(
        key="agents.engine_config",
        method="PUT",
        path="/api/v1/agents/{agent_id}/engine-config",
        scope="config",
        summary="Partially update system_prompt, model, selected_tool_ids, context, or pre_recall.",
        path_params=[_param("agent_id", "integer", True, "Agent ID.")],
        body_fields=[
            _param("system_prompt", "string", False, "System prompt, max 10000 chars."),
            _param("model", "object", False, "Model config."),
            _param("selected_tool_ids", "array[integer]", False, "Enabled tool IDs."),
            _param("context", "object", False, "Context policy."),
            _param("pre_recall", "object", False, "Pre-recall config."),
        ],
        response="AgentResponse with updated engine_config.",
        errors=["401 missing or invalid API key", "403 scope missing", "404 agent not found", "422 validation error"],
        example="python -m app.openapi_cli agents engine-config 1 --json '{\"system_prompt\":\"You are helpful.\"}'",
    ),
    EndpointDoc(
        key="tools.list",
        method="GET",
        path="/api/v1/agents/{agent_id}/tools",
        scope="config",
        summary="List system and custom tools for an agent.",
        path_params=[_param("agent_id", "integer", True, "Agent ID.")],
        response="AgentToolListResponse.",
        errors=["401 missing or invalid API key", "403 scope missing", "404 agent not found"],
        example="python -m app.openapi_cli tools list 1",
    ),
    EndpointDoc(
        key="tools.create",
        method="POST",
        path="/api/v1/agents/{agent_id}/tools",
        scope="config",
        summary="Create a custom tool for an agent.",
        path_params=[_param("agent_id", "integer", True, "Agent ID.")],
        body_fields=[
            _param("name", "string", True, "Tool name, 1-128 chars."),
            _param("description", "string", False, "Tool description."),
            _param("tool_type", "string", True, "search, doc_query, notebook, tool_response_fetch, or python_code."),
            _param("config", "object", False, "Tool config."),
        ],
        response="AgentToolResponse.",
        errors=["401 missing or invalid API key", "403 scope missing", "404 agent not found", "422 validation error"],
        example="python -m app.openapi_cli tools create 1 --name Search --tool-type search --json '{\"config\":{\"kb_ids\":[1]}}'",
    ),
    EndpointDoc(
        key="tools.get",
        method="GET",
        path="/api/v1/agents/{agent_id}/tools/{tool_id}",
        scope="config",
        summary="Get tool detail.",
        path_params=[
            _param("agent_id", "integer", True, "Agent ID."),
            _param("tool_id", "integer", True, "Tool ID."),
        ],
        response="AgentToolResponse.",
        errors=["401 missing or invalid API key", "403 scope missing", "404 tool not found"],
        example="python -m app.openapi_cli tools get 1 2",
    ),
    EndpointDoc(
        key="tools.update",
        method="PUT",
        path="/api/v1/agents/{agent_id}/tools/{tool_id}",
        scope="config",
        summary="Update a custom tool. System tools cannot be modified.",
        path_params=[
            _param("agent_id", "integer", True, "Agent ID."),
            _param("tool_id", "integer", True, "Tool ID."),
        ],
        body_fields=[
            _param("name", "string", False, "Tool name."),
            _param("description", "string", False, "Tool description."),
            _param("config", "object", False, "Tool config."),
        ],
        response="AgentToolResponse.",
        errors=["401 missing or invalid API key", "403 scope missing", "404 tool not found", "422 validation error"],
        example="python -m app.openapi_cli tools update 1 2 --json '{\"config\":{\"kb_ids\":[1,2]}}'",
    ),
    EndpointDoc(
        key="tools.toggle",
        method="PUT",
        path="/api/v1/agents/{agent_id}/tools/{tool_id}/toggle",
        scope="config",
        summary="Enable or disable a tool.",
        path_params=[
            _param("agent_id", "integer", True, "Agent ID."),
            _param("tool_id", "integer", True, "Tool ID."),
        ],
        body_fields=[_param("is_enabled", "boolean", True, "true to enable, false to disable.")],
        response="AgentToolResponse.",
        errors=["401 missing or invalid API key", "403 scope missing", "404 tool not found"],
        example="python -m app.openapi_cli tools toggle 1 2 false",
    ),
    EndpointDoc(
        key="tools.delete",
        method="DELETE",
        path="/api/v1/agents/{agent_id}/tools/{tool_id}",
        scope="config",
        summary="Delete a custom tool. System tools cannot be deleted.",
        path_params=[
            _param("agent_id", "integer", True, "Agent ID."),
            _param("tool_id", "integer", True, "Tool ID."),
        ],
        response='{"message": "Tool removed successfully"}',
        errors=["401 missing or invalid API key", "403 scope missing", "404 tool not found", "422 system tool cannot be deleted"],
        example="python -m app.openapi_cli tools delete 1 2",
    ),
    EndpointDoc(
        key="tools.execute",
        method="POST",
        path="/api/v1/agents/{agent_id}/tools/{tool_id}/execute",
        scope="config",
        summary="Debug execute a tool with arbitrary JSON arguments.",
        path_params=[
            _param("agent_id", "integer", True, "Agent ID."),
            _param("tool_id", "integer", True, "Tool ID."),
        ],
        query_params=[_param("conversation_id", "integer", False, "Conversation ID for tool context.")],
        body_fields=[_param("*", "object", False, "Tool-specific arguments.")],
        response="ToolExecuteResponse.",
        errors=["401 missing or invalid API key", "403 scope missing", "404 tool not found", "422 validation error"],
        example="python -m app.openapi_cli tools execute 1 2 --json '{\"query\":\"pricing\"}'",
    ),
    EndpointDoc(
        key="channels.list",
        method="GET",
        path="/api/v1/channels",
        scope="config",
        summary="List Web SDK channels for the current tenant.",
        query_params=[
            _param("page", "integer", False, "Page number."),
            _param("per_page", "integer", False, "Items per page."),
        ],
        response="ChannelListResponse.",
        errors=["401 missing or invalid API key", "403 scope missing"],
        example="python -m app.openapi_cli channels list --page 1 --per-page 10",
    ),
    EndpointDoc(
        key="channels.create",
        method="POST",
        path="/api/v1/channels",
        scope="config",
        summary="Create a Web SDK channel. tenant_id is injected by the server.",
        body_fields=[
            _param("name", "string", True, "Channel name, 1-64 chars."),
            _param("description", "string", False, "Description, max 500 chars."),
            _param("channel_type", "string", False, "Defaults to web-sdk."),
            _param("agent_id", "integer", False, "Bound agent ID."),
            _param("access_mode", "string", False, "url or embed."),
            _param("config", "object", False, "Appearance and behavior config."),
        ],
        response="ChannelResponse.",
        errors=["400 duplicate name", "401 missing or invalid API key", "403 scope missing", "422 validation error"],
        example="python -m app.openapi_cli channels create --name Website --agent-id 1 --access-mode embed",
    ),
    EndpointDoc(
        key="channels.get",
        method="GET",
        path="/api/v1/channels/{channel_id}",
        scope="config",
        summary="Get channel detail.",
        path_params=[_param("channel_id", "integer", True, "Channel ID.")],
        response="ChannelResponse.",
        errors=["401 missing or invalid API key", "403 scope missing", "404 channel not found"],
        example="python -m app.openapi_cli channels get 1",
    ),
    EndpointDoc(
        key="channels.update",
        method="PUT",
        path="/api/v1/channels/{channel_id}",
        scope="config",
        summary="Update channel name, description, agent_id, access_mode, or config.",
        path_params=[_param("channel_id", "integer", True, "Channel ID.")],
        body_fields=[
            _param("name", "string", False, "Channel name."),
            _param("description", "string", False, "Channel description."),
            _param("agent_id", "integer", False, "Bound agent ID."),
            _param("access_mode", "string", False, "url or embed."),
            _param("config", "object", False, "Appearance and behavior config."),
        ],
        response="ChannelResponse.",
        errors=["400 duplicate name", "401 missing or invalid API key", "403 scope missing", "404 channel not found", "422 validation error"],
        example="python -m app.openapi_cli channels update 1 --access-mode url",
    ),
    EndpointDoc(
        key="channels.delete",
        method="DELETE",
        path="/api/v1/channels/{channel_id}",
        scope="config",
        summary="Delete a channel.",
        path_params=[_param("channel_id", "integer", True, "Channel ID.")],
        response='{"message": "Deleted successfully"}',
        errors=["401 missing or invalid API key", "403 scope missing", "404 channel not found"],
        example="python -m app.openapi_cli channels delete 1",
    ),
    EndpointDoc(
        key="channels.secret_key",
        method="POST",
        path="/api/v1/channels/{channel_id}/secret-key",
        scope="config",
        summary="Generate or rotate the channel secret key for embed token signing.",
        path_params=[_param("channel_id", "integer", True, "Channel ID.")],
        response="ChannelResponse with secret_key.",
        errors=["401 missing or invalid API key", "403 scope missing", "404 channel not found"],
        example="python -m app.openapi_cli channels secret-key 1",
    ),
)

ENDPOINT_BY_KEY = {endpoint.key: endpoint for endpoint in ENDPOINTS}


class OpenApiClient:
    """Small HTTP client for OpenAgent OpenAPI endpoints."""

    def __init__(self, host: str, api_key: str | None) -> None:
        self.host = host.rstrip("/")
        self.api_key = api_key

    def request(
        self,
        endpoint_key: str,
        path_params: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        *,
        stream: bool = False,
    ) -> bytes | None:
        endpoint = get_endpoint(endpoint_key)
        if endpoint.scope and not self.api_key:
            raise CliError(f"Missing API key. Set {ENV_API_KEY} or pass --api-key.")

        url = self._build_url(endpoint, path_params or {}, query or {})
        data = None
        headers = {"Accept": "text/event-stream" if stream else "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url, data=data, headers=headers, method=endpoint.method)
        try:
            with urlopen(request) as response:  # noqa: S310 - CLI calls user-provided API host.
                if stream:
                    for line in response:
                        sys.stdout.buffer.write(line)
                        sys.stdout.buffer.flush()
                    return None
                return response.read()
        except HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            raise CliError(f"HTTP {exc.code} for {endpoint_key}: {payload}") from exc
        except URLError as exc:
            raise CliError(f"Failed to connect to {url}: {exc.reason}") from exc

    def _build_url(self, endpoint: EndpointDoc, path_params: dict[str, Any], query: dict[str, Any]) -> str:
        path = endpoint.path
        for param in endpoint.path_params:
            if param.name not in path_params:
                raise CliError(f"Missing path parameter: {param.name}")
            path = path.replace("{" + param.name + "}", str(path_params[param.name]))

        clean_query = {
            key: value
            for key, value in query.items()
            if value is not None and value is not False
        }
        suffix = f"?{urlencode(clean_query, doseq=True)}" if clean_query else ""
        return f"{self.host}{path}{suffix}"


def get_endpoint(key: str) -> EndpointDoc:
    try:
        return ENDPOINT_BY_KEY[key]
    except KeyError as exc:
        choices = ", ".join(sorted(ENDPOINT_BY_KEY))
        raise CliError(f"Unknown endpoint '{key}'. Available endpoints: {choices}") from exc


def load_json_payload(json_text: str | None, json_file: str | None) -> dict[str, Any]:
    """Load an object JSON payload from text or file."""
    if json_text and json_file:
        raise CliError("--json and --json-file cannot be used together.")
    if not json_text and not json_file:
        return {}
    source = json_text
    if json_file:
        source = Path(json_file).read_text(encoding="utf-8")
    try:
        payload = json.loads(source or "{}")
    except json.JSONDecodeError as exc:
        raise CliError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise CliError("JSON payload must be an object.")
    return payload


def merge_payload(args: argparse.Namespace, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = load_json_payload(getattr(args, "json", None), getattr(args, "json_file", None))
    for key, value in (extra or {}).items():
        if value is not None:
            payload[key] = value
    return payload


def print_output(data: bytes | None, *, pretty: bool, raw: bool) -> None:
    if data is None:
        return
    text = data.decode("utf-8", errors="replace")
    if raw:
        print(text, end="" if text.endswith("\n") else "\n")
        return
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        print(text, end="" if text.endswith("\n") else "\n")
        return
    if pretty:
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(parsed, ensure_ascii=False, separators=(",", ":")))


def endpoint_as_dict(endpoint: EndpointDoc) -> dict[str, Any]:
    return asdict(endpoint)


def handle_docs(args: argparse.Namespace) -> int:
    if args.docs_action == "list":
        items = [
            {
                "key": item.key,
                "method": item.method,
                "path": item.path,
                "scope": item.scope,
                "summary": item.summary,
            }
            for item in ENDPOINTS
        ]
        print(json.dumps(items, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0

    endpoint = get_endpoint(args.endpoint)
    doc = endpoint_as_dict(endpoint)
    if args.json_doc:
        print(json.dumps(doc, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0

    print(f"{endpoint.key}")
    print(f"  {endpoint.method} {endpoint.path}")
    print(f"  scope: {endpoint.scope or 'none'}")
    print(f"  summary: {endpoint.summary}")
    if endpoint.path_params:
        print("  path params:")
        for item in endpoint.path_params:
            print(f"    - {item.name} ({item.type}, required={item.required}): {item.description}")
    if endpoint.query_params:
        print("  query params:")
        for item in endpoint.query_params:
            print(f"    - {item.name} ({item.type}, required={item.required}): {item.description}")
    if endpoint.body_fields:
        print("  body fields:")
        for item in endpoint.body_fields:
            print(f"    - {item.name} ({item.type}, required={item.required}): {item.description}")
    if endpoint.response:
        print(f"  response: {endpoint.response}")
    if endpoint.errors:
        print("  errors:")
        for item in endpoint.errors:
            print(f"    - {item}")
    if endpoint.example:
        print(f"  example: {endpoint.example}")
    return 0


def client_from_args(args: argparse.Namespace) -> OpenApiClient:
    host = args.host or os.getenv(ENV_HOST) or os.getenv(LEGACY_ENV_HOST) or DEFAULT_HOST
    api_key = args.api_key or os.getenv(ENV_API_KEY) or os.getenv(LEGACY_ENV_API_KEY)
    return OpenApiClient(host=host, api_key=api_key)


def run_request(
    args: argparse.Namespace,
    endpoint_key: str,
    path_params: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    *,
    stream: bool = False,
) -> int:
    data = client_from_args(args).request(
        endpoint_key,
        path_params=path_params,
        query=query,
        body=body,
        stream=stream,
    )
    print_output(data, pretty=args.pretty, raw=args.raw)
    return 0


def handle_knowledge(args: argparse.Namespace) -> int:
    if args.knowledge_action == "search":
        body = merge_payload(args, {"query": args.query})
        return run_request(args, "knowledge.search", {"kb_id": args.kb_id}, body=body)
    return run_request(args, "knowledge.markdown", {"kb_id": args.kb_id, "doc_id": args.doc_id})


def handle_conversations(args: argparse.Namespace) -> int:
    action = args.conversation_action
    if action == "create":
        body = merge_payload(
            args,
            {
                "agent_id": args.agent_id,
                "external_user_id": args.external_user_id,
                "source": args.source,
                "title": args.title,
                "display_name": args.display_name,
                "email": args.email,
                "phone": args.phone,
                "avatar_url": args.avatar_url,
            },
        )
        return run_request(args, "conversations.create", {"agent_id": args.agent_id}, body=body)
    if action == "list":
        query = {
            "page": args.page,
            "per_page": args.per_page,
            "start_time": args.start_time,
            "end_time": args.end_time,
            "status_filter": args.status_filter,
            "source": args.source,
            "conversation_id": args.conversation_external_id,
            "external_user_id": args.external_user_id,
            "search": args.search,
        }
        return run_request(args, "conversations.list", {"agent_id": args.agent_id}, query=query)
    path_params = {"agent_id": args.agent_id, "conversation_id": args.conversation_id}
    return run_request(args, f"conversations.{action}", path_params)


def handle_chat(args: argparse.Namespace) -> int:
    body = merge_payload(
        args,
        {
            "message": args.message,
            "conversation_id": args.conversation_id,
            "conversation_external_id": args.conversation_external_id,
            "request_id": args.request_id,
            "resume": True if args.resume else None,
        },
    )
    return run_request(args, "chat.stream", {"agent_id": args.agent_id}, body=body, stream=True)


def handle_steps(args: argparse.Namespace) -> int:
    return run_request(
        args,
        "steps.list",
        {"agent_id": args.agent_id, "conversation_id": args.conversation_id},
    )


def handle_agents(args: argparse.Namespace) -> int:
    action = args.agent_action
    if action == "list":
        return run_request(
            args,
            "agents.list",
            query={"status_filter": args.status_filter, "page": args.page, "per_page": args.per_page},
        )
    if action == "create":
        body = merge_payload(args, {"name": args.name, "description": args.description})
        return run_request(args, "agents.create", body=body)
    if action == "get":
        return run_request(args, "agents.get", {"agent_id": args.agent_id})
    if action == "update":
        body = merge_payload(args, {"name": args.name, "description": args.description})
        return run_request(args, "agents.update", {"agent_id": args.agent_id}, body=body)
    if action == "status":
        return run_request(args, "agents.status", {"agent_id": args.agent_id}, body={"status": args.status})
    body = merge_payload(args)
    return run_request(args, "agents.engine_config", {"agent_id": args.agent_id}, body=body)


def handle_tools(args: argparse.Namespace) -> int:
    action = args.tool_action
    if action == "list":
        return run_request(args, "tools.list", {"agent_id": args.agent_id})
    if action == "create":
        body = merge_payload(
            args,
            {"name": args.name, "description": args.description, "tool_type": args.tool_type},
        )
        return run_request(args, "tools.create", {"agent_id": args.agent_id}, body=body)
    if action == "get":
        return run_request(args, "tools.get", {"agent_id": args.agent_id, "tool_id": args.tool_id})
    if action == "update":
        body = merge_payload(args, {"name": args.name, "description": args.description})
        return run_request(args, "tools.update", {"agent_id": args.agent_id, "tool_id": args.tool_id}, body=body)
    if action == "toggle":
        return run_request(
            args,
            "tools.toggle",
            {"agent_id": args.agent_id, "tool_id": args.tool_id},
            body={"is_enabled": args.is_enabled},
        )
    if action == "delete":
        return run_request(args, "tools.delete", {"agent_id": args.agent_id, "tool_id": args.tool_id})
    body = merge_payload(args)
    return run_request(
        args,
        "tools.execute",
        {"agent_id": args.agent_id, "tool_id": args.tool_id},
        query={"conversation_id": args.conversation_id},
        body=body,
    )


def handle_channels(args: argparse.Namespace) -> int:
    action = args.channel_action
    if action == "list":
        return run_request(args, "channels.list", query={"page": args.page, "per_page": args.per_page})
    if action == "create":
        body = merge_payload(
            args,
            {
                "name": args.name,
                "description": args.description,
                "agent_id": args.agent_id,
                "access_mode": args.access_mode,
            },
        )
        return run_request(args, "channels.create", body=body)
    if action == "get":
        return run_request(args, "channels.get", {"channel_id": args.channel_id})
    if action == "update":
        body = merge_payload(
            args,
            {
                "name": args.name,
                "description": args.description,
                "agent_id": args.agent_id,
                "access_mode": args.access_mode,
            },
        )
        return run_request(args, "channels.update", {"channel_id": args.channel_id}, body=body)
    if action == "delete":
        return run_request(args, "channels.delete", {"channel_id": args.channel_id})
    return run_request(args, "channels.secret_key", {"channel_id": args.channel_id})


def add_json_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", help="JSON object payload.")
    parser.add_argument("--json-file", help="Read JSON object payload from file.")


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", help=f"API host. Defaults to ${ENV_HOST} or {DEFAULT_HOST}.")
    parser.add_argument("--api-key", help=f"API key. Defaults to ${ENV_API_KEY}.")
    parser.add_argument("--pretty", action=argparse.BooleanOptionalAction, default=True, help="Pretty-print JSON output.")
    parser.add_argument("--raw", action="store_true", help="Print raw response text.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenAgent OpenAPI CLI")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    docs = subparsers.add_parser("docs", help="Query built-in API documentation for humans and AI agents.")
    docs_sub = docs.add_subparsers(dest="docs_action", required=True)
    docs_sub.add_parser("list", help="List endpoint keys.")
    docs_show = docs_sub.add_parser("show", help="Show endpoint documentation.")
    docs_show.add_argument("endpoint")
    docs_show.add_argument("--json", dest="json_doc", action="store_true", help="Output machine-readable JSON.")
    docs.set_defaults(handler=handle_docs)

    knowledge = subparsers.add_parser("knowledge", help="Knowledge base endpoints.")
    knowledge_sub = knowledge.add_subparsers(dest="knowledge_action", required=True)
    knowledge_search = knowledge_sub.add_parser("search")
    knowledge_search.add_argument("kb_id", type=int)
    knowledge_search.add_argument("--query", required=True)
    add_json_args(knowledge_search)
    knowledge_markdown = knowledge_sub.add_parser("markdown")
    knowledge_markdown.add_argument("kb_id", type=int)
    knowledge_markdown.add_argument("doc_id", type=int)
    knowledge.set_defaults(handler=handle_knowledge)

    conversations = subparsers.add_parser("conversations", help="Conversation endpoints.")
    conv_sub = conversations.add_subparsers(dest="conversation_action", required=True)
    conv_create = conv_sub.add_parser("create")
    conv_create.add_argument("agent_id", type=int)
    conv_create.add_argument("--source", default="api", choices=["chat", "api", "embed"])
    conv_create.add_argument("--title")
    conv_create.add_argument("--external-user-id")
    conv_create.add_argument("--display-name")
    conv_create.add_argument("--email")
    conv_create.add_argument("--phone")
    conv_create.add_argument("--avatar-url")
    add_json_args(conv_create)
    conv_list = conv_sub.add_parser("list")
    conv_list.add_argument("agent_id", type=int)
    conv_list.add_argument("--page", type=int)
    conv_list.add_argument("--per-page", type=int)
    conv_list.add_argument("--start-time")
    conv_list.add_argument("--end-time")
    conv_list.add_argument("--status-filter")
    conv_list.add_argument("--source", choices=["chat", "api", "embed"])
    conv_list.add_argument("--conversation-external-id")
    conv_list.add_argument("--external-user-id")
    conv_list.add_argument("--search")
    for name in ("get", "end"):
        conv_item = conv_sub.add_parser(name)
        conv_item.add_argument("agent_id", type=int)
        conv_item.add_argument("conversation_id", type=int)
    conversations.set_defaults(handler=handle_conversations)

    chat = subparsers.add_parser("chat", help="Stream chat with an agent.")
    chat.add_argument("agent_id", type=int)
    chat.add_argument("--message", required=True)
    chat.add_argument("--conversation-id", type=int)
    chat.add_argument("--conversation-external-id")
    chat.add_argument("--request-id")
    chat.add_argument("--resume", action="store_true")
    add_json_args(chat)
    chat.set_defaults(handler=handle_chat)

    steps = subparsers.add_parser("steps", help="List conversation execution steps.")
    steps.add_argument("agent_id", type=int)
    steps.add_argument("conversation_id", type=int)
    steps.set_defaults(handler=handle_steps)

    agents = subparsers.add_parser("agents", help="Agent endpoints.")
    agent_sub = agents.add_subparsers(dest="agent_action", required=True)
    agent_list = agent_sub.add_parser("list")
    agent_list.add_argument("--status-filter", default="active", choices=["active", "inactive"])
    agent_list.add_argument("--page", type=int)
    agent_list.add_argument("--per-page", type=int)
    agent_create = agent_sub.add_parser("create")
    agent_create.add_argument("--name", required=True)
    agent_create.add_argument("--description")
    add_json_args(agent_create)
    agent_get = agent_sub.add_parser("get")
    agent_get.add_argument("agent_id", type=int)
    agent_update = agent_sub.add_parser("update")
    agent_update.add_argument("agent_id", type=int)
    agent_update.add_argument("--name")
    agent_update.add_argument("--description")
    add_json_args(agent_update)
    agent_status = agent_sub.add_parser("status")
    agent_status.add_argument("agent_id", type=int)
    agent_status.add_argument("status", choices=["active", "inactive"])
    agent_engine = agent_sub.add_parser("engine-config")
    agent_engine.add_argument("agent_id", type=int)
    add_json_args(agent_engine)
    agents.set_defaults(handler=handle_agents)

    tools = subparsers.add_parser("tools", help="Agent tool endpoints.")
    tool_sub = tools.add_subparsers(dest="tool_action", required=True)
    tool_list = tool_sub.add_parser("list")
    tool_list.add_argument("agent_id", type=int)
    tool_create = tool_sub.add_parser("create")
    tool_create.add_argument("agent_id", type=int)
    tool_create.add_argument("--name", required=True)
    tool_create.add_argument("--description")
    tool_create.add_argument("--tool-type", required=True, choices=["search", "doc_query", "notebook", "tool_response_fetch", "python_code"])
    add_json_args(tool_create)
    for name in ("get", "delete"):
        tool_item = tool_sub.add_parser(name)
        tool_item.add_argument("agent_id", type=int)
        tool_item.add_argument("tool_id", type=int)
    tool_update = tool_sub.add_parser("update")
    tool_update.add_argument("agent_id", type=int)
    tool_update.add_argument("tool_id", type=int)
    tool_update.add_argument("--name")
    tool_update.add_argument("--description")
    add_json_args(tool_update)
    tool_toggle = tool_sub.add_parser("toggle")
    tool_toggle.add_argument("agent_id", type=int)
    tool_toggle.add_argument("tool_id", type=int)
    tool_toggle.add_argument("is_enabled", type=parse_bool)
    tool_execute = tool_sub.add_parser("execute")
    tool_execute.add_argument("agent_id", type=int)
    tool_execute.add_argument("tool_id", type=int)
    tool_execute.add_argument("--conversation-id", type=int)
    add_json_args(tool_execute)
    tools.set_defaults(handler=handle_tools)

    channels = subparsers.add_parser("channels", help="Web SDK channel endpoints.")
    channel_sub = channels.add_subparsers(dest="channel_action", required=True)
    channel_list = channel_sub.add_parser("list")
    channel_list.add_argument("--page", type=int)
    channel_list.add_argument("--per-page", type=int)
    channel_create = channel_sub.add_parser("create")
    channel_create.add_argument("--name", required=True)
    channel_create.add_argument("--description")
    channel_create.add_argument("--agent-id", type=int)
    channel_create.add_argument("--access-mode", choices=["url", "embed"])
    add_json_args(channel_create)
    for name in ("get", "delete", "secret-key"):
        channel_item = channel_sub.add_parser(name)
        channel_item.add_argument("channel_id", type=int)
    channel_update = channel_sub.add_parser("update")
    channel_update.add_argument("channel_id", type=int)
    channel_update.add_argument("--name")
    channel_update.add_argument("--description")
    channel_update.add_argument("--agent-id", type=int)
    channel_update.add_argument("--access-mode", choices=["url", "embed"])
    add_json_args(channel_update)
    channels.set_defaults(handler=handle_channels)

    return parser


def parse_bool(value: str) -> bool:
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("Expected boolean: true/false")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
