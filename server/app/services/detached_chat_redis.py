"""
Redis Streams backend for detached public Web SDK chat (DETACHED_CHAT_BACKEND="redis").

Makes the detached round cross-process so the API can run multiple workers /
replicas (so a single event loop's CPU is not the concurrency ceiling).

Why Streams (not pub/sub): the public Web SDK must support seamless reconnects
via ``Last-Event-ID`` — a reconnect (even onto a different worker) has to replay
the events emitted while the socket was down. Pub/sub has no history, so it would
drop that tail. A Redis Stream keeps the round's events, so any consumer can read
from the start, skip what the client already saw, and then tail live updates.

Design:
- The worker that wins a ``SET NX`` claim for a ``client_message_id`` runs the
  engine and ``XADD``s each SSE event to a per-message stream; it appends a CLOSE
  sentinel when the round ends. The claim is a SHORT lease while running (renewed
  ~3x/lease) so a crashed producer frees it quickly; on completion it is extended
  to a LONG TTL as a "done marker" so a late reconnect replays the finished
  stream instead of re-running the engine.
- ANY worker serving a request for that message ``XREAD``s the stream from the
  beginning, filters out events at/below the client's ``Last-Event-ID``, yields
  the rest, then blocks for live updates. The producing worker consumes the same
  stream, so there is exactly one read path.
- Cancel uses a durable cancel key (covers the subscribe race) plus a pub/sub
  fast path; the owning worker's listener cancels the engine task. Consumer
  disconnects do NOT cancel (detached semantics) — the producer is kept alive by
  a module-level task reference.
- Streams are bounded (``MAXLEN``) and TTL'd so they self-clean.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import suppress
from typing import AsyncIterator

from app.db import session as db_session
from app.db.redis import redis_client
from app.services.agent_engine_service import AgentEngineService
from app.services.round_event_buffer import parse_event_id

logger = logging.getLogger(__name__)

_CLOSE_SENTINEL = "\x00__DETACHED_CLOSE__\x00"
_CANCEL_MESSAGE = "cancel"
_EVENT_FIELD = "d"
# Active-run lease: SHORT so a crashed/stuck producer's claim frees within this
# window and another worker can re-claim. Renewed ~3x per lease while running.
_RUN_LEASE_TTL_SEC = 120
# Done marker: after a clean finish the claim is extended to this LONG TTL so a
# late reconnect within the window replays the finished stream instead of
# re-running the engine. Matches the stream's own TTL.
_RUN_DONE_TTL_SEC = 3600
# Stream lifetime: must outlast a full round + the reconnect window. Bounded
# length caps memory; sized generously so a normal round never trims events a
# reconnecting client still needs. If a pathological round DOES overflow it,
# ``_consume_stream`` detects the gap and emits ``assistant_reset`` instead of
# silently dropping frames.
_STREAM_TTL_SEC = 3600
_STREAM_MAXLEN = 20000
_HEARTBEAT_INTERVAL_SEC = 5.0
_CONTROL_POLL_SEC = 1.0
# Consumer liveness guard: if the stream key itself is absent for this long, no
# event will ever arrive (the producer died before its first write, or a botched
# finalize left a claim marker without a readable stream). End the relay so the
# client's retry re-enters and can re-claim, instead of heartbeating forever.
# Sized at the run lease so by the time we bail, a dead producer's claim has also
# expired and a re-claim will actually win.
_STREAM_IDLE_BAIL_SEC = _RUN_LEASE_TTL_SEC

# Identifies this process for claim ownership / debugging.
_WORKER_ID = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
_ACTIVE_RUN_VALUE = f"active:{_WORKER_ID}"
_DONE_RUN_VALUE = f"done:{_WORKER_ID}"

# Renew / promote the run claim only if THIS worker still owns it (value match),
# so a stalled-then-resumed worker never extends a claim another worker re-took.
# Returns 1 on success, 0 if the claim was lost / re-owned.
_RENEW_CLAIM_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end"
)

# All finalize-time shared writes are gated SERVER-SIDE on "do we still own the
# run claim", atomically with the write. The local ``lost_claim`` flag is only a
# fast-path: if this worker stalled past the lease and another worker re-claimed
# WITHOUT our renewer noticing (e.g. ``renew_stop`` fired first), ``lost_claim``
# can be false yet we no longer own the run. These scripts ensure a stale
# producer can never corrupt the new owner's stream / claim / cancel flag.
# KEYS[1]=run_key KEYS[2]=stream_key; ARGV: active_value, maxlen, field, data, stream_ttl
_OWNED_XADD_LUA = (
    "if redis.call('get', KEYS[1]) ~= ARGV[1] then return 0 end "
    "redis.call('xadd', KEYS[2], 'MAXLEN', '~', ARGV[2], '*', ARGV[3], ARGV[4]) "
    "redis.call('expire', KEYS[2], ARGV[5]) "
    "return 1"
)
# Append CLOSE, refresh the stream TTL, drop the run's cancel flag, and promote
# the run claim to the long "done marker" TTL — all atomically and only while we
# own the claim. The cancel-flag DEL must run BEFORE the promote (it is gated on
# us still owning the ACTIVE claim), so folding it into this one call is the only
# correct ordering — a separate post-promote DEL would always no-op.
# KEYS[1]=run_key KEYS[2]=stream_key KEYS[3]=cancel_key
# ARGV: active_value, maxlen, field, close_sentinel, stream_ttl, done_value, run_done_ttl
_OWNED_CLOSE_LUA = (
    "if redis.call('get', KEYS[1]) ~= ARGV[1] then return 0 end "
    "redis.call('xadd', KEYS[2], 'MAXLEN', '~', ARGV[2], '*', ARGV[3], ARGV[4]) "
    "redis.call('expire', KEYS[2], ARGV[5]) "
    "redis.call('del', KEYS[3]) "
    "redis.call('set', KEYS[1], ARGV[6], 'EX', ARGV[7]) "
    "return 1"
)
# Release our active claim early after lock loss / persistent Redis uncertainty,
# but only if it is still ours. This shortens consumer retry windows without
# deleting a new owner's active claim or a done marker.
_OWNED_DEL_RUN_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)
# Explicit cancel should be a terminal stream, not a bare socket close. Append a
# cancel-flavored done frame plus CLOSE, drop the cancel flag, and promote the
# run to a done marker — all in one owner-guarded Lua call (same DEL-before-
# promote ordering as _OWNED_CLOSE_LUA).
# KEYS[1]=run_key KEYS[2]=stream_key KEYS[3]=cancel_key
# ARGV: active_value, maxlen, field, done_frame, close_sentinel, stream_ttl, done_value, run_done_ttl
_OWNED_CANCEL_CLOSE_LUA = (
    "if redis.call('get', KEYS[1]) ~= ARGV[1] then return 0 end "
    "redis.call('xadd', KEYS[2], 'MAXLEN', '~', ARGV[2], '*', ARGV[3], ARGV[4]) "
    "redis.call('xadd', KEYS[2], 'MAXLEN', '~', ARGV[2], '*', ARGV[3], ARGV[5]) "
    "redis.call('expire', KEYS[2], ARGV[6]) "
    "redis.call('del', KEYS[3]) "
    "redis.call('set', KEYS[1], ARGV[7], 'EX', ARGV[8]) "
    "return 1"
)

# Keeps detached producer tasks alive after the originating HTTP request returns
# (the consumer may disconnect long before the round finishes).
_producer_tasks: set[asyncio.Task[None]] = set()


def _stream_key(owner: str, cmid: str) -> str:
    return f"dcs:stream:{owner}:{cmid}"


def _ctl_channel(owner: str, cmid: str) -> str:
    return f"dcs:ctl:{owner}:{cmid}"


def _run_key(owner: str, cmid: str) -> str:
    return f"dcs:run:{owner}:{cmid}"


def _cancel_key(owner: str, cmid: str) -> str:
    return f"dcs:cancel:{owner}:{cmid}"


def _redis_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _is_active_run_value(value: object) -> bool:
    text = _redis_text(value)
    return bool(text and text.startswith("active:"))


def _is_done_run_value(value: object) -> bool:
    text = _redis_text(value)
    return bool(text and text.startswith("done:"))


def _extract_round_cursor(raw_event: str) -> tuple[int, int] | None:
    """Parse ``(round, seq)`` from an event's ``id:`` line, or ``None``."""
    first_line = raw_event.split("\n", 1)[0]
    if not first_line.startswith("id:"):
        return None
    return parse_event_id(first_line[3:].strip())


