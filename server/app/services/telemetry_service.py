"""
Telemetry service — flatten frontend events into stdlib LogRecords.

This service is intentionally a one-trick pony: it takes a validated
:class:`TelemetryBatchRequest`, walks each event, and re-emits it through a
dedicated logger (``app.frontend.event``) so the existing OTel
``LoggingHandler`` can ship it to ``otel_logs``. We do **not** use any
ORM/Repository because:

1. There is no PG table — events live in GreptimeDB via the OTLP pipeline.
2. The logger pipeline already has batching, retry and shutdown-flush.
3. Going through stdlib logging is the cleanest way to get the
   :class:`TraceFilter` and existing observability conventions for free.

The contract with the log-analyzer Skill (see
``.claude/skills/log-analyzer/SKILL.md``) is therefore:

- ``scope_name = 'app.frontend.event'`` identifies our records.
- ``log_attributes.event`` is the event name.
- ``log_attributes.props_*`` and ``log_attributes.metrics_*`` are the
  user-defined fields, flattened out of the original ``props`` / ``metrics``
  dicts so they're directly grep-able as JSON keys.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.configs.settings import settings
from app.core.trace import (
    _conversation_external_id_var,
    _request_id_var,
    _trace_id_var,
    set_conversation_external_id,
    set_request_id,
    set_trace_id,
)
from app.schemas.telemetry import (
    MAX_EVENTS_PER_BATCH,
    MAX_KEY_CHARS,
    MAX_KEYS_PER_DICT,
    MAX_VALUE_CHARS,
    TelemetryBatchRequest,
    TelemetryBatchResponse,
    TelemetryEvent,
    TelemetryLevel,
)


# Keys in props/metrics must be ASCII snake_case so they query cleanly via
# ``json_get_string(log_attributes, 'props_<key>')`` in your log backend without
# escaping. Anything that fails this check is dropped at the flatten step
# (with the rest of the event still landing in otel_logs).
_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


# Dedicated logger name. Kept distinct from ``__name__`` so the scope shows
# up in your log backend as ``app.frontend.event`` (matching what the
# log-analyzer Skill teaches users to filter by) instead of the noisier
# ``app.services.telemetry_service`` that would otherwise be inferred.
_FRONTEND_LOGGER_NAME = "app.frontend.event"
logger = logging.getLogger(_FRONTEND_LOGGER_NAME)


# Fields that are stable across every event, written via stdlib's reserved
# ``extra`` mechanism. These shadow nothing in :class:`logging.LogRecord`
# (verified — no collisions with stdlib record attribute names).
_RESERVED_LOG_RECORD_ATTRS = frozenset(
    {
        # Stdlib LogRecord builtins. Touching these via ``extra={}`` raises
        # KeyError, so the flatten step skips/renames anything that lands
        # here. The full list comes from cpython's ``logging.LogRecord``.
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
    }
)


def _coerce_str(value: Any) -> str:
    """Stringify a primitive, capping length so a runaway value can't bloat
    a log row. Booleans are normalised to lowercase to match the wire format
    seen in JS (``true`` / ``false``)."""
    if isinstance(value, bool):
        out = "true" if value else "false"
    else:
        out = str(value)
    if len(out) > MAX_VALUE_CHARS:
        out = out[:MAX_VALUE_CHARS] + f"...({len(out) - MAX_VALUE_CHARS} more)"
    return out


def _level_to_log(level: TelemetryLevel) -> int:
    """Map the wire-format level to a stdlib level integer.

    Falls through to INFO for any unknown value. Pydantic should already
    have rejected those, but defence-in-depth keeps a typo from raising
    at log-time and breaking ingest for a whole batch.
    """
    if level == "warn":
        return logging.WARNING
    if level == "error":
        return logging.ERROR
    return logging.INFO


def _flatten_dict(
    target: dict[str, str], prefix: str, source: dict[str, Any] | None
) -> None:
    """Flatten a ``props``/``metrics`` dict into ``target`` with a key
    prefix. Mutates ``target`` in place.

    Drops keys that:
      * collide with stdlib LogRecord attributes (``message``, ``msg``, …),
      * exceed the per-batch attribute budget (``MAX_KEYS_PER_DICT``),
      * are longer than ``MAX_KEY_CHARS`` — usually a SDK bug or attempt
        to smuggle a giant key into log_attributes; defence-in-depth on
        top of the schema layer's overall body cap,
      * fail the ASCII snake_case pattern — same reason: keep a clean
        contract for log-analyzer queries instead of accepting arbitrary
        unicode that breaks ``json_get_string`` filters,
      * have empty/None keys.

    All values are stringified so columnar storage gets a uniform type;
    the log-analyzer Skill ``CAST(... AS BIGINT)`` recipes handle the
    numeric reads at query time.

    Returning silently (rather than raising) on a bad key is intentional:
    one bad key in a batch should never poison the other 99 events. If
    a bug starts spraying bad keys in production we'll see ``accepted``
    rise but the ``log_attributes.props_*`` column distribution stay flat,
    which is the right signal to investigate without paging.
    """
    if not source:
        return
    written = 0
    for k, v in source.items():
        if written >= MAX_KEYS_PER_DICT:
            break
        if not isinstance(k, str) or not k:
            continue
        if len(k) > MAX_KEY_CHARS:
            continue
        if not _KEY_PATTERN.match(k):
            continue
        attr_name = f"{prefix}{k}"
        if attr_name in _RESERVED_LOG_RECORD_ATTRS:
            # Skip silently — the SDK shouldn't be using these names, but
            # if it does we'd rather lose the field than abort the batch.
            continue
        target[attr_name] = _coerce_str(v)
        written += 1


def _build_extra(
    event: TelemetryEvent,
    common_attrs: dict[str, str],
    channel_attrs: dict[str, str],
) -> dict[str, str]:
    """Build the ``extra`` dict for a single event.

    Order matters: per-event values (event.*) win over common / channel
    fields when keys collide. In practice they don't collide (event has
    ``trace_id`` / ``request_id`` / etc. that the common block lacks), but
    the precedence is documented so future additions don't surprise anyone.
    """
    extra: dict[str, str] = {}
    extra.update(channel_attrs)
    extra.update(common_attrs)

    extra["event"] = event.name
    extra["event_ts_ms"] = str(event.ts)
    extra["event_level"] = event.level

    if event.trace_id:
        extra["trace_id"] = event.trace_id
    if event.conversation_external_id:
        extra["conversation_external_id"] = event.conversation_external_id
    if event.request_id:
        extra["request_id"] = event.request_id
    if event.client_message_id:
        extra["client_message_id"] = event.client_message_id

    _flatten_dict(extra, "props_", event.props)
    _flatten_dict(extra, "metrics_", event.metrics)
    return extra


def _common_to_attrs(common) -> dict[str, str]:  # noqa: ANN001 — Pydantic model
    """Return the subset of ``common`` to attach as log attributes.

    None values are dropped so empty fields don't pollute every record's
    ``log_attributes`` JSON.
    """
    out: dict[str, str] = {
        "session_id": common.session_id,
        "device_id": common.device_id,
    }
    for k in (
        "user_id",
        "release",
        "url",
        "user_agent",
        "network_type",
        "viewport",
        "sdk_name",
        "sdk_version",
    ):
        v = getattr(common, k, None)
        if v is not None:
            out[k] = _coerce_str(v)
    if common.ts_offset_ms is not None:
        out["ts_offset_ms"] = str(common.ts_offset_ms)
    return out


class TelemetryService:
    """Stateless service. Methods are static-style for symmetry with the
    rest of the project (see ``ChannelService``, ``AgentService``, …)."""

    @staticmethod
    async def ingest(
        *,
        channel,  # noqa: ANN001 — Channel ORM, kept duck-typed for testability
        body: TelemetryBatchRequest,
    ) -> TelemetryBatchResponse:
        """Validate, trim and emit a batch of frontend events.

        Returns counts so the SDK can detect oversized batches without
        having to read response headers. The kill switch
        (``settings.TELEMETRY_ENABLED``) short-circuits before *any*
        logger call so flipping it really does drop the cost — the
        request still 200s so the SDK doesn't escalate to localStorage
        replay needlessly.
        """
        incoming = list(body.events)
        # Trim to the per-batch cap. The order is preserved so the
        # earliest-emitted events are the ones we keep — that aligns with
        # the SDK's "head-of-line replay" semantics.
        accepted_events = incoming[:MAX_EVENTS_PER_BATCH]
        dropped = len(incoming) - len(accepted_events)

        if not settings.TELEMETRY_ENABLED:
            # Treat the whole batch as dropped from a billing/observability
            # standpoint — we never called the logger.
            return TelemetryBatchResponse(
                accepted=0, dropped=len(incoming),
            )

        if not accepted_events:
            return TelemetryBatchResponse(accepted=0, dropped=dropped)

        common_attrs = _common_to_attrs(body.common)
        channel_attrs: dict[str, str] = {
            "channel_token": channel.token,
            "tenant_id": str(channel.tenant_id),
            "agent_id": str(channel.agent_id) if channel.agent_id else "",
        }

        # Snapshot the request-level contextvars BEFORE the batch loop so
        # we can restore them after. The route entry didn't set them
        # (this endpoint takes no chat body) so they should already be
        # at the default ``"-"`` sentinel, but we treat the saved values
        # as opaque to avoid coupling.
        prev_trace = _trace_id_var.get()
        prev_conv = _conversation_external_id_var.get()
        prev_req = _request_id_var.get()

        try:
            for event in accepted_events:
                # CRITICAL: ``TraceFilter`` reads contextvars when each
                # ``logger.log()`` runs and writes them onto the LogRecord
                # (overwriting the ``extra={'trace_id': ...}`` we set in
                # ``_build_extra``). So we MUST set every var per event,
                # falling back to ``"-"`` for missing fields — otherwise
                # event N would inherit event N-1's trace_id at the
                # otel_logs top-level column, silently mis-attributing
                # log lines to the wrong turn.
                #
                # Note: ``set_trace_id("")`` would auto-generate a fresh
                # uuid (see ``trace.py``), so we touch the underlying
                # ContextVar directly when clearing — this is the one
                # place that reset semantics matter and the public
                # setter doesn't expose a "no value" mode.
                if event.trace_id:
                    set_trace_id(event.trace_id)
                else:
                    _trace_id_var.set("-")

                if event.conversation_external_id:
                    set_conversation_external_id(event.conversation_external_id)
                else:
                    _conversation_external_id_var.set("-")

                if event.request_id:
                    set_request_id(event.request_id)
                else:
                    _request_id_var.set("-")

                extra = _build_extra(event, common_attrs, channel_attrs)
                level = _level_to_log(event.level)
                # Plain message keeps the otel_logs.body column readable
                # (``frontend event: sse_done``) while all the structured data
                # rides on log_attributes.
                logger.log(level, "frontend event: %s", event.name, extra=extra)
        finally:
            # Defence-in-depth: don't leak the last event's correlation
            # IDs into post-loop logging (the response build, FastAPI's
            # access log, exception handlers in middleware etc.). The
            # task that owns this request would tear down its own
            # context anyway, but explicit restore keeps lifetime
            # reasoning local to this function.
            _trace_id_var.set(prev_trace)
            _conversation_external_id_var.set(prev_conv)
            _request_id_var.set(prev_req)

        return TelemetryBatchResponse(
            accepted=len(accepted_events), dropped=dropped,
        )
