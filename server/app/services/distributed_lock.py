"""
Redis-backed distributed lock (for ROUND_LOCK_BACKEND="redis").

Why this exists: the per-conversation round lock must serialize rounds of one
conversation. The ``memory`` backend does that with an in-process asyncio lock
(single worker only); the ``advisory`` backend pins a PostgreSQL connection.
This backend uses Redis so the lock is correct across multiple workers/replicas
WITHOUT pinning any DB connection — a prerequisite for horizontal scale where
"only the LLM is the bottleneck".

Design:
- Acquire with ``SET key token NX PX lease_ms`` and a bounded poll-wait.
- A unique ``token`` lets us release/renew only our own lock (compare-and-act
  via Lua), so a lock that already expired and was re-taken is never clobbered.
- A background heartbeat renews the lease while the body runs, so a legitimately
  long round never loses the lock; the lease TTL still guarantees recovery if
  the holder process dies.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from app.core.exceptions import ConflictError
from app.db.redis import redis_client

logger = logging.getLogger(__name__)

# Release/renew only when the stored token matches ours (atomic compare-and-act).
_RELEASE_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)
_RENEW_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('pexpire', KEYS[1], ARGV[2]) else return 0 end"
)

DEFAULT_LEASE_MS = 60_000
"""Lock lease. Renewed every ~lease/3, so it only matters for crash recovery:
if the holder process dies, the lock auto-frees within this window."""


@asynccontextmanager
async def redis_lock(
    key: str,
    *,
    wait_timeout: float,
    lease_ms: int = DEFAULT_LEASE_MS,
    poll_initial: float = 0.05,
    poll_max: float = 1.0,
) -> AsyncIterator[None]:
    """Hold a Redis lock named ``key`` for the duration of the context.

    Waits up to ``wait_timeout`` seconds for the lock; raises
    :class:`ConflictError` on timeout so SSE callers surface ``event: error``
    (mirrors the memory/advisory backends).
    """
    client = redis_client.client
    token = uuid.uuid4().hex
    deadline = time.monotonic() + wait_timeout
    poll = poll_initial

    while True:
        acquired = await client.set(key, token, nx=True, px=lease_ms)
        if acquired:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            logger.warning("Redis lock wait timed out — key=%s after %.1fs", key, wait_timeout)
            raise ConflictError(
                f"Resource {key} is still busy after {int(wait_timeout)}s; please retry shortly"
            )
        await asyncio.sleep(min(poll, remaining))
        poll = min(poll * 1.5, poll_max)

    stop = asyncio.Event()
    # The task running the protected body — cancelled if we lose the lock, so the
    # body can't keep running outside mutual exclusion (another holder may have
    # acquired the lock after our lease expired).
    owner_task = asyncio.current_task()

    async def _renew() -> None:
        # Renew ~3x per lease so a single missed beat never expires the lock.
        # Must stay below the lease, so never floor it above lease/3.
        interval = lease_ms / 1000.0 / 3.0
        # The lease is good until ``last_ok + lease``. If renew keeps failing with
        # transient Redis errors past that window, the lock has almost certainly
        # expired (and may be re-taken) — abort the holder rather than run it
        # unguarded, same as an explicit "lost lock".
        last_ok = time.monotonic()
        lease_sec = lease_ms / 1000.0
        try:
            while not stop.is_set():
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=interval)
                if stop.is_set():
                    return
                try:
                    renewed = await client.eval(_RENEW_LUA, 1, key, token, lease_ms)
                except Exception:  # noqa: BLE001 — transient redis error
                    if time.monotonic() - last_ok >= lease_sec - interval:
                        logger.error(
                            "Redis lock renew failing past lease — aborting holder. "
                            "key=%s", key,
                        )
                        if owner_task is not None:
                            owner_task.cancel()
                        return
                    logger.warning("Redis lock renew failed (transient) — key=%s", key)
                    continue
                if not renewed:
                    # Lost the lock (lease expired and possibly re-taken). The
                    # body is no longer protected, so abort it by cancelling the
                    # holder task rather than letting it run unguarded.
                    logger.error(
                        "Redis lock lost — aborting holder. key=%s", key,
                    )
                    if owner_task is not None:
                        owner_task.cancel()
                    return
                last_ok = time.monotonic()
        except asyncio.CancelledError:
            raise

    renew_task = asyncio.create_task(_renew())
    try:
        yield
    finally:
        stop.set()
        renew_task.cancel()
        with suppress(asyncio.CancelledError):
            await renew_task
        try:
            await client.eval(_RELEASE_LUA, 1, key, token)
        except Exception as exc:  # noqa: BLE001 — release must never break a round
            logger.warning("Failed to release Redis lock key=%s: %s", key, exc)
