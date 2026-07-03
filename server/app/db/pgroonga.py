"""Idempotent PGroonga keyword-index bootstrap, executed at startup.

Deliberately kept OUT of Alembic migrations: the pgroonga extension is absent on
vanilla dev/CI PostgreSQL, so a migration referencing it would fail and block
startup everywhere. Instead we ensure the extension + index only when the
PGroonga keyword backend is explicitly enabled (``KB_PGROONGA_ENABLED``),
idempotently (``IF NOT EXISTS``), and never crash the app if the database can't
provide it — a prominent error is logged so a misconfigured deploy is obvious
while the rest of the API keeps serving.
"""
import logging
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.repositories.search_repository import _PGROONGA_TARGET

logger = logging.getLogger(__name__)


async def ensure_pgroonga_index(db: AsyncSession) -> None:
    """Create the pgroonga extension + keyword index if enabled and missing.

    No-op unless ``KB_PGROONGA_ENABLED``. The index expression is kept in sync
    with ``_PGROONGA_TARGET`` (the single source of truth used by the query).

    NOTE: a non-concurrent ``CREATE INDEX`` takes a brief write lock while it
    builds. On a large EXISTING table prefer creating the index manually with
    ``CREATE INDEX CONCURRENTLY`` first (see docs/搜索性能与准确性优化.md); the
    ``IF NOT EXISTS`` here then no-ops. For a fresh/small table the startup build
    is negligible.
    """
    if not settings.KB_PGROONGA_ENABLED:
        return

    index_name = settings.KB_PGROONGA_INDEX_NAME
    try:
        await db.execute(text("CREATE EXTENSION IF NOT EXISTS pgroonga"))

        # Skip (and say so) when already built, so startup logs are unambiguous.
        if await db.scalar(text("SELECT to_regclass(:n)"), {"n": index_name}) is not None:
            await db.commit()
            logger.info("PGroonga keyword index %r already present; skipping build.", index_name)
            return

        # Loud "starting" log: a non-concurrent build scans every existing row and
        # blocks writes (SELECTs unaffected) until done — ~tens of seconds per 100k
        # rows. Without this, a multi-minute build on a large table looks like a hang.
        logger.warning(
            "Building PGroonga keyword index %r on slices; this scans all existing "
            "rows and BLOCKS WRITES until finished (~tens of seconds per 100k rows). "
            "On a large production table build it manually with CREATE INDEX "
            "CONCURRENTLY instead (see docs/搜索性能与准确性优化.md).",
            index_name,
        )
        started = time.perf_counter()
        await db.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {index_name} "
                f"ON slices USING pgroonga ({_PGROONGA_TARGET})"
            )
        )
        await db.commit()
        logger.info(
            "PGroonga keyword index %r built in %.2fs.",
            index_name, time.perf_counter() - started,
        )
    except Exception:
        await db.rollback()
        logger.error(
            "Failed to ensure PGroonga extension/index %r — keyword search will "
            "error while KB_PGROONGA_ENABLED is true. Verify the pgroonga "
            "extension is available on this database and the role may CREATE it "
            "(or create it manually; see docs/搜索性能与准确性优化.md).",
            index_name, exc_info=True,
        )
