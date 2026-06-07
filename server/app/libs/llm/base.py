"""
LLM provider abstraction — abstract interface for large language model calls.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


class LLMAPIError(Exception):
    """Raised when the LLM API returns a non-200 response."""

    def __init__(self, status_code: int, message: str, param: str | None = None, error_type: str | None = None):
        self.status_code = status_code
        self.error_message = message
        self.param = param
        self.error_type = error_type
        super().__init__(message)


@dataclass
class LLMMessage:
    role: str
    content: str | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict


@dataclass
class LLMStreamDelta:
    """A single chunk from a streaming LLM response."""
    content: str | None = None
    thinking_content: str | None = None
    tool_calls: list[dict] | None = None
    finish_reason: str | None = None


_CACHE_TOKEN_KEYS = (
    "cached_tokens",
    "cache_read_input_tokens",
    "prompt_cache_hit_tokens",
)


def _usage_value(container: Any, key: str) -> Any:
    if container is None:
        return None
    if isinstance(container, dict):
        return container.get(key)
    return getattr(container, key, None)


def _token_count(value: Any) -> int:
    if value is None:
        return 0
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def extract_cached_tokens_from_usage(usage: Any) -> int:
    """Extract prompt-cache hit tokens from OpenAI-compatible usage payloads."""
    prompt_details = _usage_value(usage, "prompt_tokens_details")
    for key in _CACHE_TOKEN_KEYS:
        count = _token_count(_usage_value(prompt_details, key))
        if count:
            return count

    for key in _CACHE_TOKEN_KEYS:
        count = _token_count(_usage_value(usage, key))
        if count:
            return count
    return 0


@dataclass
class LLMResponse:
    """Complete (non-streaming) LLM response."""
    content: str | None = None
    thinking_content: str | None = None
    tool_calls: list[dict] | None = None
    finish_reason: str | None = None
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    request_id: str | None = None
    model: str | None = None
    provider_channel: str | None = None
    provider_name: str | None = None


@dataclass
class LLMStreamResult:
    """Accumulated result from a streaming call, populated as chunks arrive.

    Stream-level reliability (stream-level retry spec):
        ``incomplete_reason`` is set by the provider when the stream did NOT
        finish cleanly (timeout, mid-stream error, missing finish_reason).
        Engine layer reads it AFTER the iterator is exhausted to decide
        whether to retry. ``None`` means a healthy successful stream.

        ``retry_count`` is bookkeeping the engine writes back AFTER its retry
        loop succeeds — it surfaces in OTel attributes and the persisted
        ``llm_call`` step metadata for post-mortem.
    """
    content: str = ""
    thinking_content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str | None = None
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    request_id: str | None = None
    model: str | None = None
    provider_channel: str | None = None
    provider_name: str | None = None
    incomplete_reason: str | None = None
    retry_count: int = 0


class BaseLLMClient(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        *,
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.01,
        top_p: float = 0.85,
        max_tokens: int = 4096,
        thinking_enabled: bool = False,
    ) -> LLMResponse:
        """Non-streaming chat completion."""
        ...

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict],
        *,
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.01,
        top_p: float = 0.85,
        max_tokens: int = 4096,
        thinking_enabled: bool = False,
    ) -> tuple[AsyncIterator[LLMStreamDelta], LLMStreamResult]:
        """Streaming chat completion.
        Returns (async iterator of deltas, result accumulator).
        The accumulator is populated as chunks arrive.
        """
        ...
