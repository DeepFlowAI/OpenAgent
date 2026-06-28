"""Unit tests for the Redis Streams detached-chat backend's pure relay logic:
gap detection on reconnect and the durable cancel-flag fast path. Uses a tiny
in-memory fake so no real Redis is needed."""
import asyncio

import pytest

from app.services import detached_chat_redis as svc


class _FakeRedis:
    """Minimal Redis stand-in covering only what the tested paths use."""

    def __init__(self) -> None:
        self._streams: dict[str, list[tuple[str, dict]]] = {}
        self._kv: dict[str, str] = {}
        self._seq = 0

    async def xadd(self, key, fields, maxlen=None, approximate=False):
        self._seq += 1
        entry_id = f"{self._seq}-0"
        self._streams.setdefault(key, []).append((entry_id, dict(fields)))
        return entry_id

    async def xread(self, streams, count=None, block=None):
        # Single-key reads only (matches the consumer's usage).
        (key, last_id), = streams.items()
        last_seq = int(last_id.split("-")[0]) if last_id != "0" else 0
        out = [
            (eid, f)
            for eid, f in self._streams.get(key, [])
            if int(eid.split("-")[0]) > last_seq
        ]
        if not out:
            return None
        return [(key, out[: count or len(out)])]

    async def exists(self, key):
        # Real Redis EXISTS works on any key type (kv or stream).
        return 1 if (key in self._kv or key in self._streams) else 0

    async def get(self, key):
        return self._kv.get(key)

    async def set(self, key, value, nx=False, ex=None, px=None):
        if nx and key in self._kv:
            return None
        self._kv[key] = value
        return True

    async def delete(self, key):
        return 1 if self._kv.pop(key, None) is not None else 0

    async def expire(self, key, ttl):
        return 1 if (key in self._kv or key in self._streams) else 0

    async def publish(self, channel, message):
        return 0

    async def eval(self, script, numkeys, *args):
        # Faithful (enough) stand-ins for the module's owner-guarded Lua, all of
        # which gate on "does run_key still hold our worker id".
        if script is svc._RENEW_CLAIM_LUA:
            run_key, worker = args[0], args[1]
            return 1 if self._kv.get(run_key) == worker else 0
        if script is svc._OWNED_XADD_LUA:
            run_key, stream_key = args[0], args[1]
            worker, _maxlen, field, data, _ttl = args[2], args[3], args[4], args[5], args[6]
            if self._kv.get(run_key) != worker:
                return 0
            await self.xadd(stream_key, {field: data})
            return 1
        if script is svc._OWNED_CLOSE_LUA:
            run_key, stream_key, cancel_key = args[0], args[1], args[2]
            worker, _maxlen, field, sentinel = args[3], args[4], args[5], args[6]
            if self._kv.get(run_key) != worker:
                return 0
            await self.xadd(stream_key, {field: sentinel})
            self._kv.pop(cancel_key, None)
            self._kv[run_key] = args[8]
            return 1
        if script is svc._OWNED_DEL_RUN_LUA:
            run_key, worker = args[0], args[1]
            if self._kv.get(run_key) != worker:
                return 0
            self._kv.pop(run_key, None)
            return 1
        if script is svc._OWNED_CANCEL_CLOSE_LUA:
            run_key, stream_key, cancel_key = args[0], args[1], args[2]
            worker, _maxlen, field = args[3], args[4], args[5]
            done_frame, sentinel = args[6], args[7]
            if self._kv.get(run_key) != worker:
                return 0
            await self.xadd(stream_key, {field: done_frame})
            await self.xadd(stream_key, {field: sentinel})
            self._kv.pop(cancel_key, None)
            self._kv[run_key] = args[9]
            return 1
        raise AssertionError(f"unexpected script: {script!r}")


def _evt(round_no: int, seq: int, body: str = "x") -> str:
    return f"id: r{round_no}-e{seq}\nevent: content_delta\ndata: {body}\n\n"


class _FakeSessionScope:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


def _patch_engine(monkeypatch, events):
    async def _fake_round(*_a, **_k):
        for ev in events:
            yield ev

    monkeypatch.setattr(svc.AgentEngineService, "run_chat_round", _fake_round)
    monkeypatch.setattr(svc.db_session, "session_scope", lambda: _FakeSessionScope())


