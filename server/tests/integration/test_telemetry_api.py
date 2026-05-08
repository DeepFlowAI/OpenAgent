"""
Integration tests for the public telemetry batch ingest endpoint.

These tests exercise the wire shape (Pydantic), trim/clamp behaviour, and the
log-attribute contract that the ``log-analyzer`` Skill recipes depend on. We
attach an in-memory ``logging.Handler`` to ``app.frontend.event`` so each
test sees the exact ``LogRecord`` extras without round-tripping to GreptimeDB.

We deliberately do **not** test:

  * The real OTLP exporter — that's an SDK concern, covered upstream.
  * Rate limiting / abuse — out of scope for the first version (see the
    ``§3.4 限流`` section of the design doc).
"""
from __future__ import annotations

import logging
import uuid
from typing import List

import pytest
from httpx import AsyncClient

from app.configs.settings import settings
from tests.conftest import make_auth_header


TENANT = "T_TLM_A"
HEADERS = make_auth_header(TENANT)


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _create_agent(client: AsyncClient) -> int:
    resp = await client.post(
        "/api/v1/agents",
        json={"name": _unique("agent"), "description": "telemetry test"},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_channel(client: AsyncClient, agent_id: int) -> dict:
    resp = await client.post(
        "/api/v1/channels",
        json={"name": _unique("ch"), "agent_id": agent_id},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class _CapturingHandler(logging.Handler):
    """Collects emitted records so tests can assert on flattened
    ``log_attributes`` without booting the OTel pipeline."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: List[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        self.records.append(record)


@pytest.fixture
def captured_logs():
    """Attaches a handler to ``app.frontend.event`` for the duration of one
    test. ``propagate`` is left alone so the OTel handler — when present in
    a real run — still gets the records too."""
    cap = _CapturingHandler()
    logger = logging.getLogger("app.frontend.event")
    prev_level = logger.level
    logger.addHandler(cap)
    logger.setLevel(logging.DEBUG)
    try:
        yield cap
    finally:
        logger.removeHandler(cap)
        logger.setLevel(prev_level)


def _basic_event(name: str = "sse_done", **overrides) -> dict:
    """Build a minimal, schema-valid event suitable for boilerplate."""
    base = {
        "name": name,
        "ts": 1_700_000_000_000,
        "level": "info",
        "metrics": {"first_chunk_ms": 1505},
    }
    base.update(overrides)
    return base


def _basic_common(**overrides) -> dict:
    base = {
        "session_id": "sess-abc",
        "device_id": "dev-xyz",
        "url": "https://example.com/chat/conv_abc",
        "release": "1.0.0",
    }
    base.update(overrides)
    return base


class TestTelemetryAPI:
    """End-to-end coverage for ``POST /v1/public/channels/{token}/telemetry/events``."""

    @pytest.mark.asyncio
    async def test_post_events_returns_200_with_accepted(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        body = {
            "common": _basic_common(),
            "events": [_basic_event() for _ in range(3)],
        }
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json=body,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"accepted": 3, "dropped": 0}
        assert len(captured_logs.records) == 3
        for rec in captured_logs.records:
            assert getattr(rec, "event") == "sse_done"
            assert getattr(rec, "channel_token") == channel["token"]
            assert getattr(rec, "tenant_id") == TENANT

    @pytest.mark.asyncio
    async def test_post_events_invalid_channel_token_returns_404(
        self, client: AsyncClient,
    ):
        resp = await client.post(
            "/api/v1/public/channels/no-such-token-xx/telemetry/events",
            json={"common": _basic_common(), "events": [_basic_event()]},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_post_events_invalid_event_name_returns_422(
        self, client: AsyncClient,
    ):
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        body = {
            "common": _basic_common(),
            "events": [_basic_event(name="UPPERCASE_BAD")],
        }
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json=body,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_post_events_truncates_over_100_events(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        body = {
            "common": _basic_common(),
            "events": [_basic_event() for _ in range(150)],
        }
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json=body,
        )
        assert resp.status_code == 200, resp.text
        # Service caps to MAX_EVENTS_PER_BATCH (100); the rest are accounted
        # for in ``dropped`` so the SDK can back off without re-trying the
        # same oversized batch.
        assert resp.json() == {"accepted": 100, "dropped": 50}
        assert len(captured_logs.records) == 100

    @pytest.mark.asyncio
    async def test_post_events_truncates_over_32_props(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        # 50 props requested; flatten step keeps only the first 32.
        large_props = {f"k{i}": i for i in range(50)}
        body = {
            "common": _basic_common(),
            "events": [_basic_event(props=large_props, metrics=None)],
        }
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json=body,
        )
        assert resp.status_code == 200
        assert resp.json() == {"accepted": 1, "dropped": 0}
        rec = captured_logs.records[-1]
        kept = [
            attr for attr in vars(rec).keys() if attr.startswith("props_")
        ]
        assert len(kept) == 32, f"expected exactly 32 props_* attrs, got {len(kept)}"

    @pytest.mark.asyncio
    async def test_post_events_emits_log_records_with_correct_attributes(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        body = {
            "common": _basic_common(network_type="4g", user_id="u-1"),
            "events": [
                _basic_event(
                    name="sse_done",
                    trace_id="t" * 32,
                    conversation_external_id="conv_jwdi78u4",
                    request_id="req_abc123",
                    client_message_id="cmid-1",
                    props={"round_number": 1, "resume": False},
                    metrics={"first_chunk_ms": 1505, "total_duration_ms": 3210},
                ),
            ],
        }
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json=body,
        )
        assert resp.status_code == 200
        rec = captured_logs.records[-1]
        # Identity & correlation
        assert getattr(rec, "event") == "sse_done"
        assert getattr(rec, "trace_id") == "t" * 32
        assert getattr(rec, "conversation_external_id") == "conv_jwdi78u4"
        assert getattr(rec, "request_id") == "req_abc123"
        assert getattr(rec, "client_message_id") == "cmid-1"
        # Common
        assert getattr(rec, "session_id") == "sess-abc"
        assert getattr(rec, "device_id") == "dev-xyz"
        assert getattr(rec, "user_id") == "u-1"
        assert getattr(rec, "network_type") == "4g"
        # Channel-injected
        assert getattr(rec, "channel_token") == channel["token"]
        assert getattr(rec, "agent_id") == str(agent_id)
        # Flattened props/metrics — strings, by design
        assert getattr(rec, "props_round_number") == "1"
        assert getattr(rec, "props_resume") == "false"
        assert getattr(rec, "metrics_first_chunk_ms") == "1505"
        assert getattr(rec, "metrics_total_duration_ms") == "3210"

    @pytest.mark.asyncio
    async def test_post_events_maps_level_to_severity(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        body = {
            "common": _basic_common(),
            "events": [
                _basic_event(name="sse_done", level="info"),
                _basic_event(name="sse_idle_timeout", level="warn"),
                _basic_event(name="sse_failed", level="error"),
            ],
        }
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json=body,
        )
        assert resp.status_code == 200
        levels = [rec.levelname for rec in captured_logs.records]
        assert levels == ["INFO", "WARNING", "ERROR"]

    @pytest.mark.asyncio
    async def test_post_events_disabled_returns_zero_accepted(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
        monkeypatch,
    ):
        # Flip the kill switch — service must short-circuit before any
        # logger call so toggling the env var is effective without a deploy.
        monkeypatch.setattr(settings, "TELEMETRY_ENABLED", False)
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        body = {
            "common": _basic_common(),
            "events": [_basic_event(), _basic_event()],
        }
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json=body,
        )
        assert resp.status_code == 200
        assert resp.json() == {"accepted": 0, "dropped": 2}
        assert captured_logs.records == [], (
            "no LogRecord should be emitted when TELEMETRY_ENABLED=False"
        )

    @pytest.mark.asyncio
    async def test_post_events_with_empty_events_returns_200(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json={"common": _basic_common(), "events": []},
        )
        assert resp.status_code == 200
        assert resp.json() == {"accepted": 0, "dropped": 0}
        assert captured_logs.records == []

    # ── Hardening tests (post-review) ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_post_events_above_schema_cap_is_rejected(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        """Schema-level guard: ``events`` longer than
        ``SCHEMA_MAX_EVENTS_PER_BATCH`` (200) must 422 BEFORE the service
        layer runs, so a malicious 10k-event payload can't burn CPU on
        Pydantic deserialisation. Honest oversize (≤200) still falls
        through to the silent service-layer trim — see the existing
        ``test_post_events_truncates_over_100_events``.
        """
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        body = {
            "common": _basic_common(),
            "events": [_basic_event() for _ in range(201)],
        }
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json=body,
        )
        assert resp.status_code == 422, resp.text
        # Service layer must NOT have been invoked — no records emitted.
        assert captured_logs.records == []

    @pytest.mark.asyncio
    async def test_post_events_drops_overlong_props_keys(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        """Key-length guard: a single bad key (> ``MAX_KEY_CHARS``) is
        silently dropped at the flatten step. The rest of the event
        still lands so a typo can't 422 a whole batch's worth of
        observability.
        """
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        long_key = "a" * 200  # > MAX_KEY_CHARS (64)
        body = {
            "common": _basic_common(),
            "events": [_basic_event(props={
                "round_number": 1,
                long_key: "should_be_dropped",
            })],
        }
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json=body,
        )
        assert resp.status_code == 200
        rec = captured_logs.records[-1]
        # Good key landed.
        assert getattr(rec, "props_round_number") == "1"
        # Bad key did NOT — vars(rec) snapshot would otherwise contain
        # ``props_aaaaa…`` which would break log_attributes downstream.
        for attr in vars(rec).keys():
            assert long_key not in attr, f"overlong key leaked into LogRecord: {attr}"

    @pytest.mark.asyncio
    async def test_post_events_drops_non_snake_case_keys(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        """Pattern guard: only ``[a-z][a-z0-9_]*`` keys survive flatten.
        This protects the ``json_get_string(log_attributes, 'props_X')``
        contract that all log-analyzer Skill recipes lean on.
        """
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        body = {
            "common": _basic_common(),
            "events": [_basic_event(props={
                "round_number": 1,
                "BadCase": 1,        # rejects: starts with uppercase
                "1starts_with_digit": 1,
                "has-dash": 1,
                "中文键": 1,
            })],
        }
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json=body,
        )
        assert resp.status_code == 200
        rec = captured_logs.records[-1]
        kept_props = {a for a in vars(rec).keys() if a.startswith("props_")}
        # Only the well-formed key survives.
        assert kept_props == {"props_round_number"}, kept_props

    @pytest.mark.asyncio
    async def test_post_events_oversize_body_rejected_by_content_length(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        """Defence layer 1: a body whose ``Content-Length`` exceeds the
        per-route 256 KB cap is rejected via the
        ``_enforce_telemetry_body_cap`` dependency BEFORE Pydantic parses
        anything. Returns 400 (ValidationError) per the project's
        existing exception convention — see ``app.core.exceptions``.

        We craft a real >256 KB body so httpx computes a matching
        Content-Length naturally; lying about the header would require
        bypassing the client's serialisation layer.
        """
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        # 200 events × ~2 KB JSON each ≈ 400 KB, comfortably above the
        # 256 KB cap and below the 200-event schema cap (so the schema
        # layer wouldn't reject this on its own).
        body = {
            "common": _basic_common(),
            "events": [
                _basic_event(props={
                    # 30 props × ~80-byte values → ~2 KB per event JSON
                    f"k_{i:02d}": "v" * 80 for i in range(30)
                })
                for _ in range(200)
            ],
        }
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json=body,
        )
        assert resp.status_code == 400, resp.text
        # No service work should have happened.
        assert captured_logs.records == []

    @pytest.mark.asyncio
    async def test_post_events_above_schema_dict_cap_is_rejected(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        """Schema-layer dict guard: a ``props`` dict bigger than
        ``SCHEMA_MAX_KEYS_PER_DICT`` (64) must 422 the whole batch
        BEFORE the service layer's silent 32-key trim runs. Without
        this, a 200-event payload with 10k props per event would still
        be fully materialised by Pydantic.

        Honest oversize (≤64) still falls through to the silent 32-key
        trim — see ``test_post_events_truncates_over_32_props``.
        """
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        # 65 keys requested — one over the schema cap.
        too_many = {f"k{i:03d}": i for i in range(65)}
        body = {
            "common": _basic_common(),
            "events": [_basic_event(props=too_many, metrics=None)],
        }
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json=body,
        )
        assert resp.status_code == 422, resp.text
        assert captured_logs.records == []

    @pytest.mark.asyncio
    async def test_post_events_oversize_string_value_is_rejected(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        """Schema-layer string value guard: a single ``props`` value
        longer than ``SCHEMA_MAX_VALUE_CHARS`` (1024) must 422. The
        SDK already truncates ``error_excerpt`` to 200 chars, so any
        value above 1024 is either a misconfigured client or an attempt
        to inflate log_attributes column rows.
        """
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        body = {
            "common": _basic_common(),
            "events": [_basic_event(props={
                "round_number": 1,
                "error_excerpt": "x" * 2000,  # > 1024
            })],
        }
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json=body,
        )
        assert resp.status_code == 422, resp.text
        assert captured_logs.records == []

    @pytest.mark.asyncio
    async def test_post_events_per_event_trace_id_isolation(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        """Per-event contextvar reset.

        ``TraceFilter`` injects ``record.trace_id`` (and friends) from
        contextvars onto every LogRecord. Without per-event reset, a
        batch that mixes events-with-trace-id and events-without would
        leak the previous event's trace_id onto the contextvar-derived
        top-level column, silently mis-attributing logs across turns.

        This test sends:
          1. ``sse_done`` with explicit trace_id ``aaaa…``,
          2. ``message_send_start`` with NO trace_id (legitimate — the
             event fires before the backend mints one),

        and asserts (a) record 1 carries ``aaaa…`` end-to-end, (b)
        record 2's contextvar-derived trace_id is the sentinel ``-``
        instead of inheriting record 1's value.
        """
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        trace_a = "a" * 32
        body = {
            "common": _basic_common(),
            "events": [
                _basic_event(
                    name="sse_done",
                    trace_id=trace_a,
                    conversation_external_id="conv_a",
                    request_id="req_a",
                ),
                # Event B intentionally omits trace_id /
                # conversation_external_id / request_id — this is the
                # exact shape ``message_send_start`` ships before the
                # backend has issued any IDs.
                _basic_event(name="message_send_start"),
            ],
        }
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json=body,
        )
        assert resp.status_code == 200, resp.text

        rec_a, rec_b = captured_logs.records[-2], captured_logs.records[-1]

        # Sanity: event names landed in the order we sent them.
        assert getattr(rec_a, "event") == "sse_done"
        assert getattr(rec_b, "event") == "message_send_start"

        # Record A: trace_id present in both ``extra`` and contextvar
        # filter — both paths agree on the same value.
        assert getattr(rec_a, "trace_id") == trace_a
        assert getattr(rec_a, "conversation_external_id") == "conv_a"
        assert getattr(rec_a, "request_id") == "req_a"

        # Record B: NO bleed-over from A. The contextvar is reset to
        # ``-`` before B's emit so TraceFilter writes that sentinel —
        # not A's trace_id — onto B's record. This is the regression
        # the per-event reset was designed to prevent.
        assert getattr(rec_b, "trace_id") == "-", (
            f"event B inherited event A's trace_id "
            f"(got {getattr(rec_b, 'trace_id')!r}, expected '-')"
        )
        assert getattr(rec_b, "conversation_external_id") == "-"
        assert getattr(rec_b, "request_id") == "-"

    @pytest.mark.asyncio
    async def test_post_events_chunked_body_over_cap_is_rejected(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        """Defence layer 1 (chunked path).

        A client that omits ``Content-Length`` (chunked transfer-encoding,
        or just a malicious raw socket write) used to bypass the cap
        because the dependency only checked the header. Now the
        dependency consumes ``request.stream()`` itself and aborts as
        soon as cumulative bytes cross the 256 KB cap.

        We trigger the chunked path by handing httpx an async generator
        as ``content=`` — httpx then sets ``Transfer-Encoding: chunked``
        and omits Content-Length. The body we yield is well over the
        cap, and chunk granularity (~64 KB) means the cap check fires
        long before the full payload is materialised.
        """
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)

        # ~512 KB total in 8 chunks of 64 KB. The body intentionally
        # isn't valid JSON — the cap check should fire before we ever
        # try to parse, so JSON shape is irrelevant.
        async def _chunked_body():
            chunk = b"x" * (64 * 1024)
            for _ in range(8):
                yield chunk

        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            content=_chunked_body(),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400, resp.text
        # Service must NOT have been entered.
        assert captured_logs.records == []

    @pytest.mark.asyncio
    async def test_post_events_chunked_body_under_cap_is_accepted(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        """Negative companion to the chunked-over-cap test.

        Confirms the stream-read path *only* rejects oversized bodies —
        a small chunked body should still parse normally so a client
        that uses chunked encoding for streaming reasons isn't broken
        by the cap. Without this test, a regression that 400s every
        chunked body would slip through.
        """
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        # Pre-build a valid JSON body, then yield it in two chunks via
        # an async generator so httpx switches to chunked encoding.
        import json as _json
        payload = _json.dumps({
            "common": _basic_common(),
            "events": [_basic_event()],
        }).encode("utf-8")
        mid = len(payload) // 2

        async def _chunked_body():
            yield payload[:mid]
            yield payload[mid:]

        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            content=_chunked_body(),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"accepted": 1, "dropped": 0}

    @pytest.mark.asyncio
    async def test_message_send_failed_retryable_uses_warn_level(
        self, client: AsyncClient, captured_logs: _CapturingHandler,
    ):
        """Wire-format check that mirrors the FE-side fix: a
        ``message_send_failed`` event with ``level='warn'`` (the level
        the SDK now sends for retryable HTTP statuses) lands as a
        WARNING LogRecord, not ERROR. Without this the
        ``severity_text='error'`` count in otel_logs would inflate every
        time a turn recovered from a transient 500/429 — which would
        wreck the "actually failed turns" alarm.
        """
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id)
        body = {
            "common": _basic_common(),
            "events": [
                _basic_event(
                    name="message_send_failed",
                    level="warn",
                    props={"http_status": 503, "retryable": True},
                ),
            ],
        }
        resp = await client.post(
            f"/api/v1/public/channels/{channel['token']}/telemetry/events",
            json=body,
        )
        assert resp.status_code == 200
        rec = captured_logs.records[-1]
        assert rec.levelname == "WARNING"
        assert getattr(rec, "event") == "message_send_failed"
        assert getattr(rec, "props_retryable") == "true"