def _reset_frame(round_number: int) -> str:
    """A standalone ``assistant_reset`` SSE frame, used when a reconnect cannot
    be resumed seamlessly (the events it needs were trimmed from the stream).
    The client discards its partial bubble and re-renders from the replay."""
    return (
        "event: assistant_reset\ndata: "
        + json.dumps(
            # ``tool_round`` kept for wire-compatibility with the engine's own
            # assistant_reset payload (client type marks it required).
            {"round_number": round_number, "tool_round": 0, "reason": "resume_gap"},
            ensure_ascii=False,
        )
        + "\n\n"
    )


def _cancel_done_frame() -> str:
    return (
        "event: done\ndata: "
        + json.dumps(
            {
                "assistant_step_id": None,
                "final_content": "",
                "finish_reason": "cancelled",
                "cancelled": True,
            },
            ensure_ascii=False,
        )
        + "\n\n"
    )


def _is_terminal_frame(data: str) -> bool:
    """True for the round's closing ``done`` / ``error`` SSE frame."""
    return "\nevent: done\n" in data or "\nevent: error\n" in data


async def stream_public_chat_redis(
    *,
    channel_token: str,
    agent_id: int,
    user_message: str,
    conversation_id: int | None,
    customer_context: dict | None,
    resume: bool,
    client_message_id: str,
    last_event_id: str | None,
) -> AsyncIterator[str]:
    """Relay a detached round's SSE events from a Redis Stream, starting the
    producer on this worker if we win the claim."""
    client = redis_client.client
    owner = channel_token
    cmid = client_message_id

    claimed = await client.set(
        _run_key(owner, cmid), _ACTIVE_RUN_VALUE, nx=True, ex=_RUN_LEASE_TTL_SEC,
    )
    if claimed:
        task = asyncio.create_task(
            _produce(
                owner=owner,
                cmid=cmid,
                agent_id=agent_id,
                user_message=user_message,
                conversation_id=conversation_id,
                customer_context=customer_context,
                resume=resume,
                last_event_id=last_event_id,
            )
        )
        _producer_tasks.add(task)
        task.add_done_callback(_producer_tasks.discard)

    async for event in _consume_stream(
        _stream_key(owner, cmid),
        run_key=_run_key(owner, cmid),
        last_event_id=last_event_id,
    ):
        yield event