async def _collect(stream_key, last_event_id, fake, run_key="dcs:run:live"):
    # Default run_key marked "live" so tests whose streams end with CLOSE never
    # trip the liveness bail; tests that exercise the bail pass an absent key.
    if not await fake.exists(run_key):
        await fake.set(run_key, "active:test-worker")
    out = []
    async for frame in svc._consume_stream(
        stream_key, run_key=run_key, last_event_id=last_event_id,
    ):
        out.append(frame)
    return out


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(svc.redis_client, "_client", fake)
    return fake


@pytest.mark.asyncio
async def test_consume_replays_only_missing_tail(fake_redis):
    key = "s"
    for seq in (3, 4, 5):
        await fake_redis.xadd(key, {svc._EVENT_FIELD: _evt(1, seq)})
    await fake_redis.xadd(key, {svc._EVENT_FIELD: svc._CLOSE_SENTINEL})

    frames = await _collect(key, "r1-e4", fake_redis)

    # Only e5 (> e4) replayed; no reset since head e3 ≤ e4+1 is not the gap
    # condition (consumer skips e3,e4 and yields e5).
    assert frames == [_evt(1, 5)]


@pytest.mark.asyncio
async def test_consume_emits_reset_on_trim_gap(fake_redis):
    key = "s"
    # Stream head is e5 but client last saw e2 => e3,e4 were trimmed (gap).
    for seq in (5, 6):
        await fake_redis.xadd(key, {svc._EVENT_FIELD: _evt(1, seq)})
    await fake_redis.xadd(key, {svc._EVENT_FIELD: svc._CLOSE_SENTINEL})

    frames = await _collect(key, "r1-e2", fake_redis)

    assert frames[0].startswith("event: assistant_reset")
    assert "resume_gap" in frames[0]
    assert '"tool_round": 0' in frames[0]  # wire-compat with engine payload
    # After reset, everything still available is replayed.
    assert frames[1:] == [_evt(1, 5), _evt(1, 6)]


@pytest.mark.asyncio
async def test_consume_replays_terminal_when_cursor_past_done(fake_redis):
    key = "s"
    # Client already saw through the done frame (e6); reconnects with cursor e6.
    await fake_redis.xadd(key, {svc._EVENT_FIELD: _evt(1, 5)})
    done = "id: r1-e6\nevent: done\ndata: {}\n\n"
    await fake_redis.xadd(key, {svc._EVENT_FIELD: done})
    await fake_redis.xadd(key, {svc._EVENT_FIELD: svc._CLOSE_SENTINEL})

    frames = await _collect(key, "r1-e6", fake_redis)

    # Everything was skipped, so replay the terminal frame once instead of
    # ending with zero frames (which the SDK would treat as a dropped stream).
    assert frames == [done]


@pytest.mark.asyncio
async def test_consume_bails_when_stream_absent(fake_redis, monkeypatch):
    # No events ever written for this key. The consumer must not heartbeat
    # forever — once the idle grace passes and the stream is still absent, it
    # ends the relay so the client's retry can re-claim.
    monkeypatch.setattr(svc, "_STREAM_IDLE_BAIL_SEC", 0)

    frames = []
    async for frame in svc._consume_stream(
        "missing-stream", run_key="dcs:run:missing", last_event_id=None,
    ):
        frames.append(frame)

    assert frames == []


@pytest.mark.asyncio
async def test_consume_keeps_waiting_for_active_claim_before_first_event(fake_redis, monkeypatch):
    # Active producer may be waiting on a round lock / first LLM token. The
    # consumer should heartbeat, not bail, just because the stream key does not
    # exist yet.
    monkeypatch.setattr(svc, "_STREAM_IDLE_BAIL_SEC", 0)
    monkeypatch.setattr(svc, "_HEARTBEAT_INTERVAL_SEC", 0.001)
    run_key = svc._run_key("o", "c")
    await fake_redis.set(run_key, "active:producer")

    agen = svc._consume_stream("missing-stream", run_key=run_key, last_event_id=None)
    try:
        frame = await asyncio.wait_for(agen.__anext__(), timeout=0.1)
    finally:
        await agen.aclose()

    assert frame == ": ping\n\n"


