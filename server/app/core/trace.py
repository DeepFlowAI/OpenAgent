"""
Request trace context — provides a unique trace_id per request via contextvars.

Four correlation IDs are exposed:

* ``trace_id``                    — full 128-bit hex (32 chars), one per HTTP
                                    request, also used as the OpenTelemetry
                                    trace_id. Console shows the full value.
                                    Use to grep ONE request end-to-end.
* ``conversation_id``             — internal DB integer PK of the conversation
                                    (e.g. ``457``). Useful for joining against
                                    application DB tables.
* ``conversation_external_id``    — the user-facing conversation identifier
                                    (e.g. ``conv_jwdi78u4``). This is the value
                                    the frontend and public API use, so it's
                                    what users actually paste into Grafana.
* ``request_id``                  — optional client-supplied correlation id
                                    (e.g. ``req_abc123``) carried in the chat
                                    request body. Useful when frontend wants
                                    to correlate its own logs / error reports
                                    with a backend trace.

All four are injected into every log record by ``TraceFilter`` so they:
  - show up in the console line prefix (trace_id only — others would be too
    verbose), and
  - get exported as searchable log attributes by the OTel LoggingHandler
    (i.e. you can directly query
    ``WHERE log_attributes['conversation_external_id'] = 'conv_jwdi78u4'``
    or ``log_attributes['request_id'] = 'req_abc123'`` in Grafana / DeepFlow
    Log).

Usage:
    # At request entry point (middleware or router):
    set_trace_id()                                    # auto-generate
    set_request_id(body.request_id)                   # from request body
    set_conversation_external_id(body.external_id)    # from request body

    # Inside a chat round (agent engine):
    set_conversation_id(conv.id)                      # 457
    set_conversation_external_id(conv.external_id)    # conv_jwdi78u4

    # Anywhere in the same async context:
    tid = get_trace_id()
    cid = get_conversation_id()
    ext = get_conversation_external_id()
    rid = get_request_id()
"""
import logging
import uuid
from contextvars import ContextVar

_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")
_conversation_id_var: ContextVar[str] = ContextVar("conversation_id", default="-")
_conversation_external_id_var: ContextVar[str] = ContextVar(
    "conversation_external_id", default="-"
)
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def set_trace_id(trace_id: str | None = None) -> str:
    """Set trace_id for the current async context.

    Auto-generates a full 128-bit hex (32 chars) so the same value can be
    used as the OpenTelemetry trace_id (which is 128-bit by spec). The
    console formatter truncates this to 12 chars for readability — the full
    value is what gets shipped to OTel / your log backend and returned in the
    ``X-Trace-Id`` response header, so clients and Grafana queries match
    byte-for-byte.
    """
    tid = trace_id or uuid.uuid4().hex
    _trace_id_var.set(tid)
    return tid


def get_trace_id() -> str:
    """Get trace_id from the current async context."""
    return _trace_id_var.get()


def get_trace_id_int() -> int | None:
    """Return the current trace_id as an int (128-bit), or None if unset/invalid.

    Used by the OpenTelemetry IdGenerator to align OTel's trace_id with the
    application's trace_id so the same value appears in the console log
    prefix, the X-Trace-Id response header, and the your tracing backend's trace tree.
    """
    tid = _trace_id_var.get()
    if not tid or tid == "-":
        return None
    try:
        return int(tid, 16)
    except ValueError:
        return None


def set_conversation_id(conversation_id: int | str | None) -> str:
    """Set the internal numeric conversation_id for the current async context.

    Accepts int / str / None and normalizes to str so log attributes stay
    a single type (Greptime treats columns as a fixed type per ingest).
    """
    cid = "-" if conversation_id in (None, 0, "0", "") else str(conversation_id)
    _conversation_id_var.set(cid)
    return cid


def get_conversation_id() -> str:
    """Get the internal numeric conversation_id from the current async context."""
    return _conversation_id_var.get()


def set_conversation_external_id(external_id: str | None) -> str:
    """Set the user-facing conversation external_id (e.g. ``conv_jwdi78u4``).

    This is the identifier the frontend and public API surface to end users —
    using it as a log/span attribute means users can paste their session id
    straight into Grafana to find every log emitted for that conversation.
    """
    eid = "-" if not external_id else str(external_id)
    _conversation_external_id_var.set(eid)
    return eid


def get_conversation_external_id() -> str:
    """Get the conversation external_id from the current async context."""
    return _conversation_external_id_var.get()


def set_request_id(request_id: str | None) -> str:
    """Set the client-supplied per-request correlation id.

    Frontend / API clients can pass their own ``request_id`` in the chat
    request body so the same id appears in their logs and in your log backend,
    which makes cross-stack debugging trivial. If the caller does not pass
    one we leave the context var unset (``-``) — we already have ``trace_id``
    serving as the canonical per-request id.
    """
    rid = "-" if not request_id else str(request_id)
    _request_id_var.set(rid)
    return rid


def get_request_id() -> str:
    """Get the client-supplied request_id from the current async context."""
    return _request_id_var.get()


class TraceFilter(logging.Filter):
    """Logging filter that injects ``trace_id``, ``conversation_id``,
    ``conversation_external_id`` and ``request_id`` into every log record.

    All fields are added as record attributes — the stdout formatter uses
    ``%(trace_id)s`` directly, and the OTel ``LoggingHandler`` automatically
    forwards every non-standard record attribute as an OTLP log attribute.
    Net result: queries like
    ``WHERE log_attributes['conversation_external_id'] = 'conv_jwdi78u4'``
    or ``WHERE log_attributes['request_id'] = 'req_abc123'`` work in
    Grafana / your log backend without any further code changes.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id_var.get()  # type: ignore[attr-defined]
        record.conversation_id = _conversation_id_var.get()  # type: ignore[attr-defined]
        record.conversation_external_id = (  # type: ignore[attr-defined]
            _conversation_external_id_var.get()
        )
        record.request_id = _request_id_var.get()  # type: ignore[attr-defined]
        return True
