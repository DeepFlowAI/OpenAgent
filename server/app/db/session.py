import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.configs.settings import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    # Tag this pool's log records (e.g. "non-checked-in connection" GC errors)
    # with "[main]" so we can tell it apart from ``lock_engine`` in the logs —
    # both are AsyncAdaptedQueuePool and otherwise share the same logger name.
    pool_logging_name="main",
)

# Dedicated pool for session-scoped ``pg_advisory_lock`` connections, which are
# pinned for an entire streaming chat round. Isolating them keeps long-held lock
# connections from starving the main pool used by short-lived request queries —
# the cause of the "QueuePool limit ... connection timed out" exhaustion.
lock_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=settings.DB_LOCK_POOL_SIZE,
    max_overflow=settings.DB_LOCK_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_logging_name="lock",
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def aclose_quietly(closeable: AsyncSession) -> None:
    """Close an AsyncSession / AsyncConnection so it is returned to the pool
    even when the surrounding task is being cancelled.

    A plain ``await closeable.close()`` in a ``finally`` is itself cancellable:
    when a request/round task is cancelled mid-stream (client disconnect or
    explicit stop), the cancellation interrupts the close before the connection
    checks back in, orphaning it. The pool then hard-terminates that connection
    later from a GC finalizer ("The garbage collector is trying to clean up
    non-checked-in connection ..."). Shielding the close lets it run to
    completion regardless, so the connection is always returned to the pool.
    """
    try:
        await asyncio.shield(closeable.close())
    except asyncio.CancelledError:
        # Our awaiter was cancelled, but the shielded close() keeps running to
        # completion, so the connection still checks back in. Re-raise so the
        # cancellation propagates as usual.
        raise
    except Exception:  # noqa: BLE001
        logger.warning("Error closing %r", closeable, exc_info=True)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """``AsyncSessionLocal()`` as a context manager whose final close is
    cancellation-safe (see :func:`aclose_quietly`). Use this instead of
    ``async with AsyncSessionLocal()`` on paths that can be cancelled."""
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await aclose_quietly(session)


class Base(DeclarativeBase):
    pass