@pytest.mark.asyncio
async def test_consume_bails_when_stream_missing_but_done_marker_exists(fake_redis, monkeypatch):
    # A done marker without a readable stream is unrecoverable for this relay
    # window. End promptly so the client retry path can decide what to do.
    monkeypatch.setattr(svc, "_STREAM_IDLE_BAIL_SEC", 0)
    run_key = svc._run_key("o", "c")
    await fake_redis.set(run_key, "done:producer")

    frames = await _collect("missing-stream", None, fake_redis, run_key=run_key)

    assert frames == []


@pytest.mark.asyncio
async def test_consume_bails_when_producer_died_midstream(fake_redis, monkeypatch):
    # Producer wrote one event then crashed: stream exists but has no CLOSE and
    # the run claim has expired. The consumer must replay what's there and then
    # bail (not heartbeat forever) so the client retry can re-claim.
    monkeypatch.setattr(svc, "_STREAM_IDLE_BAIL_SEC", 0)
    key = "s"
    await fake_redis.xadd(key, {svc._EVENT_FIELD: _evt(1, 0)})

    # run_key intentionally absent (never set) => claim_alive is False.
    out = []
    async for frame in svc._consume_stream(
        key, run_key="dcs:run:dead", last_event_id=None,
    ):
        out.append(frame)

    assert out == [_evt(1, 0)]


@pytest.mark.asyncio
async def test_consume_bails_when_stream_present_but_done_marker_no_close(
    fake_redis, monkeypatch,
):
    # Stream has events but the CLOSE sentinel was trimmed (MAXLEN) or our cursor
    # is past it, while the run claim is a done marker. The producer is finished
    # and will never write again, so the consumer must replay the tail and then
    # bail instead of heartbeating forever.
    monkeypatch.setattr(svc, "_STREAM_IDLE_BAIL_SEC", 0)
    key = "s"
    await fake_redis.xadd(key, {svc._EVENT_FIELD: _evt(1, 0)})
    run_key = svc._run_key("o", "c")
    await fake_redis.set(run_key, "done:producer")

    out = []
    async for frame in svc._consume_stream(key, run_key=run_key, last_event_id=None):
        out.append(frame)

    assert out == [_evt(1, 0)]


@pytest.mark.asyncio
async def test_consume_fresh_connection_replays_all(fake_redis):
    key = "s"
    for seq in (0, 1):
        await fake_redis.xadd(key, {svc._EVENT_FIELD: _evt(1, seq)})
    await fake_redis.xadd(key, {svc._EVENT_FIELD: svc._CLOSE_SENTINEL})

    frames = await _collect(key, None, fake_redis)

    assert frames == [_evt(1, 0), _evt(1, 1)]


@pytest.mark.asyncio
async def test_listen_cancel_honors_preexisting_flag(fake_redis):
    await fake_redis.set(svc._cancel_key("owner", "cmid"), "1")

    async def _never_ends():
        await asyncio.sleep(60)

    engine_task = asyncio.create_task(_never_ends())
    await svc._listen_cancel(None, engine_task, owner="owner", cmid="cmid")

    assert engine_task.cancelled() or engine_task.cancelling()
    engine_task.cancel()


@pytest.mark.asyncio
async def test_renew_claim_aborts_engine_when_claim_lost(fake_redis):
    # Claim is owned by a DIFFERENT worker (we lost it after a stall).
    await fake_redis.set(svc._run_key("o", "c"), "active:someone-else")

    async def _never_ends():
        await asyncio.sleep(60)

    engine_task = asyncio.create_task(_never_ends())
    stop = asyncio.Event()
    lost_claim = asyncio.Event()
    # interval = TTL/3; force an immediate tick by shrinking the TTL.
    monkey_ttl = svc._RUN_LEASE_TTL_SEC
    svc._RUN_LEASE_TTL_SEC = 0  # interval 0 => renew checks right away
    try:
        await svc._renew_claim("o", "c", stop, engine_task, lost_claim)
    finally:
        svc._RUN_LEASE_TTL_SEC = monkey_ttl

    assert lost_claim.is_set()
    assert engine_task.cancelled() or engine_task.cancelling()
    engine_task.cancel()