async def cancel_public_chat_redis(
    *,
    channel_token: str,
    client_message_id: str,
) -> bool:
    """Broadcast a cancel for a detached round. Returns whether a live run claim
    existed when we asked (best-effort — the owning worker performs the cancel)."""
    client = redis_client.client
    run_value = await client.get(_run_key(channel_token, client_message_id))
    if not _is_active_run_value(run_value):
        # No active run claim (never started, already finished, or done-marker
        # only): nothing to cancel. Skip the durable flag — leaving one around
        # would poison a future re-claim of the same cmid (it would self-cancel
        # on startup). Mirrors the memory backend returning False for a missing
        # live run.
        return False
    # Durable flag covers the window where the producer claimed but its listener
    # hasn't subscribed yet (or a publish races the subscribe). Short TTL: the
    # producer clears it on finalize, and it only needs to outlive the
    # subscribe race, not the whole done-marker window.
    await client.set(
        _cancel_key(channel_token, client_message_id), "1", ex=_RUN_LEASE_TTL_SEC,
    )
    await client.publish(
        _ctl_channel(channel_token, client_message_id), _CANCEL_MESSAGE,
    )
    return True


async def _consume_stream(
    stream_key: str, *, run_key: str, last_event_id: str | None,
) -> AsyncIterator[str]:
    """Read the stream from the start, skip events at/below ``last_event_id``
    (so a reconnect replays only its missing tail), then block for live events
    until the CLOSE sentinel. Emits heartbeats during idle gaps.

    Gap safety: if the events the client needs (right after its Last-Event-ID)
    were already trimmed by ``MAXLEN``, seamless continuation is impossible — we
    emit ``assistant_reset`` and replay everything still available instead of
    silently dropping the missing middle.
    """
    client = redis_client.client
    cursor = parse_event_id(last_event_id)
    # No cursor (fresh connection) => nothing to skip and no gap to check.
    gap_checked = cursor is None
    last_id = "0"
    block_ms = int(_HEARTBEAT_INTERVAL_SEC * 1000)
    yielded_any = False
    last_terminal: str | None = None
    idle_ms = 0
    bail_ms = int(_STREAM_IDLE_BAIL_SEC * 1000)
    while True:
        result = await client.xread({stream_key: last_id}, count=256, block=block_ms)
        if not result:
            # Liveness guard:
            # - stream missing + ACTIVE claim => producer may still be waiting on
            #   round lock / first token; keep the detached SSE open.
            # - stream missing + DONE/missing claim => no replayable stream will
            #   arrive; end so the SDK can retry/reclaim instead of pinging
            #   forever.
            # - stream exists + missing claim => producer died mid-round before
            #   CLOSE; end after the grace window so retry can re-claim.
            # - stream exists + DONE claim => producer finished and will never
            #   write another event; if we got here we already drained the tail
            #   without seeing CLOSE (it was trimmed, or our cursor is past it),
            #   so end rather than ping forever for a frame that won't come.
            # - stream exists + ACTIVE claim => legitimately idle/live round;
            #   keep waiting for the next event / CLOSE.
            idle_ms += block_ms
            if idle_ms >= bail_ms:
                stream_alive = await client.exists(stream_key)
                run_value = await client.get(run_key)
                claim_alive = run_value is not None
                # Keep waiting ONLY while an active producer still owns the run.
                # A done marker (finished, no more events) or a missing claim
                # (producer gone) both mean no further frame will arrive.
                should_bail = not _is_active_run_value(run_value)
                if should_bail:
                    logger.warning(
                        "Detached relay ending after %.0fs idle "
                        "(stream_alive=%s claim_alive=%s run_value=%s) — client should "
                        "re-claim. key=%s",
                        idle_ms / 1000, bool(stream_alive), bool(claim_alive),
                        _redis_text(run_value),
                        stream_key,
                    )
                    return
                idle_ms = 0
            yield ": ping\n\n"
            continue
        idle_ms = 0
        _name, entries = result[0]
        for entry_id, fields in entries:
            last_id = entry_id
            data = fields.get(_EVENT_FIELD, "")
            if data == _CLOSE_SENTINEL:
                # If the client's cursor was already at/past the terminal frame
                # (it reconnected after seeing ``done``/``error``), we skipped
                # everything and yielded nothing. Replay the terminal frame so
                # the SDK sees a clean end instead of treating a 0-frame stream
                # as a dropped connection and retrying forever. Mirrors the
                # engine's in-memory "cursor past terminal" fast-path.
                if not yielded_any and last_terminal is not None:
                    yield last_terminal
                return
            event_cursor = _extract_round_cursor(data)
            if _is_terminal_frame(data):
                last_terminal = data

            # On the first event that carries a cursor, check for a trim gap.
            if not gap_checked and event_cursor is not None:
                gap_checked = True
                if (
                    event_cursor[0] == cursor[0]
                    and event_cursor[1] > cursor[1] + 1
                ):
                    logger.warning(
                        "Detached stream gap — client at e%d but stream head is "
                        "e%d; resetting. key=%s",
                        cursor[1], event_cursor[1], stream_key,
                    )
                    yield _reset_frame(event_cursor[0])
                    yielded_any = True
                    cursor = None  # replay everything still available

            if (
                cursor is not None
                and event_cursor is not None
                and event_cursor[0] == cursor[0]
                and event_cursor[1] <= cursor[1]
            ):
                continue
            yield data
            yielded_any = True


