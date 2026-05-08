"""
Noop observability provider — used when no backend is configured.

Keeps every call a cheap no-op so local dev / tests carry zero overhead.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from app.libs.observability.provider import ObservabilitySpan


class _NoopSpan:
    def set_attribute(self, key: str, value: object) -> None:  # noqa: D401
        return

    def set_status_ok(self) -> None:
        return

    def set_status_error(self, message: str) -> None:
        return

    def add_event(self, name: str, attributes: dict | None = None) -> None:
        return


_NOOP_SPAN = _NoopSpan()


class NoopProvider:
    name = "noop"

    def init(self) -> None:
        return

    def shutdown(self) -> None:
        return

    def get_log_handler(self) -> logging.Handler | None:
        return None

    @contextmanager
    def start_conversation_span(
        self, name: str, attributes: dict | None = None
    ) -> Iterator[ObservabilitySpan]:
        yield _NOOP_SPAN

    @contextmanager
    def start_llm_span(
        self, name: str, attributes: dict | None = None
    ) -> Iterator[ObservabilitySpan]:
        yield _NOOP_SPAN

    def get_current_span(self) -> ObservabilitySpan:
        return _NOOP_SPAN