@pytest.mark.asyncio
async def test_renew_claim_aborts_on_persistent_transient_error(fake_redis):
    await fake_redis.set(svc._run_key("o", "c"), svc._ACTIVE_RUN_VALUE)

    async def _raise(*_a, **_k):
        raise RuntimeError("redis down")

    fake_redis.eval = _raise

    async def _never_ends():
        await asyncio.sleep(60)

    engine_task = asyncio.create_task(_never_ends())
    stop = asyncio.Event()
    lost_claim = asyncio.Event()
    monkey_ttl = svc._RUN_LEASE_TTL_SEC
    # TTL 0 => threshold (TTL - interval) = 0, so the first transient error is
    # already "past TTL" and must abort instead of being swallowed forever.
    svc._RUN_LEASE_TTL_SEC = 0
    try:
        await svc._renew_claim("o", "c", stop, engine_task, lost_claim)
    finally:
        svc._RUN_LEASE_TTL_SEC = monkey_ttl

    assert lost_claim.is_set()
    assert engine_task.cancelled() or engine_task.cancelling()
    engine_task.cancel()


@pytest.mark.asyncio
async def test_owned_close_noop_when_claim_re_owned(fake_redis):
    # Another worker re-claimed the run; a stale producer's CLOSE must NOT land
    # in the stream (it would truncate the new owner's live run) and must NOT
    # promote/extend the new owner's claim.
    run_key = svc._run_key("o", "c")
    stream_key = svc._stream_key("o", "c")
    cancel_key = svc._cancel_key("o", "c")
    await fake_redis.set(run_key, "active:another-worker")
    await fake_redis.set(cancel_key, "1")  # belongs to the NEW owner's run

    rv = await fake_redis.eval(
        svc._OWNED_CLOSE_LUA, 3, run_key, stream_key, cancel_key,
        svc._ACTIVE_RUN_VALUE, svc._STREAM_MAXLEN, svc._EVENT_FIELD,
        svc._CLOSE_SENTINEL, svc._STREAM_TTL_SEC, svc._DONE_RUN_VALUE,
        svc._RUN_DONE_TTL_SEC,
    )

    assert rv == 0
    assert stream_key not in fake_redis._streams  # no CLOSE written
    assert await fake_redis.exists(cancel_key)  # new owner's cancel flag intact


@pytest.mark.asyncio
async def test_owned_close_writes_and_clears_cancel_when_owned(fake_redis):
    run_key = svc._run_key("o", "c")
    stream_key = svc._stream_key("o", "c")
    cancel_key = svc._cancel_key("o", "c")
    await fake_redis.set(run_key, svc._ACTIVE_RUN_VALUE)
    await fake_redis.set(cancel_key, "1")

    rv = await fake_redis.eval(
        svc._OWNED_CLOSE_LUA, 3, run_key, stream_key, cancel_key,
        svc._ACTIVE_RUN_VALUE, svc._STREAM_MAXLEN, svc._EVENT_FIELD,
        svc._CLOSE_SENTINEL, svc._STREAM_TTL_SEC, svc._DONE_RUN_VALUE,
        svc._RUN_DONE_TTL_SEC,
    )

    assert rv == 1
    _eid, fields = fake_redis._streams[stream_key][-1]
    assert fields[svc._EVENT_FIELD] == svc._CLOSE_SENTINEL
    assert fake_redis._kv[run_key] == svc._DONE_RUN_VALUE
    # Cancel flag is dropped atomically (before the done-marker promote).
    assert not await fake_redis.exists(cancel_key)


@pytest.mark.asyncio
async def test_owned_cancel_close_writes_terminal_done_and_clears_cancel(fake_redis):
    run_key = svc._run_key("o", "c")
    stream_key = svc._stream_key("o", "c")
    cancel_key = svc._cancel_key("o", "c")
    await fake_redis.set(run_key, svc._ACTIVE_RUN_VALUE)
    await fake_redis.set(cancel_key, "1")

    rv = await fake_redis.eval(
        svc._OWNED_CANCEL_CLOSE_LUA, 3, run_key, stream_key, cancel_key,
        svc._ACTIVE_RUN_VALUE, svc._STREAM_MAXLEN, svc._EVENT_FIELD,
        svc._cancel_done_frame(), svc._CLOSE_SENTINEL, svc._STREAM_TTL_SEC,
        svc._DONE_RUN_VALUE, svc._RUN_DONE_TTL_SEC,
    )

    assert rv == 1
    bodies = [f[svc._EVENT_FIELD] for _id, f in fake_redis._streams[stream_key]]
    assert bodies[0].startswith("event: done")
    assert '"cancelled": true' in bodies[0]
    assert bodies[1] == svc._CLOSE_SENTINEL
    assert fake_redis._kv[run_key] == svc._DONE_RUN_VALUE
    assert not await fake_redis.exists(cancel_key)


