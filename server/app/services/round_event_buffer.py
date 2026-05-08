"""
In-memory ring buffer of recently-emitted SSE events, keyed by the round
they belong to. Backs the "Last-Event-ID resume" path.

Why: the prior resume implementation rebuilt the SSE stream from
``conversation_steps`` rows on every reconnect — readable but lossy
(per-token deltas were collapsed into one big ``content_delta``) AND
unable to do "pick up exactly where we left off". The buffer keeps the
RAW event text the client just lost, so a reconnect within the TTL
window lets us replay starting from ``last_event_id + 1`` byte-for-byte
— no ``assistant_reset`` needed, the client sees seamless continuation.

DB persistence stays as the long-term audit + cold-replay fallback
(server restart, TTL expired, multi-process deployment without shared
buffer): when the buffer misses, callers fall back to the existing
step-replay path.

Constraints (deliberately small / simple):

- **Single process only.** A multi-worker deployment would need a Redis
  pub/sub or sticky-session strategy, but our current setup is
  single-Uvicorn-worker + nginx in front, so per-process is fine.
- **Bounded memory.** ``MAX_EVENTS_PER_ROUND`` × ``MAX_TRACKED_ROUNDS``
  caps the worst case (≈ 1024 × 256 ≈ 256K small strings).
- **TTL eviction is lazy** (checked on access). No background task —
  reconnects exercise the buffer, idle entries get GC'd next time we
  need a slot.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass

# Tunables. Sized for our current single-worker FastAPI deployment serving
# ≤ ~100 concurrent rounds. Each event is small (<2KB on average for
# content_delta), so worst-case memory ≈ MAX_TRACKED_ROUNDS × MAX_EVENTS_PER_ROUND × 2KB
# ≈ 256 × 1024 × 2KB ≈ 512 MB ceiling — but in practice rounds are evicted
# well before they fill, so steady-state usage is far lower.
TTL_SECONDS = 60.0
"""How long a round buffer stays warm after the last event was recorded.
Sized so a typical mobile reconnect (NAT / 4G handover ≤ 30s) lands
inside the window. Beyond this, callers fall back to step-replay."""

MAX_EVENTS_PER_ROUND = 1024
"""Per-round event cap. ~1 minute of dense LLM streaming at ~16ms per
delta ≈ 3000 events; we keep the most recent 1024, which still covers
the entire reconnect window since the older deltas are already
displayed on the client."""

MAX_TRACKED_ROUNDS = 256
"""LRU cap on concurrent round buffers. Eviction order favors least-
recently-touched rounds, since active rounds keep getting writes."""


@dataclass(frozen=True)
class RoundKey:
    """Composite key identifying one chat round. Conversations can have
    many rounds; rounds within a conversation are uniquely numbered."""
    conversation_id: int
    round_number: int


@dataclass
class _Entry:
    """A single buffered SSE event. ``raw`` is the full wire-format
    string ready to ``yield`` back into the response (newlines + headers
    included), so replay does not have to re-serialize anything."""
    seq: int
    raw: str


class _RoundBuffer:
    """One round's bounded sequence of events.

    Locks at the round level, not globally — keeps writes from the
    streaming path off the global registry's lock during the hot path.
    """

    __slots__ = ("_events", "_last_touched", "_lock")

    def __init__(self) -> None:
        self._events: deque[_Entry] = deque(maxlen=MAX_EVENTS_PER_ROUND)
        self._last_touched: float = time.monotonic()
        self._lock = threading.Lock()

    def append(self, seq: int, raw: str) -> None:
        with self._lock:
            self._events.append(_Entry(seq=seq, raw=raw))
            self._last_touched = time.monotonic()

    def slice_after(self, last_seq: int) -> list[str] | None:
        """Return raw events with ``seq > last_seq`` in order.

        Three-state return so callers can tell the difference between
        "nothing more to send" and "I lost the events you need":

        - ``None``: the buffer is empty OR there's a gap the ring
          already evicted (``last_seq < first_seq - 1``). The caller
          MUST fall back to step-replay — replaying ``[]`` here would
          silently swallow lost frames.
        - ``[]``: the cursor is at or past the latest buffered seq.
          The client is up to date; do NOT step-replay (would
          duplicate). Pair with :meth:`latest_raw` if you need to
          short-circuit "cursor past terminal frame" scenarios.
        - non-empty list: the missing tail in order.
        """
        with self._lock:
            self._last_touched = time.monotonic()
            if not self._events:
                return None
            first_seq = self._events[0].seq
            if last_seq < first_seq - 1:
                return None
            return [e.raw for e in self._events if e.seq > last_seq]

    def latest_raw(self) -> str | None:
        """Most recently buffered raw frame, or ``None`` if the buffer
        is empty.

        Designed for the engine's "is the tail a terminal `done` /
        `error` frame?" peek — when :meth:`slice_after` returns ``[]``
        we still need to know whether the round actually finished
        (replay the terminal so the SDK exits cleanly) or merely the
        cursor caught up to a still-streaming round (must step-replay
        because the round will keep emitting).
        """
        with self._lock:
            self._last_touched = time.monotonic()
            if not self._events:
                return None
            return self._events[-1].raw

    def is_expired(self, now: float) -> bool:
        return now - self._last_touched > TTL_SECONDS


class RoundEventBuffer:
    """Process-global registry of round buffers.

    Thread-safe: the streaming engine and FastAPI run on the same event
    loop (so writes are serialized by the loop), but the design makes no
    assumption about that — locks both at the registry and per-round
    levels so a future move to multi-thread / multi-loop runtimes
    doesn't introduce a regression.
    """

    def __init__(self) -> None:
        self._buffers: OrderedDict[RoundKey, _RoundBuffer] = OrderedDict()
        self._lock = threading.Lock()

    def append(self, key: RoundKey, seq: int, raw: str) -> None:
        """Record an emitted SSE event so we can replay it on reconnect."""
        buf = self._get_or_create(key)
        buf.append(seq, raw)

    def slice_after(self, key: RoundKey, last_seq: int) -> list[str] | None:
        """Replay events with ``seq > last_seq`` for ``key``.

        ``None`` means "fall back to step-replay" (no buffer, expired,
        empty, or gap); ``[]`` means "already caught up — don't replay
        anything". Both branches are deliberately distinct so the
        engine's fast-path predicate (``cached and any(... done ...)``)
        only fires when there's something concrete to replay.
        """
        with self._lock:
            buf = self._buffers.get(key)
            if buf is None:
                return None
            self._buffers.move_to_end(key)
        if buf.is_expired(time.monotonic()):
            self.evict(key)
            return None
        return buf.slice_after(last_seq)

    def latest_raw(self, key: RoundKey) -> str | None:
        """Peek at the most recently buffered frame for ``key``, or
        ``None`` when no live buffer is held for the round (missing,
        empty, or expired).

        Companion to :meth:`slice_after` for the cursor-past-terminal
        fast-path: when ``slice_after`` returns ``[]`` we need a way to
        distinguish "round finished, client just retried after `done`"
        from "round still in flight". The first case requires replaying
        the terminal frame so the SDK's done handler fires; the second
        falls back to step-replay because the buffer is up to date but
        the round itself is not.
        """
        with self._lock:
            buf = self._buffers.get(key)
            if buf is None:
                return None
            self._buffers.move_to_end(key)
        if buf.is_expired(time.monotonic()):
            self.evict(key)
            return None
        return buf.latest_raw()

    def evict(self, key: RoundKey) -> None:
        """Remove a round's buffer (e.g. after a successful round end)."""
        with self._lock:
            self._buffers.pop(key, None)

    def _get_or_create(self, key: RoundKey) -> _RoundBuffer:
        with self._lock:
            buf = self._buffers.get(key)
            if buf is not None:
                self._buffers.move_to_end(key)
                return buf
            now = time.monotonic()
            # Opportunistic GC: evict expired buffers when we need a slot.
            if len(self._buffers) >= MAX_TRACKED_ROUNDS:
                expired = [k for k, b in self._buffers.items() if b.is_expired(now)]
                for k in expired:
                    self._buffers.pop(k, None)
                # Still over capacity? Drop the LRU.
                while len(self._buffers) >= MAX_TRACKED_ROUNDS:
                    self._buffers.popitem(last=False)
            buf = _RoundBuffer()
            self._buffers[key] = buf
            return buf

    # ── Test-only helpers ──────────────────────────────────────────────

    def _len(self) -> int:
        with self._lock:
            return len(self._buffers)