async def _produce(
    *,
    owner: str,
    cmid: str,
    agent_id: int,
    user_message: str,
    conversation_id: int | None,
    customer_context: dict | None,
    resume: bool,
    last_event_id: str | None,
) -> None:
    client = redis_client.client
    stream_key = _stream_key(owner, cmid)

    # Subscribe to the control channel BEFORE the engine starts so a cancel that
    # arrives early is not missed.
    cancel_pubsub = client.pubsub()
    await cancel_pubsub.subscribe(_ctl_channel(owner, cmid))

    # ``lost_claim`` is shared by three tasks: the engine publisher sets it the
    # instant an owner-guarded XADD reveals we no longer own the run, the renewer
    # sets it when a renew is rejected/times out, and the finalizer reads it to
    # decide whether touching the shared stream is safe.
    renew_stop = asyncio.Event()
    lost_claim = asyncio.Event()
    engine_task = asyncio.create_task(
        _run_engine_publish(
            owner=owner,
            cmid=cmid,
            agent_id=agent_id,
            user_message=user_message,
            conversation_id=conversation_id,
            customer_context=customer_context,
            resume=resume,
            last_event_id=last_event_id,
            lost_claim=lost_claim,
        )
    )
    cancel_task = asyncio.create_task(
        _listen_cancel(cancel_pubsub, engine_task, owner=owner, cmid=cmid)
    )
    # Renew the run claim while the engine runs so a round longer than the claim
    # TTL is not re-claimed (and re-run) by another worker. If we ever discover
    # we lost the claim, the renewer sets ``lost_claim`` and aborts the engine to
    # prevent double-run; ``_produce`` then must NOT touch the shared stream
    # (another worker now owns it).
    renew_task = asyncio.create_task(
        _renew_claim(owner, cmid, renew_stop, engine_task, lost_claim)
    )
    cancelled = False
    try:
        await engine_task
    except asyncio.CancelledError:
        cancelled = True
        logger.info("Detached redis chat cancelled — owner=%s cmid=%s", owner, cmid)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Detached redis chat stream error")
        # Write the error frame + refresh TTL only while we still own the claim
        # (server-side guard, atomic) so a stale producer can't inject an error
        # into another worker's live run. The expire also bounds a stream whose
        # only write is this error frame.
        if not lost_claim.is_set():
            with suppress(Exception):
                await client.eval(
                    _OWNED_XADD_LUA, 2, _run_key(owner, cmid), stream_key,
                    _ACTIVE_RUN_VALUE, _STREAM_MAXLEN, _EVENT_FIELD,
                    "event: error\ndata: "
                    + json.dumps({"message": str(exc)}, ensure_ascii=False)
                    + "\n\n",
                    _STREAM_TTL_SEC,
                )
    finally:
        renew_stop.set()
        with suppress(asyncio.CancelledError):
            await renew_task
        cancel_task.cancel()
        with suppress(asyncio.CancelledError):
            await cancel_task
        with suppress(Exception):
            await cancel_pubsub.aclose()
        # If we lost the claim, another worker now owns this stream + claim.
        # Touching either would corrupt its run: writing CLOSE could truncate
        # the new producer's stream mid-round, and deleting the cancel flag could
        # drop a cancel meant for the new run. Leave all shared state alone.
        if lost_claim.is_set():
            logger.warning(
                "Skipping stream finalize — claim lost to another worker. "
                "owner=%s cmid=%s", owner, cmid,
            )
            with suppress(Exception):
                await client.eval(
                    _OWNED_DEL_RUN_LUA, 1, _run_key(owner, cmid), _ACTIVE_RUN_VALUE,
                )
            return
        if cancelled:
            # Cancel flag (KEYS[3]) is cleared inside the same owner-guarded call
            # before the done-marker promote — it only covered the subscribe race
            # for THIS run.
            with suppress(Exception):
                await client.eval(
                    _OWNED_CANCEL_CLOSE_LUA, 3, _run_key(owner, cmid), stream_key,
                    _cancel_key(owner, cmid),
                    _ACTIVE_RUN_VALUE, _STREAM_MAXLEN, _EVENT_FIELD,
                    _cancel_done_frame(), _CLOSE_SENTINEL, _STREAM_TTL_SEC,
                    _DONE_RUN_VALUE, _RUN_DONE_TTL_SEC,
                )
            return
        # Finalize atomically and ONLY while we own the claim: append CLOSE
        # (after which the round is replayable and must not be re-run), refresh
        # the stream TTL, clear the cancel flag (KEYS[3]), and promote the run
        # claim to the long "done marker" TTL. Doing all of this in one owner-
        # guarded Lua call means a stale producer (lost the lease without our
        # renewer noticing) can neither truncate the new owner's stream nor
        # extend/drop THEIR claim/cancel flag, and we never land in a "CLOSE
        # written but claim still short-lease re-runnable" state.
        with suppress(Exception):
            await client.eval(
                _OWNED_CLOSE_LUA, 3, _run_key(owner, cmid), stream_key,
                _cancel_key(owner, cmid),
                _ACTIVE_RUN_VALUE, _STREAM_MAXLEN, _EVENT_FIELD, _CLOSE_SENTINEL,
                _STREAM_TTL_SEC, _DONE_RUN_VALUE, _RUN_DONE_TTL_SEC,
            )


