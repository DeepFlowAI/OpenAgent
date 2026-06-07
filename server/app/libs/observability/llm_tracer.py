"""
LLM client tracing decorator.

Wraps any `BaseLLMClient` so every call emits an OpenTelemetry GenAI-flavored
span on the dedicated "genai.llm" tracer. The wrapped client implements the
exact same interface — provider implementations stay untouched.

Why a Decorator (not subclassing each provider):
    - Adding new providers (Anthropic, Bedrock, …) automatically inherits
      tracing without copying boilerplate.
    - Tests can swap to the underlying client with a single attribute access.
    - Decoupling matches the "abstraction at the boundary" principle the rest
      of this codebase uses (see `BaseLLMClient` itself).

Span attributes follow the OpenTelemetry GenAI semantic convention:
    https://opentelemetry.io/docs/specs/semconv/gen-ai/
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from app.configs.settings import settings
from app.libs.llm.base import (
    BaseLLMClient,
    LLMAPIError,
    LLMResponse,
    LLMStreamDelta,
    LLMStreamResult,
)
from app.libs.observability.helpers import llm_span

logger = logging.getLogger(__name__)


def _system_from_model(model: str) -> str:
    """Best-effort guess of the gen_ai.system value from a model identifier."""
    m = model.lower()
    if "qwen" in m or "dashscope" in m:
        return "aliyun-bailian"
    if "openrouter/" in m or m.startswith("openrouter/"):
        return "openrouter"
    if "openai" in m or m.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    if "anthropic" in m or "claude" in m:
        return "anthropic"
    if "deepseek" in m:
        return "deepseek"
    if "moonshot" in m or "kimi" in m:
        return "moonshot"
    if "z-ai" in m or "glm" in m:
        return "zhipu"
    if "x-ai" in m or "grok" in m:
        return "xai"
    if "minimax" in m:
        return "minimax"
    return "unknown"


def _system_from_channel(channel: str | None, fallback_model: str) -> str:
    """Prefer the actual routed channel over a best-effort model-name guess."""
    if not channel:
        return _system_from_model(fallback_model)
    if channel in {"aliyun-bailian", "siliconflow", "openrouter"}:
        return channel
    if channel == "moonshot-official":
        return "moonshot"
    if channel == "zhipu-official":
        return "zhipu"
    if channel == "minimax-official":
        return "minimax"
    return _system_from_model(fallback_model)


def _base_attributes(
    *,
    model: str,
    operation: str,
    messages: list[dict],
    tools: list[dict] | None,
    temperature: float,
    top_p: float,
    max_tokens: int,
    thinking_enabled: bool,
) -> dict:
    """Attributes set up-front (before the call returns)."""
    attrs: dict = {
        "gen_ai.system": _system_from_model(model),
        "gen_ai.operation.name": operation,
        "gen_ai.request.model": model,
        "gen_ai.request.temperature": temperature,
        "gen_ai.request.top_p": top_p,
        "gen_ai.request.max_tokens": max_tokens,
        "gen_ai.request.thinking_enabled": thinking_enabled,
        "gen_ai.request.messages_count": len(messages),
    }
    if tools:
        attrs["gen_ai.request.tools_count"] = len(tools)
    if settings.OTEL_CAPTURE_LLM_CONTENT:
        # Truncated to keep span payload small; full bodies live in DB anyway.
        try:
            import json

            attrs["gen_ai.prompt"] = json.dumps(
                messages, ensure_ascii=False, default=str
            )[:8000]
        except Exception:  # noqa: BLE001
            pass
    return attrs


def _record_response(span, *, response: LLMResponse) -> None:
    span.set_attribute(
        "gen_ai.system",
        _system_from_channel(response.provider_channel, response.model or ""),
    )
    span.set_attribute("gen_ai.response.model", response.model or "")
    if response.provider_channel:
        span.set_attribute("gen_ai.provider.channel", response.provider_channel)
    if response.provider_name:
        span.set_attribute("gen_ai.provider.name", response.provider_name)
    # NOTE: GenAI semconv defines `finish_reasons` as an array, but the GreptimeDB
    # column for this attribute was created as String at first ingestion. Sending a
    # list now causes the entire span to be silently rejected. We emit the value as
    # a comma-joined string for backend compatibility — there's effectively only
    # ever one reason per response in our flow anyway.
    span.set_attribute("gen_ai.response.finish_reasons", response.finish_reason or "")
    span.set_attribute("gen_ai.usage.input_tokens", int(response.input_tokens or 0))
    span.set_attribute("gen_ai.usage.cached_tokens", int(response.cached_tokens or 0))
    span.set_attribute("gen_ai.usage.output_tokens", int(response.output_tokens or 0))
    span.set_attribute("gen_ai.usage.total_tokens", int(response.total_tokens or 0))
    if response.request_id:
        span.set_attribute("gen_ai.response.id", response.request_id)
    if response.tool_calls:
        span.set_attribute("gen_ai.response.tool_calls_count", len(response.tool_calls))
    if settings.OTEL_CAPTURE_LLM_CONTENT and response.content:
        span.set_attribute("gen_ai.completion", (response.content or "")[:8000])


def _record_stream_result(span, *, result: LLMStreamResult) -> None:
    span.set_attribute(
        "gen_ai.system",
        _system_from_channel(result.provider_channel, result.model or ""),
    )
    span.set_attribute("gen_ai.response.model", result.model or "")
    if result.provider_channel:
        span.set_attribute("gen_ai.provider.channel", result.provider_channel)
    if result.provider_name:
        span.set_attribute("gen_ai.provider.name", result.provider_name)
    # See note in `_record_response`: keep this as a String so GreptimeDB doesn't
    # silently drop the span. Single-string is enough for current consumers.
    span.set_attribute("gen_ai.response.finish_reasons", result.finish_reason or "")
    span.set_attribute("gen_ai.usage.input_tokens", int(result.input_tokens or 0))
    span.set_attribute("gen_ai.usage.cached_tokens", int(result.cached_tokens or 0))
    span.set_attribute("gen_ai.usage.output_tokens", int(result.output_tokens or 0))
    span.set_attribute("gen_ai.usage.total_tokens", int(result.total_tokens or 0))
    if result.request_id:
        span.set_attribute("gen_ai.response.id", result.request_id)
    if result.tool_calls:
        span.set_attribute("gen_ai.response.tool_calls_count", len(result.tool_calls))
    if settings.OTEL_CAPTURE_LLM_CONTENT and result.content:
        span.set_attribute("gen_ai.completion", (result.content or "")[:8000])
    # Stream-level reliability (stream-level retry spec): mark incomplete attempts so the
    # billing/audit dashboards can compute "retry rate = incomplete spans / total".
    if result.incomplete_reason:
        span.set_attribute("gen_ai.stream.incomplete", True)
        span.set_attribute("gen_ai.stream.incomplete_reason", result.incomplete_reason)


class TracedLLMClient(BaseLLMClient):
    """Transparent tracing wrapper around a `BaseLLMClient`."""

    def __init__(self, inner: BaseLLMClient) -> None:
        self._inner = inner

    # ── chat (non-streaming) ──────────────────────────────────────────
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
        attrs = _base_attributes(
            model=model,
            operation="chat",
            messages=messages,
            tools=tools,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            thinking_enabled=thinking_enabled,
        )
        with llm_span(f"chat {model}", attrs) as span:
            try:
                response = await self._inner.chat(
                    messages,
                    model=model,
                    tools=tools,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    thinking_enabled=thinking_enabled,
                )
            except LLMAPIError as exc:
                span.set_attribute("gen_ai.error.type", exc.error_type or "api_error")
                span.set_attribute("gen_ai.error.status_code", exc.status_code)
                span.set_status_error(exc.error_message)
                raise
            except Exception as exc:  # noqa: BLE001
                span.set_attribute("gen_ai.error.type", type(exc).__name__)
                span.set_status_error(str(exc))
                raise
            else:
                _record_response(span, response=response)
                span.set_status_ok()
                return response

    # ── stream_chat ──────────────────────────────────────────────────
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
        # Streaming spans are tricky: the call returns immediately with an
        # iterator that's consumed later. We span around the *whole* lifetime
        # of the iterator using a wrapper async-generator, which is cleaner
        # than juggling raw start/end span APIs and survives early exits.
        attrs = _base_attributes(
            model=model,
            operation="chat",
            messages=messages,
            tools=tools,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            thinking_enabled=thinking_enabled,
        )
        attrs["gen_ai.request.streaming"] = True

        inner_iter, result = await self._inner.stream_chat(
            messages,
            model=model,
            tools=tools,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            thinking_enabled=thinking_enabled,
        )

        async def _traced_stream() -> AsyncIterator[LLMStreamDelta]:
            with llm_span(f"chat {model}", attrs) as span:
                try:
                    async for delta in inner_iter:
                        yield delta
                except LLMAPIError as exc:
                    span.set_attribute(
                        "gen_ai.error.type", exc.error_type or "api_error"
                    )
                    span.set_attribute("gen_ai.error.status_code", exc.status_code)
                    span.set_status_error(exc.error_message)
                    raise
                except Exception as exc:  # noqa: BLE001
                    span.set_attribute("gen_ai.error.type", type(exc).__name__)
                    span.set_status_error(str(exc))
                    raise
                else:
                    _record_stream_result(span, result=result)
                    # Mark "stream completed but flagged as incomplete" attempts as
                    # ERROR so dashboards can compute retry rates from span status
                    # alone (no need to also filter on `gen_ai.stream.incomplete`).
                    if result.incomplete_reason:
                        span.set_status_error(
                            f"stream incomplete: {result.incomplete_reason}"
                        )
                    else:
                        span.set_status_ok()

        return _traced_stream(), result


def wrap_llm_client(client: BaseLLMClient) -> BaseLLMClient:
    """Wrap an LLM client with tracing, unless the client is already wrapped."""
    if isinstance(client, TracedLLMClient):
        return client
    return TracedLLMClient(client)