# Process-singleton. Tests reset state by calling ``round_event_buffer.evict``
# on whatever keys they touched.
round_event_buffer = RoundEventBuffer()


# ── Event-id helpers (single source of truth for the wire format) ──

def format_event_id(round_number: int, seq: int) -> str:
    """Wire-format event id: ``r{round}-e{seq}``.

    Stable, opaque-looking, hard to confuse with arbitrary strings the
    client might also store. Round number and seq are both monotonic
    within their scope, so a lexicographic compare is NOT meaningful
    across rounds — clients should treat the id as opaque and only
    compare against the last value they remember.
    """
    return f"r{int(round_number)}-e{int(seq)}"


def parse_event_id(value: str | None) -> tuple[int, int] | None:
    """Inverse of :func:`format_event_id`. Returns ``(round, seq)`` on a
    well-formed id, or ``None`` for ``None`` / unparseable input.

    Tolerant by design: malformed ``last_event_id`` from the client
    must not 500 the request — the engine just falls back to "no
    cursor, replay from start of buffer" semantics.
    """
    if not value:
        return None
    try:
        if not value.startswith("r"):
            return None
        round_str, _, seq_str = value[1:].partition("-e")
        if not round_str or not seq_str:
            return None
        return int(round_str), int(seq_str)
    except (ValueError, AttributeError):
        return None
