"""
Helpers exposed to business code.

Business modules (`routers`, `services`, …) import only from here. They never
touch OpenTelemetry types directly, so vendor migrations stay isolated to the
`observability/` package.

Resilience contract
-------------------
Every helper here MUST guarantee that observability failures (SDK errors,
network timeouts, misconfiguration) cannot leak into business code. If the
backend is misbehaving, callers transparently get a no-op span and the main
flow keeps running. Exceptions originating from the user's `with`-block body,
on the other hand, are always re-raised — observability never swallows real
business errors.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from app.libs.observability.factory import get_provider
from app.libs.observability.noop import _NOOP_SPAN
from app.libs.observability.provider import ObservabilitySpan

logger = logging.getLogger(__name__)


@contextmanager
def _safe_span(
    starter_name: str, name: str, attributes: dict | None
) -> Iterator[ObservabilitySpan]:
    """Provider-agnostic span wrapper that never raises observability errors.

    We enter / exit the underlying context manager manually so we can
    distinguish observability failures (swallowed) from business-code
    failures (always propagated). The provider is resolved through the
    factory so noop deployments stay zero-cost.
    """
    provider = get_provider()
    starter = getattr(provider, starter_name)

    cm = None
    span: ObservabilitySpan = _NOOP_SPAN
    try:
        cm = starter(name, attributes)
        span = cm.__enter__()
    except Exception:  # noqa: BLE001 — observability must not raise
        logger.debug("observability: failed to open %s", name, exc_info=True)
        cm = None
        span = _NOOP_SPAN

    try:
        yield span
    except BaseException as exc:
        # Business-code raised — let the span observe the error, then re-raise.
        if cm is not None:
            try:
                cm.__exit__(type(exc), exc, exc.__traceback__)
            except Exception:  # noqa: BLE001
                pass
        raise
    else:
        if cm is not None:
            try:
                cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                logger.debug(
                    "observability: failed to close %s", name, exc_info=True
                )


@contextmanager
def conversation_span(
    name: str, attributes: dict | None = None
) -> Iterator[ObservabilitySpan]:
    """Open a conversation-tracer span.

    Use at the entry of an agent chat round, around tool calls, etc. Attach
    `conversation.id`, `agent.id`, `tenant.id` so downstream queries can group
    by any of them. Failures of the underlying backend are silently downgraded
    to a no-op span so the main flow is never affected.
    """
    with _safe_span("start_conversation_span", name, attributes) as span:
        yield span


@contextmanager
def llm_span(
    name: str, attributes: dict | None = None
) -> Iterator[ObservabilitySpan]:
    """Open an LLM-tracer span (separate stream from conversation logs).

    Like `conversation_span`, observability backend errors never propagate
    to business code — callers always get a usable span.
    """
    with _safe_span("start_llm_span", name, attributes) as span:
        yield span


def current_span() -> ObservabilitySpan:
    """Return the currently active span (or a no-op span if none).

    Use this when an attribute only becomes known *inside* the span body —
    e.g. setting ``conversation.id`` after the conversation row has been
    written to the DB. Failures never propagate; the worst case is a no-op
    span where ``set_attribute`` is silently dropped.
    """
    try:
        return get_provider().get_current_span()
    except Exception:  # noqa: BLE001 — observability must not raise
        logger.debug("observability: get_current_span failed", exc_info=True)
        return _NOOP_SPAN
