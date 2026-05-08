"""
Small SSE helpers shared by chat endpoints.
"""
import asyncio
from contextlib import suppress
from typing import AsyncIterator


async def with_sse_heartbeat(
    source: AsyncIterator[str],
    *,
    interval_sec: float = 5.0,
) -> AsyncIterator[str]:
    """Yield SSE comments while waiting for the next real event.

    Mobile browsers and embedded WebViews are more likely to stall long-lived
    streaming POST responses when no bytes arrive for several seconds. SSE
    comment frames are ignored by clients but keep the transport active.
    """
    iterator = source.__aiter__()
    next_event = asyncio.create_task(iterator.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait({next_event}, timeout=interval_sec)
            if not done:
                yield ": ping\n\n"
                continue

            try:
                yield next_event.result()
            except StopAsyncIteration:
                break
            next_event = asyncio.create_task(iterator.__anext__())
    finally:
        if not next_event.done():
            next_event.cancel()
            with suppress(asyncio.CancelledError):
                await next_event