@pytest.mark.asyncio
async def test_run_engine_publish_writes_events_when_owned(fake_redis, monkeypatch):
    run_key = svc._run_key("o", "c")
    stream_key = svc._stream_key("o", "c")
    await fake_redis.set(run_key, svc._ACTIVE_RUN_VALUE)
    _patch_engine(monkeypatch, [_evt(1, 0), _evt(1, 1)])

    lost = asyncio.Event()
    await svc._run_engine_publish(
        owner="o", cmid="c", agent_id=1, user_message="hi",
        conversation_id=None, customer_context=None, resume=False,
        last_event_id=None, lost_claim=lost,
    )

    assert not lost.is_set()
    bodies = [f[svc._EVENT_FIELD] for _id, f in fake_redis._streams[stream_key]]
    assert bodies == [_evt(1, 0), _evt(1, 1)]


@pytest.mark.asyncio
async def test_run_engine_publish_stops_when_claim_lost(fake_redis, monkeypatch):
    # Another worker owns the run claim: the owner-guarded XADD must reject the
    # first event, set lost_claim, and write nothing into the shared stream.
    run_key = svc._run_key("o", "c")
    stream_key = svc._stream_key("o", "c")
    await fake_redis.set(run_key, "active:another-worker")
    _patch_engine(monkeypatch, [_evt(1, 0), _evt(1, 1)])

    lost = asyncio.Event()
    await svc._run_engine_publish(
        owner="o", cmid="c", agent_id=1, user_message="hi",
        conversation_id=None, customer_context=None, resume=False,
        last_event_id=None, lost_claim=lost,
    )

    assert lost.is_set()
    assert stream_key not in fake_redis._streams


@pytest.mark.asyncio
async def test_cancel_returns_false_and_sets_no_flag_without_run(fake_redis):
    rv = await svc.cancel_public_chat_redis(
        channel_token="o", client_message_id="c",
    )

    assert rv is False
    assert not await fake_redis.exists(svc._cancel_key("o", "c"))


@pytest.mark.asyncio
async def test_cancel_returns_false_for_done_marker(fake_redis):
    await fake_redis.set(svc._run_key("o", "c"), "done:producer")

    rv = await svc.cancel_public_chat_redis(
        channel_token="o", client_message_id="c",
    )

    assert rv is False
    assert not await fake_redis.exists(svc._cancel_key("o", "c"))


@pytest.mark.asyncio
async def test_cancel_sets_durable_flag_when_run_exists(fake_redis):
    await fake_redis.set(svc._run_key("o", "c"), svc._ACTIVE_RUN_VALUE)

    rv = await svc.cancel_public_chat_redis(
        channel_token="o", client_message_id="c",
    )

    assert rv is True
    assert await fake_redis.exists(svc._cancel_key("o", "c"))


@pytest.mark.asyncio
async def test_renew_claim_does_not_abort_when_owned(fake_redis):
    await fake_redis.set(svc._run_key("o", "c"), svc._ACTIVE_RUN_VALUE)

    async def _never_ends():
        await asyncio.sleep(60)

    engine_task = asyncio.create_task(_never_ends())
    stop = asyncio.Event()
    lost_claim = asyncio.Event()
    monkey_ttl = svc._RUN_LEASE_TTL_SEC
    svc._RUN_LEASE_TTL_SEC = 0  # interval 0 => ticks immediately
    try:
        task = asyncio.create_task(
            svc._renew_claim("o", "c", stop, engine_task, lost_claim)
        )
        await asyncio.sleep(0.01)  # let it tick (renew succeeds, no abort)
        stop.set()
        await task
    finally:
        svc._RUN_LEASE_TTL_SEC = monkey_ttl

    assert not lost_claim.is_set()
    assert not engine_task.cancelled()
    engine_task.cancel()
