"""
Observability — vendor-neutral telemetry layer.

Public API:
    init_observability() / shutdown_observability()
        Lifecycle hooks (call once at app startup / shutdown).

    get_provider()
        Read the active provider, e.g. to attach its log handler to the
        stdlib root logger inside `setup_logging()`.

    conversation_span(name, attributes)
        Span context manager for the conversation tracer (chat round, tool
        call, assistant message …).

    llm_span(name, attributes)
        Span context manager on the dedicated `genai.llm` tracer. Use this
        only when you need fully manual instrumentation; the default path is
        to wrap the LLM client via `wrap_llm_client()` in the factory.

    current_span()
        Returns the currently active span (or a no-op span if none). Use
        this to enrich the surrounding span when an attribute only becomes
        known after the span has already been opened — e.g. setting
        `conversation.id` after `INSERT` returns the generated id.

    wrap_llm_client(client)
        Decorator that adds OTel GenAI tracing to any `BaseLLMClient`.
"""
from app.libs.observability.factory import (
    get_provider,
    init_observability,
    shutdown_observability,
)
from app.libs.observability.helpers import (
    conversation_span,
    current_span,
    llm_span,
)
from app.libs.observability.llm_tracer import wrap_llm_client

__all__ = [
    "init_observability",
    "shutdown_observability",
    "get_provider",
    "conversation_span",
    "llm_span",
    "current_span",
    "wrap_llm_client",
]