async def _run_engine_publish(
    *,
    owner: str,
    cmid: str,
    agent_id: int,
    user_message: str,
    conversation_id: int | None,
    customer_context: dict | None,
    resume: bool,
    last_event_id: str | None,
    lost_claim: asyncio.Event,
) -> None:
    client = redis_client.client
    stream_key = _stream_key(owner, cmid)
    run_key = _run_key(owner, cmid)
    async with db_session.session_scope() as db:
        stream = AgentEngineService.run_chat_round(
            db,
            agent_id=agent_id,
            user_message=user_message,
            conversation_id=conversation_id,
            customer_context=customer_context,
            resume=resume,
            # Detached: a dropped SSE consumer must not stop the round.
            is_disconnected_cb=None,
            client_message_id=cmid,
            last_event_id=last_event_id,
        )
        try:
            async for event in stream:
                # Every live event is appended under a server-side owner guard
                # (XADD + refresh TTL only while THIS worker still holds the run
                # claim). If we ever stalled past the lease and another worker
                # re-claimed, the guard returns 0 — stop producing immediately so
                # we never interleave our frames into the new owner's stream or
                # keep burning LLM tokens for a round we no longer own. The TTL
                # refresh on the first event also makes cleanup crash-safe.
                wrote = await client.eval(
                    _OWNED_XADD_LUA, 2, run_key, stream_key,
                    _ACTIVE_RUN_VALUE, _STREAM_MAXLEN, _EVENT_FIELD, event,
                    _STREAM_TTL_SEC,
                )
                if not wrote:
                    logger.warning(
                        "Run claim lost mid-stream (XADD rejected) — stopping "
                        "producer to avoid corrupting the new owner. "
                        "owner=%s cmid=%s", owner, cmid,
                    )
                    lost_claim.set()
                    return
        finally:
            # Close the engine generator promptly if we broke out early, so its
            # own cancellation/cleanup (incomplete-step persistence) runs now
            # rather than at GC time.
            close = getattr(stream, "aclose", None)
            if callable(close):
                await close()


