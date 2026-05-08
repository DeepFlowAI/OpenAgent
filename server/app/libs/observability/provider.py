"""
Observability Provider — vendor-neutral abstraction for log / trace shipping.

Why an interface:
    The remote system speaks OTLP (e.g. a GreptimeDB-compatible pipeline). Tomorrow it might
    be SigNoz, Honeycomb, Aliyun SLS, or a self-hosted Tempo+Loki stack. By
    funnelling every emit through a single interface, switching vendors is a
    one-line factory change — business code never imports OpenTelemetry directly.

Three signal types we explicitly model (per requirements):
    1. Console logs       — captured via stdlib `logging` handler attachment.
                            Provider returns the handler; setup_logging() wires it.
    2. Conversation logs  — emitted as spans via `start_conversation_span()`.
    3. LLM calls          — emitted as spans via `start_llm_span()`, kept on a
                            separate tracer name ("genai.llm") so they can be
                            filtered / billed independently downstream.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator, Protocol


class ObservabilitySpan(Protocol):
    """Minimal span surface — same shape regardless of underlying SDK."""

    def set_attribute(self, key: str, value: object) -> None: ...
    def set_status_ok(self) -> None: ...
    def set_status_error(self, message: str) -> None: ...
    def add_event(self, name: str, attributes: dict | None = None) -> None: ...


class ObservabilityProvider(Protocol):
    """Facade over the underlying telemetry SDK."""

    name: str

    def init(self) -> None:
        """Initialize exporters / processors. Idempotent."""

    def shutdown(self) -> None:
        """Flush buffers and tear down. Called on app shutdown."""

    def get_log_handler(self) -> logging.Handler | None:
        """Return a stdlib `logging.Handler` to attach to the root logger,
        or None if this backend does not capture console logs.
        """

    @contextmanager
    def start_conversation_span(
        self, name: str, attributes: dict | None = None
    ) -> Iterator[ObservabilitySpan]:
        """Open a span on the *conversation* tracer.

        Use for: chat round entry, user message, tool call, assistant message.
        """
        yield  # type: ignore[misc]

    @contextmanager
    def start_llm_span(
        self, name: str, attributes: dict | None = None
    ) -> Iterator[ObservabilitySpan]:
        """Open a span on the dedicated *LLM* tracer.

        Use for: every call to BaseLLMClient.chat / stream_chat. Spans here
        follow the OpenTelemetry GenAI semantic convention (`gen_ai.*`) so any
        OTLP-compatible backend can render LLM dashboards out of the box.
        """
        yield  # type: ignore[misc]

    def get_current_span(self) -> ObservabilitySpan:
        """Return the currently active span (or a no-op span if none).

        Used by deeply nested code that needs to enrich the surrounding
        span — e.g. setting ``conversation.id`` only after the conversation
        row has been written to the DB. Callers never have to know which
        span is active; they just call ``current_span().set_attribute(...)``.
        """
        ...
