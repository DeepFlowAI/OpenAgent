"""
Telemetry batch ingest schemas.

Frontend SDK ships per-page-session events (chat lifecycle, SSE state, retries,
timeouts) in batched POSTs. The backend trims oversized batches, flattens
``props``/``metrics`` onto a stdlib ``logging`` ``LogRecord`` and lets the
existing OTel ``LoggingHandler`` ship the records to ``otel_logs`` — no new
table, no new exporter. Field naming and defaults are designed so a
``json_get_string(log_attributes, ...)`` query in the log-analyzer Skill
works without needing to know the SDK's internal shape.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Maximum number of events accepted in a single batch (service-layer trim).
# Anything beyond this number is dropped silently and reported in the response
# ``dropped`` count. The SDK is configured well below this bound (20 events
# per flush) so a healthy client never trips it; this is purely a runtime
# safety net for bugs.
MAX_EVENTS_PER_BATCH = 100

# Hard upper bound enforced at the schema layer — exceeding it 422s the whole
# batch instead of silently trimming, which protects the API from a malicious
# client that POSTs 10k+ events in one body. Sized at 2× MAX_EVENTS_PER_BATCH
# so a slightly-too-eager-but-honest client still gets a normal trim response,
# while a clearly abusive payload is rejected before any flatten/log work runs.
SCHEMA_MAX_EVENTS_PER_BATCH = 200

# Per-event upper bounds on the props/metrics dicts. We accept up to
# MAX_KEYS_PER_DICT keys; the rest are silently truncated. Each value is
# coerced to ``str`` for OTLP export and capped to MAX_VALUE_CHARS to keep
# log_attributes column rows from blowing up.
MAX_KEYS_PER_DICT = 32
MAX_VALUE_CHARS = 256

# Schema-layer kill switches — paired with the service-layer trims above so
# the same defence-in-depth pattern ``events`` already follows applies to
# props/metrics too. A misbehaving client can still send a 200-event batch
# (passes ``SCHEMA_MAX_EVENTS_PER_BATCH``) where each event has 10k props of
# 1MB strings; without these bounds Pydantic would parse the whole tree
# into Python objects before the service-layer trim runs. Sized at 2×/4× the
# silent-trim caps so an honest client never trips them.
SCHEMA_MAX_KEYS_PER_DICT = 64
SCHEMA_MAX_VALUE_CHARS = 1024

# Maximum length of any individual key in props / metrics. Anything longer
# is silently dropped at the service layer (paired with a warning log).
# Long keys are usually a client-side typo — silently dropping the bad key
# keeps the rest of the event landing in otel_logs instead of 422-ing the
# whole batch over a single bad attribute.
MAX_KEY_CHARS = 64


TelemetryLevel = Literal["info", "warn", "error"]


class TelemetryCommon(BaseModel):
    """Shared metadata for the whole batch.

    Mirrors Doubao's ``common`` block but de-duplicated to one copy per batch
    (Doubao repeats it per event — wasteful for both bandwidth and the
    columnar storage that flattens these into ``log_attributes``).
    """

    model_config = ConfigDict(extra="ignore")

    session_id: str = Field(..., min_length=1, max_length=64)
    device_id: str = Field(..., min_length=1, max_length=64)
    user_id: str | None = Field(None, max_length=128)
    release: str | None = Field(None, max_length=32)
    url: str | None = Field(None, max_length=1024)
    user_agent: str | None = Field(None, max_length=512)
    network_type: str | None = Field(None, max_length=32)
    viewport: str | None = Field(None, max_length=32)
    sdk_name: str | None = Field(None, max_length=32)
    sdk_version: str | None = Field(None, max_length=32)
    # Rough wall-clock skew between client and server, supplied by the SDK
    # so timeline reconstruction can correct for clients with bad clocks.
    ts_offset_ms: int | None = None


class TelemetryEvent(BaseModel):
    """A single user-journey event point.

    The ``name`` regex doubles as a soft contract — any new event type the
    SDK adds must be ASCII snake_case so it lines up with the
    ``log_attributes.event = '...'`` filter pattern in the log-analyzer
    Recipe section.
    """

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    ts: int = Field(..., description="Client epoch milliseconds")
    level: TelemetryLevel = "info"

    # Cross-stack correlation IDs. None of these are required because some
    # events fire before the round (e.g. message_send_start) or after a
    # crash (replay-from-localStorage), but ``trace_id`` is the keystone of
    # any post-mortem so the SDK should attach it whenever available.
    trace_id: str | None = Field(None, max_length=64)
    conversation_external_id: str | None = Field(None, max_length=64)
    request_id: str | None = Field(None, max_length=64)
    client_message_id: str | None = Field(None, max_length=64)

    # ``props`` are categorical/identity fields (round_number, resume bool,
    # error_type, etc). ``metrics`` are numeric (durations, counts) so the
    # log-analyzer can ``CAST(... AS DOUBLE)`` them without per-event type
    # detection. Splitting them up-front saves us a query-time inference pass.
    #
    # ``max_length`` on a Pydantic ``dict`` field bounds the number of keys
    # — a schema-layer DoS guard mirroring the ``events`` cap above.
    props: dict[str, str | int | float | bool] | None = Field(
        default=None, max_length=SCHEMA_MAX_KEYS_PER_DICT
    )
    metrics: dict[str, int | float] | None = Field(
        default=None, max_length=SCHEMA_MAX_KEYS_PER_DICT
    )

    @model_validator(mode="after")
    def _bound_string_value_lengths(self) -> "TelemetryEvent":
        """Reject any string ``props`` value longer than ``SCHEMA_MAX_VALUE_CHARS``.

        Prevents the "200 events × 1MB value" DoS shape that the
        ``events`` and dict-size caps don't catch on their own. ``metrics``
        is typed as numeric only, so Pydantic already rejects strings
        there at the type-coercion step.

        Raising (rather than the silent service-layer truncate) is the
        right call here: a value that big is never a legitimate honest
        payload — even ``error_excerpt`` is sliced to 200 chars in the
        SDK before emit.
        """
        if not self.props:
            return self
        for k, v in self.props.items():
            if isinstance(v, str) and len(v) > SCHEMA_MAX_VALUE_CHARS:
                raise ValueError(
                    f"props[{k[:32]!r}] value exceeds "
                    f"{SCHEMA_MAX_VALUE_CHARS} chars (got {len(v)})"
                )
        return self


class TelemetryBatchRequest(BaseModel):
    """Body of POST /public/channels/{token}/telemetry/events.

    The ``events`` list is bounded at the schema layer (rather than relying
    purely on the service-side trim) so the FastAPI body-parse stage rejects
    pathologically large payloads before they're materialised into Python
    objects. Without this cap a client that posted, say, 100k events would
    force Pydantic to allocate every TelemetryEvent before the service
    layer's ``MAX_EVENTS_PER_BATCH`` could trim — pointlessly burning CPU
    and memory on something we'd throw away anyway.
    """

    model_config = ConfigDict(extra="ignore")

    common: TelemetryCommon
    events: list[TelemetryEvent] = Field(
        default_factory=list, max_length=SCHEMA_MAX_EVENTS_PER_BATCH
    )

    @model_validator(mode="after")
    def _events_must_have_one_entry(self) -> "TelemetryBatchRequest":
        # An empty batch is a no-op for the backend but still costs one
        # round trip; we accept it (returning accepted=0/dropped=0) rather
        # than rejecting because mid-pageload races between SDK init and
        # flush legitimately produce an empty drain. This validator is a
        # placeholder that future shape-checks (e.g. cross-event ordering)
        # can hook into without changing the public contract.
        return self


class TelemetryBatchResponse(BaseModel):
    """Outcome counts. ``accepted`` and ``dropped`` always sum to the
    incoming ``len(events)``; the SDK uses ``dropped > 0`` as a soft signal
    to slow down its emit rate."""

    accepted: int
    dropped: int