async def _listen_cancel(
    pubsub, engine_task: asyncio.Task[None], *, owner: str, cmid: str,
) -> None:
    client = redis_client.client
    cancel_key = _cancel_key(owner, cmid)
    try:
        # Immediate check: a cancel may have been flagged before we subscribed.
        if await client.exists(cancel_key):
            engine_task.cancel()
            return
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=_CONTROL_POLL_SEC,
            )
            if message is not None:
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8", "replace")
                if data == _CANCEL_MESSAGE:
                    engine_task.cancel()
                    return
            # Durable fallback: a publish that raced our subscribe is caught by
            # the flag on the next poll tick.
            if await client.exists(cancel_key):
                engine_task.cancel()
                return
    except asyncio.CancelledError:
        raise


async def _renew_claim(
    owner: str,
    cmid: str,
    stop: asyncio.Event,
    engine_task: asyncio.Task[None],
    lost_claim: asyncio.Event,
) -> None:
    """Keep THIS worker's run claim alive while it produces the round. Renews
    ~3x per TTL so a single missed beat never lets the claim expire mid-round.

    Two abort paths, both set ``lost_claim`` and cancel the engine so the round
    can't keep running (and double-write / double-XADD) outside a claim we own:

    1. Value-guarded renew returns 0 — the claim is gone or now owned by another
       worker (we stalled past the TTL and it was re-claimed).
    2. Renew keeps failing with transient Redis errors long enough that the claim
       must have expired (no confirmed renew within the TTL). We can no longer
       prove we own it, so we treat it as lost rather than running unguarded.
    """
    client = redis_client.client
    run_key = _run_key(owner, cmid)
    interval = _RUN_LEASE_TTL_SEC / 3.0
    # The lease is good until ``last_ok + lease``. Abort one interval before that
    # so we never run past a possible expiry while only seeing transient errors.
    last_ok = time.monotonic()
    try:
        while not stop.is_set():
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=interval)
            if stop.is_set():
                return
            try:
                renewed = await client.eval(
                    _RENEW_CLAIM_LUA, 1, run_key, _ACTIVE_RUN_VALUE,
                    _RUN_LEASE_TTL_SEC,
                )
            except Exception:  # noqa: BLE001 — transient redis error
                if time.monotonic() - last_ok >= _RUN_LEASE_TTL_SEC - interval:
                    logger.error(
                        "Run-claim renew failing past TTL — claim likely expired; "
                        "aborting engine. owner=%s cmid=%s", owner, cmid,
                    )
                    lost_claim.set()
                    engine_task.cancel()
                    return
                logger.warning("Run-claim renew failed (transient) — cmid=%s", cmid)
                continue
            if not renewed:
                logger.error(
                    "Run claim lost — another worker may have re-claimed; aborting "
                    "engine to avoid double-run. owner=%s cmid=%s", owner, cmid,
                )
                lost_claim.set()
                engine_task.cancel()
                return
            last_ok = time.monotonic()
    except asyncio.CancelledError:
        raise
