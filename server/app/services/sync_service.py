"""
Sync service — orchestrates Git pull + document parsing + DB import.

Supports two sync modes:
- full: delete all documents & slices, re-import everything
- incremental: only process added/modified/deleted files based on content hash

Concurrency: one sync job per knowledge base (PostgreSQL advisory lock).
"""
import asyncio
import hashlib
import logging
import os
import tempfile
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.db import session as db_session
from app.libs.git_sync.provider import GitSyncService
from app.libs.doc_parser.parser import (
    parse_document,
    discover_markdown_files,
    ParsedDocument,
)
from app.libs.doc_parser.schema_loader import (
    load_schema,
    extract_schema_fields,
    extract_schema_definitions,
    get_field_type_map,
)
from app.libs.doc_parser.nav_loader import load_nav_config
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.slice_repository import SliceRepository
from app.repositories.sync_log_repository import SyncLogRepository

logger = logging.getLogger(__name__)

_DOC_TITLE_MAX = 256
_DOC_FILE_PATH_MAX = 512
_DOC_SOURCE_URL_MAX = 1024

_EMBED_MAX_CHARS_PER_TEXT = 8000
# Advisory-lock namespace — keep distinct from conversation round locks (key2 = round_number).
_KB_SYNC_LOCK_KEY2 = 900_001
_background_sync_tasks: set[asyncio.Task] = set()


class SyncCancelledError(Exception):
    """Raised when a sync job is stopped by the user."""


@dataclass
class _SyncJobHandle:
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None


_active_sync_jobs: dict[int, _SyncJobHandle] = {}


def _register_sync_job(sync_log_id: int, task: asyncio.Task) -> None:
    _active_sync_jobs[sync_log_id] = _SyncJobHandle(task=task)


def _unregister_sync_job(sync_log_id: int) -> None:
    _active_sync_jobs.pop(sync_log_id, None)


def _request_cancel_sync(sync_log_id: int) -> bool:
    handle = _active_sync_jobs.get(sync_log_id)
    if not handle:
        return False
    handle.cancel_event.set()
    if handle.task and not handle.task.done():
        handle.task.cancel()
    return True


def _ensure_not_cancelled(sync_log_id: int | None) -> None:
    if sync_log_id is None:
        return
    handle = _active_sync_jobs.get(sync_log_id)
    if handle and handle.cancel_event.is_set():
        raise SyncCancelledError("Sync cancelled by user")


class SyncProgressReporter:
    """Persist live sync progress into ``sync_logs.details`` for the UI."""

    def __init__(self, db: AsyncSession, sync_log_id: int):
        self._db = db
        self._sync_log_id = sync_log_id
        self.sync_mode = "unknown"
        self.schema_changed = False
        self._files: list[dict] = []

    def append_file(self, entry: dict) -> None:
        self._files.append(entry)

    async def publish(self, **fields: object) -> None:
        progress = {
            key: value
            for key, value in fields.items()
            if key not in {"success_count", "error_count"}
        }
        progress["updated_at"] = datetime.utcnow().isoformat() + "Z"
        if "message" not in progress:
            phase = progress.get("phase")
            if phase == "import":
                fi, ft = progress.get("file_index"), progress.get("file_total")
                if fi is not None and ft:
                    progress["message"] = f"正在导入 {fi}/{ft}"
            elif phase == "embedding":
                eb, et = progress.get("embedding_batch"), progress.get("embedding_batch_total")
                if eb is not None and et:
                    progress["message"] = f"向量化 {eb}/{et}"
            elif phase == "delete":
                fi, ft = progress.get("file_index"), progress.get("file_total")
                if fi is not None and ft:
                    progress["message"] = f"正在删除 {fi}/{ft}"
        progress["percent"] = _calc_sync_progress_percent(progress)

        update: dict = {
            "details": {
                "sync_mode": self.sync_mode,
                "schema_changed": self.schema_changed,
                "progress": progress,
                "files": self._files,
            },
        }
        if "success_count" in fields:
            update["success_count"] = fields["success_count"]
        if "error_count" in fields:
            update["error_count"] = fields["error_count"]
        if "file_total" in fields:
            update["total_files"] = fields["file_total"]

        # Use a separate DB session so progress commits never interfere with the
        # long-running sync transaction (especially inside begin_nested()).
        from app.db.session import AsyncSessionLocal

        try:
            async with AsyncSessionLocal() as progress_db:
                log_row = await SyncLogRepository.get_by_id(
                    progress_db, self._sync_log_id,
                )
                if not log_row:
                    return
                await SyncLogRepository.update(progress_db, log_row, update)
                await progress_db.commit()
        except Exception as exc:
            logger.warning(
                "Failed to publish sync progress for log %s: %s",
                self._sync_log_id,
                exc,
            )
            return

        phase = progress.get("phase")
        file_index = progress.get("file_index")
        file_total = progress.get("file_total")
        if phase == "embedding":
            logger.info(
                "Sync progress kb_log=%s: %s file=%s/%s batch=%s/%s",
                self._sync_log_id,
                progress.get("message"),
                file_index,
                file_total,
                progress.get("embedding_batch"),
                progress.get("embedding_batch_total"),
            )
        elif phase == "import" and file_index is not None and file_total and int(file_index) % 10 == 0:
            logger.info(
                "Sync progress kb_log=%s: %s (%s ok, %s err)",
                self._sync_log_id,
                progress.get("message"),
                fields.get("success_count", 0),
                fields.get("error_count", 0),
            )


def _kb_sync_lock_keys(kb_id: int) -> dict[str, int]:
    return {"k1": int(kb_id), "k2": _KB_SYNC_LOCK_KEY2}


async def _release_kb_sync_lock(conn, kb_id: int) -> None:
    """Release session advisory lock; best-effort if the connection is dying."""
    keys = _kb_sync_lock_keys(kb_id)
    try:
        await conn.execute(
            text("SELECT pg_advisory_unlock(:k1, :k2)"),
            keys,
        )
    except Exception as exc:  # noqa: BLE001
        # Do not call pg_advisory_unlock_all() — the same session may hold
        # unrelated advisory locks (e.g. conversation round locks).
        logger.warning(
            "Failed to release KB sync advisory lock kb_id=%s: %s; "
            "caller should invalidate the connection",
            kb_id, exc,
        )


async def _invalidate_db_connection(db: AsyncSession) -> None:
    """Drop pooled connection after sync so leaked advisory locks cannot linger."""
    try:
        conn = await db.connection()
        await conn.invalidate()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to invalidate DB connection after sync: %s", exc)


async def _probe_kb_sync_lock(db: AsyncSession, kb_id: int) -> bool:
    """Return True when no other session holds this KB's sync advisory lock."""
    conn = await db.connection()
    acquired = bool((await conn.execute(
        text("SELECT pg_try_advisory_lock(:k1, :k2)"),
        _kb_sync_lock_keys(kb_id),
    )).scalar())
    if acquired:
        await _release_kb_sync_lock(conn, kb_id)
    return acquired


async def _clear_orphaned_kb_sync_lock(db: AsyncSession, kb_id: int) -> int:
    """Terminate stale backends still holding this KB's sync lock.

    A real sync must have a ``running`` sync log. Callers only reach this helper
    after that source of truth says no job is running, so an old lock holder is
    treated as orphaned even if PostgreSQL reports it as non-idle.
    """
    result = await db.execute(
        text("""
            SELECT l.pid
            FROM pg_locks l
            JOIN pg_stat_activity a ON a.pid = l.pid
            WHERE l.locktype = 'advisory'
              AND l.database = (
                  SELECT oid FROM pg_database WHERE datname = current_database()
              )
              AND l.classid = :k1
              AND l.objid = :k2
              AND a.pid <> pg_backend_pid()
              AND now() - COALESCE(a.state_change, a.xact_start, a.backend_start)
                  > interval '2 minutes'
        """),
        _kb_sync_lock_keys(kb_id),
    )
    pids = [int(row[0]) for row in result]
    for pid in pids:
        await db.execute(
            text("SELECT pg_terminate_backend(:pid)"),
            {"pid": pid},
        )
    if pids:
        logger.warning(
            "Cleared orphaned KB sync advisory lock kb_id=%s pids=%s",
            kb_id, pids,
        )
    return len(pids)


async def _ensure_kb_sync_available(db: AsyncSession, kb_id: int) -> None:
    """Raise ConflictError when a real sync holds the lock; recover stale pool locks."""
    if await _probe_kb_sync_lock(db, kb_id):
        return
    if await SyncLogRepository.has_running(db, kb_id):
        raise ConflictError("Knowledge base sync is already in progress")
    cleared = await _clear_orphaned_kb_sync_lock(db, kb_id)
    retry_count = 5 if cleared else 1
    for attempt in range(retry_count):
        if await _probe_kb_sync_lock(db, kb_id):
            return
        if attempt < retry_count - 1:
            await asyncio.sleep(0.2)
    raise ConflictError("Knowledge base sync is already in progress")


async def _release_lock_on_conn(conn, kb_id: int) -> None:
    """Release the sync advisory lock on its dedicated connection.

    With a dedicated connection (never recycled by the session's commits) the
    unlock reliably succeeds. If it somehow fails we invalidate the connection
    so PostgreSQL physically drops it — and the lock with it — instead of
    returning it to the pool with the lock still held.
    """
    try:
        await conn.execute(
            text("SELECT pg_advisory_unlock(:k1, :k2)"),
            _kb_sync_lock_keys(kb_id),
        )
        await conn.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to release KB sync advisory lock kb_id=%s: %s; "
            "invalidating connection",
            kb_id, exc,
        )
        try:
            await conn.invalidate()
        except Exception:  # noqa: BLE001
            pass


@asynccontextmanager
async def _kb_sync_lock(db: AsyncSession, kb_id: int):
    """One active sync per knowledge base; 409 if another job holds the lock.

    The advisory lock is held on a DEDICATED connection, not the session's: a
    sync commits many times, and each commit returns the session's connection
    to the pool, which would orphan this session-level advisory lock onto a
    pooled connection (it survives rollback/return-to-pool) and leak it. A
    connection we own for the whole job is never recycled, so we always release.
    Uses the dedicated lock pool so long-held sync locks don't starve the main
    request pool.
    """
    conn = await db_session.lock_engine.connect()
    try:
        acquired = bool((await conn.execute(
            text("SELECT pg_try_advisory_lock(:k1, :k2)"),
            _kb_sync_lock_keys(kb_id),
        )).scalar())
        await conn.commit()
        if not acquired:
            raise ConflictError("Knowledge base sync is already in progress")
        try:
            yield
        finally:
            await _release_lock_on_conn(conn, kb_id)
    finally:
        await conn.close()


@asynccontextmanager
async def _kb_sync_lock_with_recovery(
    db: AsyncSession, kb_id: int, sync_log_id: int,
):
    """Acquire KB sync lock; on acquire failure clear pool orphans and retry once.

    Like :func:`_kb_sync_lock`, the lock is held on a dedicated connection so it
    can never leak into the pool.
    """
    last_exc = ConflictError("Knowledge base sync is already in progress")
    for attempt in range(2):
        conn = await db_session.lock_engine.connect()
        acquired = False
        try:
            acquired = bool((await conn.execute(
                text("SELECT pg_try_advisory_lock(:k1, :k2)"),
                _kb_sync_lock_keys(kb_id),
            )).scalar())
            await conn.commit()
            if acquired:
                try:
                    yield
                finally:
                    await _release_lock_on_conn(conn, kb_id)
                return
        finally:
            await conn.close()
        if attempt == 0:
            running = await SyncLogRepository.get_latest_running(db, kb_id)
            if running is not None and running.id != sync_log_id:
                raise last_exc
            await _clear_orphaned_kb_sync_lock(db, kb_id)
            continue
    raise last_exc


async def _run_under_kb_sync_lock(
    db: AsyncSession,
    kb_id: int,
    sync_log_id: int,
    job: Callable[[], Awaitable[None]],
) -> None:
    """Run sync work under the KB lock (job errors are not retried)."""
    async with _kb_sync_lock_with_recovery(db, kb_id, sync_log_id):
        await job()


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------

def _compute_schema_hash(repo_path: str) -> str:
    """SHA-256 of concatenated schema file contents."""
    parts: list[str] = []
    for filename in ("doc-meta.yaml", "slice-meta.yaml"):
        path = os.path.join(repo_path, "schema", filename)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                parts.append(f"{filename}:{f.read()}")
        else:
            parts.append(f"{filename}:")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _compute_content_hash(content: str) -> str:
    """SHA-256 of raw markdown content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _calc_sync_progress_percent(progress: dict) -> int:
    file_index = int(progress.get("file_index") or 0)
    file_total = int(progress.get("file_total") or 0)
    if file_total <= 0:
        return 0
    phase = progress.get("phase")
    if phase == "embedding":
        batch = int(progress.get("embedding_batch") or 0)
        batch_total = int(progress.get("embedding_batch_total") or 1)
        return min(100, int(((file_index - 1) + batch / batch_total) / file_total * 100))
    if phase in ("import", "delete"):
        return min(100, int(file_index / file_total * 100))
    return 0


def _classify_files(
    discovered: dict[str, str],
    existing: dict[str, tuple[int, str | None]],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """
    Classify files into (added, modified, unchanged, deleted).

    Args:
        discovered: {file_path: content_hash} from filesystem
        existing: {file_path: (doc_id, content_hash)} from DB
    """
    disc_set = set(discovered)
    exist_set = set(existing)

    added = sorted(disc_set - exist_set)
    deleted = sorted(exist_set - disc_set)
    common = disc_set & exist_set

    modified = sorted(
        fp for fp in common
        if existing[fp][1] is None or discovered[fp] != existing[fp][1]
    )
    unchanged = sorted(
        fp for fp in common
        if existing[fp][1] is not None and discovered[fp] == existing[fp][1]
    )
    return added, modified, unchanged, deleted


# ---------------------------------------------------------------------------
# SyncService
# ---------------------------------------------------------------------------

class SyncService:

    @staticmethod
    async def start_sync(
        db: AsyncSession, kb_id: int, *, force_full: bool = False,
    ) -> dict:
        """Create a sync log and run the job in the background; return immediately."""
        kb = await KnowledgeBaseRepository.get_by_id(db, kb_id)
        if not kb or kb.status == "deleted":
            raise NotFoundError("Knowledge base not found")

        await _ensure_kb_sync_available(db, kb_id)

        if await SyncLogRepository.has_running(db, kb_id):
            await SyncLogRepository.cancel_stale_running(
                db, kb_id, reason="superseded by new sync job",
            )

        sync_log = await SyncLogRepository.create(db, {
            "knowledge_base_id": kb.id,
            "tenant_id": kb.tenant_id,
            "status": "running",
        })
        await db.commit()
        sync_log_id = sync_log.id

        task = asyncio.create_task(
            SyncService._run_sync_job_background(kb_id, sync_log_id, force_full),
        )
        _register_sync_job(sync_log_id, task)
        _background_sync_tasks.add(task)

        def _on_task_done(done_task: asyncio.Task) -> None:
            _background_sync_tasks.discard(done_task)
            _unregister_sync_job(sync_log_id)

        task.add_done_callback(_on_task_done)

        return {
            "sync_log_id": sync_log_id,
            "status": "running",
            "sync_mode": "full" if force_full else "auto",
        }

    @staticmethod
    async def cancel_sync(
        db: AsyncSession,
        kb_id: int,
        *,
        sync_log_id: int | None = None,
    ) -> dict:
        """Stop a running sync job, or clear an orphaned ``running`` log."""
        kb = await KnowledgeBaseRepository.get_by_id(db, kb_id)
        if not kb or kb.status == "deleted":
            raise NotFoundError("Knowledge base not found")

        if sync_log_id is not None:
            log_row = await SyncLogRepository.get_by_id(db, sync_log_id)
            if not log_row or log_row.knowledge_base_id != kb_id:
                raise NotFoundError("Sync log not found")
        else:
            log_row = await SyncLogRepository.get_latest_running(db, kb_id)
            if not log_row:
                raise NotFoundError("No running sync job")

        if log_row.status != "running":
            raise ConflictError("Sync is not running")

        target_log_id = log_row.id
        _request_cancel_sync(target_log_id)
        await SyncService._finalize_cancelled_sync(
            db, target_log_id, kb_id, reason="cancelled by user",
        )
        return {"sync_log_id": target_log_id, "status": "cancelled"}

    @staticmethod
    async def sync_and_parse(
        db: AsyncSession, kb_id: int, *, force_full: bool = False,
    ) -> dict:
        """Blocking sync — kept for tests and internal callers."""
        kb = await KnowledgeBaseRepository.get_by_id(db, kb_id)
        if not kb or kb.status == "deleted":
            raise NotFoundError("Knowledge base not found")

        async with _kb_sync_lock(db, kb_id):
            await SyncLogRepository.cancel_stale_running(
                db, kb_id, reason="superseded by new sync job",
            )
            return await SyncService._run_sync_job(
                db, kb, kb_id, force_full=force_full,
            )

    @staticmethod
    async def _run_sync_job_background(
        kb_id: int, sync_log_id: int, force_full: bool,
    ) -> None:
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            try:
                async def _job() -> None:
                    kb = await KnowledgeBaseRepository.get_by_id(db, kb_id)
                    if not kb or kb.status == "deleted":
                        raise NotFoundError("Knowledge base not found")
                    await SyncService._run_sync_job(
                        db,
                        kb,
                        kb_id,
                        force_full=force_full,
                        sync_log_id=sync_log_id,
                    )

                await _run_under_kb_sync_lock(db, kb_id, sync_log_id, _job)
            except SyncCancelledError:
                logger.info(
                    "Background sync kb_id=%s log=%s cancelled",
                    kb_id, sync_log_id,
                )
                await SyncService._finalize_cancelled_sync(
                    db, sync_log_id, kb_id, reason="cancelled by user",
                )
            except asyncio.CancelledError:
                logger.info(
                    "Background sync task cancelled kb_id=%s log=%s",
                    kb_id, sync_log_id,
                )
                await SyncService._finalize_cancelled_sync(
                    db, sync_log_id, kb_id, reason="cancelled by user",
                )
                raise
            except ConflictError as exc:
                logger.warning(
                    "Background sync kb_id=%s log=%s lost lock race: %s",
                    kb_id, sync_log_id, exc,
                )
                await SyncService._finalize_failed_sync(db, sync_log_id, exc)
            except Exception as exc:
                logger.exception(
                    "Background sync wrapper failed for KB %s log %s",
                    kb_id, sync_log_id,
                )
                await SyncService._finalize_failed_sync(db, sync_log_id, exc)
            finally:
                await _invalidate_db_connection(db)

    @staticmethod
    async def _run_sync_job(
        db: AsyncSession,
        kb,
        kb_id: int,
        *,
        force_full: bool,
        sync_log_id: int | None = None,
    ) -> dict:
        if sync_log_id is None:
            sync_log = await SyncLogRepository.create(db, {
                "knowledge_base_id": kb.id,
                "tenant_id": kb.tenant_id,
                "status": "running",
            })
            await db.commit()
            sync_log_id = sync_log.id
        reporter = SyncProgressReporter(db, sync_log_id)

        work_dir = None
        try:
            _ensure_not_cancelled(sync_log_id)
            await reporter.publish(phase="git_pull", message="正在拉取 Git 仓库…")
            work_dir = tempfile.mkdtemp(prefix=f"kb_{kb.id}_")
            repo_path = GitSyncService.sync_repo(
                git_url=kb.git_url,
                branch=kb.git_branch,
                auth_token=kb.auth_token,
                work_dir=work_dir,
            )

            doc_schema_data = load_schema(repo_path, "doc-meta.yaml")
            slice_schema_data = load_schema(repo_path, "slice-meta.yaml")
            doc_field_types = get_field_type_map(doc_schema_data)
            slice_field_types = get_field_type_map(slice_schema_data)

            current_schema_hash = _compute_schema_hash(repo_path)
            current_schema_fields = extract_schema_fields(repo_path)
            current_schema_defs = extract_schema_definitions(repo_path)
            stored_schema_hash = kb.schema_hash
            schema_changed = (
                stored_schema_hash is None
                or current_schema_hash != stored_schema_hash
            )
            sync_mode = "full" if (force_full or schema_changed) else "incremental"
            reporter.sync_mode = sync_mode
            reporter.schema_changed = schema_changed

            md_files = discover_markdown_files(repo_path)
            total_files = len(md_files)
            await reporter.publish(
                phase="discovered",
                file_total=total_files,
                file_index=0,
                success_count=0,
                error_count=0,
                message=f"发现 {total_files} 个文件，准备同步",
            )
            logger.info(
                "Sync kb_id=%s: mode=%s schema_changed=%s discovered %d file(s)",
                kb.id, sync_mode, schema_changed, total_files,
            )

            if sync_mode == "full":
                result = await SyncService._sync_full(
                    db, kb, repo_path, md_files, current_schema_hash,
                    doc_field_types=doc_field_types,
                    slice_field_types=slice_field_types,
                    reporter=reporter,
                    sync_log_id=sync_log_id,
                )
            else:
                result = await SyncService._sync_incremental(
                    db, kb, repo_path, md_files, current_schema_hash,
                    doc_field_types=doc_field_types,
                    slice_field_types=slice_field_types,
                    reporter=reporter,
                    sync_log_id=sync_log_id,
                )

            details = result["details"]
            success_count = result["success_count"]
            error_count = result["error_count"]
            total_doc_count = result["total_doc_count"]

            nav_config = load_nav_config(repo_path)

            kb_row = await KnowledgeBaseRepository.get_by_id(db, kb_id)
            if kb_row:
                kb_row.last_synced_at = datetime.utcnow()
                kb_row.document_count = total_doc_count
                kb_row.schema_hash = current_schema_hash
                kb_row.schema_fields = {
                    **current_schema_fields,
                    **current_schema_defs,
                }
                kb_row.nav_config = nav_config

            log_row = await SyncLogRepository.get_by_id(db, sync_log_id)
            if not log_row:
                raise RuntimeError(f"sync_log id={sync_log_id} missing after sync")
            if log_row.status != "running":
                logger.info(
                    "Sync kb_id=%s log=%s no longer running (status=%s); skip finalize",
                    kb.id, sync_log_id, log_row.status,
                )
                return {
                    "sync_log_id": sync_log_id,
                    "status": log_row.status,
                    "sync_mode": sync_mode,
                    "total_files": total_files,
                    "success_count": success_count,
                    "error_count": error_count,
                    "total_documents": total_doc_count,
                    "total_slices": result.get("total_slice_count", 0),
                }

            job_status = "success" if error_count == 0 else "partial_success"

            sync_details: dict = {
                "sync_mode": sync_mode,
                "schema_changed": schema_changed,
                "added_count": result.get("added_count", 0),
                "modified_count": result.get("modified_count", 0),
                "unchanged_count": result.get("unchanged_count", 0),
                "deleted_count": result.get("deleted_count", 0),
                "files": details,
            }

            await SyncLogRepository.update(db, log_row, {
                "status": job_status,
                "finished_at": datetime.utcnow(),
                "total_files": total_files,
                "success_count": success_count,
                "error_count": error_count,
                "details": sync_details,
            })

            await db.commit()

            logger.info(
                "Sync kb_id=%s finished: mode=%s status=%s files=%d ok=%d err=%d docs=%d",
                kb.id, sync_mode, job_status, total_files,
                success_count, error_count, total_doc_count,
            )

            return {
                "sync_log_id": sync_log_id,
                "status": job_status,
                "sync_mode": sync_mode,
                "total_files": total_files,
                "success_count": success_count,
                "error_count": error_count,
                "total_documents": total_doc_count,
                "total_slices": result.get("total_slice_count", 0),
            }

        except SyncCancelledError:
            logger.info("Sync cancelled for KB %s log %s", kb_id, sync_log_id)
            await SyncService._finalize_cancelled_sync(
                db, sync_log_id, kb_id, reason="cancelled by user",
            )
            return {
                "sync_log_id": sync_log_id,
                "status": "cancelled",
                "error": "cancelled by user",
                "sync_mode": "unknown",
                "total_files": 0,
                "success_count": 0,
                "error_count": 0,
                "total_documents": 0,
                "total_slices": 0,
            }
        except Exception as exc:
            logger.exception("Sync failed for KB %s", kb_id)
            await SyncService._finalize_failed_sync(db, sync_log_id, exc)
            return {
                "sync_log_id": sync_log_id,
                "status": "failed",
                "error": str(exc),
                "sync_mode": "unknown",
                "total_files": 0,
                "success_count": 0,
                "error_count": 0,
                "total_documents": 0,
                "total_slices": 0,
            }

        finally:
            if work_dir:
                GitSyncService.cleanup(work_dir)

    # ------------------------------------------------------------------
    # Full mode — same as original: delete all then re-import
    # ------------------------------------------------------------------

    @staticmethod
    async def _sync_full(
        db: AsyncSession,
        kb,
        repo_path: str,
        md_files: list[str],
        schema_hash: str,
        *,
        doc_field_types: dict[str, str] | None = None,
        slice_field_types: dict[str, str] | None = None,
        reporter: SyncProgressReporter | None = None,
        sync_log_id: int | None = None,
    ) -> dict:
        deleted_slices = await SliceRepository.delete_by_kb_id(db, kb.id)
        deleted_docs = await DocumentRepository.delete_by_kb_id(db, kb.id)
        await db.commit()
        logger.info(
            "Sync kb_id=%s [full]: cleared prior data (documents=%s slices=%s)",
            kb.id, deleted_docs, deleted_slices,
        )

        details: list[dict] = []
        success_count = 0
        error_count = 0
        total_doc_count = 0
        total_slice_count = 0
        total_files = len(md_files)

        for idx, rel_path in enumerate(md_files, start=1):
            _ensure_not_cancelled(sync_log_id)
            if reporter:
                await reporter.publish(
                    phase="import",
                    file_index=idx - 1,
                    file_total=total_files,
                    current_file=rel_path,
                    success_count=success_count,
                    error_count=error_count,
                    message=f"正在导入 {idx}/{total_files}",
                )
            full_path = os.path.join(repo_path, rel_path)
            try:
                async with db.begin_nested():
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    content_hash = _compute_content_hash(content)
                    parsed = parse_document(
                        rel_path,
                        content,
                        doc_field_types=doc_field_types,
                        slice_field_types=slice_field_types,
                    )
                    doc_record = await _save_document(
                        db, kb, parsed, content_hash=content_hash,
                    )
                    slice_records = await _save_slices(
                        db, kb, doc_record, parsed,
                        reporter=reporter,
                        file_index=idx,
                        file_total=total_files,
                        current_file=rel_path,
                        sync_log_id=sync_log_id,
                    )

                    total_doc_count += 1
                    total_slice_count += len(slice_records)
                    success_count += 1
                    file_entry = {
                        "file": rel_path,
                        "status": "added",
                        "slice_count": len(slice_records),
                    }
                    details.append(file_entry)
                    if reporter:
                        reporter.append_file(file_entry)
                    logger.info(
                        "Sync kb_id=%s [full] %d/%d ok file=%s slices=%d",
                        kb.id, idx, total_files, rel_path, len(slice_records),
                    )
                await db.commit()
                if reporter:
                    await reporter.publish(
                        phase="import",
                        file_index=idx,
                        file_total=total_files,
                        current_file=rel_path,
                        success_count=success_count,
                        error_count=error_count,
                    )
            except SyncCancelledError:
                raise
            except Exception as exc:
                error_count += 1
                err_entry = {"file": rel_path, "status": "error", "error": str(exc)}
                details.append(err_entry)
                if reporter:
                    reporter.append_file(err_entry)
                    await reporter.publish(
                        phase="import",
                        file_index=idx,
                        file_total=total_files,
                        current_file=rel_path,
                        success_count=success_count,
                        error_count=error_count,
                    )
                logger.error(
                    "Sync kb_id=%s [full] %d/%d FAILED file=%s: %s",
                    kb.id, idx, total_files, rel_path, exc,
                )
                try:
                    await db.rollback()
                except Exception:
                    pass

        return {
            "details": details,
            "success_count": success_count,
            "error_count": error_count,
            "total_doc_count": total_doc_count,
            "total_slice_count": total_slice_count,
            "added_count": success_count,
            "modified_count": 0,
            "unchanged_count": 0,
            "deleted_count": 0,
        }

    # ------------------------------------------------------------------
    # Incremental mode — only process changed files
    # ------------------------------------------------------------------

    @staticmethod
    async def _sync_incremental(
        db: AsyncSession,
        kb,
        repo_path: str,
        md_files: list[str],
        schema_hash: str,
        *,
        doc_field_types: dict[str, str] | None = None,
        slice_field_types: dict[str, str] | None = None,
        reporter: SyncProgressReporter | None = None,
        sync_log_id: int | None = None,
    ) -> dict:
        # Build discovered hash map
        discovered: dict[str, str] = {}
        file_contents: dict[str, str] = {}
        for rel_path in md_files:
            full_path = os.path.join(repo_path, rel_path)
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            discovered[rel_path] = _compute_content_hash(content)
            file_contents[rel_path] = content

        existing = await DocumentRepository.get_hash_map_by_kb(db, kb.id)
        added, modified, unchanged, deleted = _classify_files(discovered, existing)

        logger.info(
            "Sync kb_id=%s [incremental]: added=%d modified=%d unchanged=%d deleted=%d",
            kb.id, len(added), len(modified), len(unchanged), len(deleted),
        )

        details: list[dict] = []
        success_count = 0
        error_count = 0
        total_slice_count = 0
        total_work = len(added) + len(modified) + len(deleted)
        work_index = 0

        async def _publish_work(rel_path: str, *, phase: str = "import") -> None:
            if not reporter:
                return
            await reporter.publish(
                phase=phase,
                file_index=work_index,
                file_total=total_work,
                current_file=rel_path,
                success_count=success_count,
                error_count=error_count,
            )

        # Process ADDED files
        for rel_path in added:
            _ensure_not_cancelled(sync_log_id)
            work_index += 1
            await _publish_work(rel_path)
            try:
                async with db.begin_nested():
                    parsed = parse_document(
                        rel_path,
                        file_contents[rel_path],
                        doc_field_types=doc_field_types,
                        slice_field_types=slice_field_types,
                    )
                    doc_record = await _save_document(
                        db, kb, parsed, content_hash=discovered[rel_path],
                    )
                    slices = await _save_slices(
                        db, kb, doc_record, parsed,
                        reporter=reporter,
                        file_index=work_index,
                        file_total=total_work,
                        current_file=rel_path,
                        sync_log_id=sync_log_id,
                    )
                    total_slice_count += len(slices)
                    success_count += 1
                    file_entry = {
                        "file": rel_path, "status": "added",
                        "slice_count": len(slices),
                    }
                    details.append(file_entry)
                    if reporter:
                        reporter.append_file(file_entry)
                    logger.info(
                        "Sync kb_id=%s [incr] added file=%s slices=%d",
                        kb.id, rel_path, len(slices),
                    )
                await db.commit()
                await _publish_work(rel_path)
            except SyncCancelledError:
                raise
            except Exception as exc:
                error_count += 1
                err_entry = {"file": rel_path, "status": "error", "error": str(exc)}
                details.append(err_entry)
                if reporter:
                    reporter.append_file(err_entry)
                    await _publish_work(rel_path)
                logger.error("Sync kb_id=%s [incr] add FAILED file=%s: %s", kb.id, rel_path, exc)
                try:
                    await db.rollback()
                except Exception:
                    pass

        # Process MODIFIED files
        for rel_path in modified:
            _ensure_not_cancelled(sync_log_id)
            work_index += 1
            await _publish_work(rel_path)
            doc_id = existing[rel_path][0]
            try:
                async with db.begin_nested():
                    await SliceRepository.delete_by_document_id(db, doc_id)

                    doc = await DocumentRepository.get_by_id(db, doc_id)
                    parsed = parse_document(
                        rel_path,
                        file_contents[rel_path],
                        doc_field_types=doc_field_types,
                        slice_field_types=slice_field_types,
                    )

                    await DocumentRepository.update_document(db, doc, {
                        "title": _clip_str(parsed.title, _DOC_TITLE_MAX),
                        "description": parsed.description,
                        "source_url": _clip_str(parsed.source_url, _DOC_SOURCE_URL_MAX),
                        "markdown_content": parsed.markdown_content,
                        "doc_meta": parsed.doc_meta if parsed.doc_meta else None,
                        "toc": parsed.toc if parsed.toc else None,
                        "slice_count": len(parsed.slices),
                        "content_hash": discovered[rel_path],
                    })

                    slices = await _save_slices(
                        db, kb, doc, parsed,
                        reporter=reporter,
                        file_index=work_index,
                        file_total=total_work,
                        current_file=rel_path,
                        sync_log_id=sync_log_id,
                    )
                    total_slice_count += len(slices)
                    success_count += 1
                    file_entry = {
                        "file": rel_path, "status": "modified",
                        "slice_count": len(slices),
                    }
                    details.append(file_entry)
                    if reporter:
                        reporter.append_file(file_entry)
                    logger.info(
                        "Sync kb_id=%s [incr] modified file=%s slices=%d",
                        kb.id, rel_path, len(slices),
                    )
                await db.commit()
                await _publish_work(rel_path)
            except SyncCancelledError:
                raise
            except Exception as exc:
                error_count += 1
                err_entry = {"file": rel_path, "status": "error", "error": str(exc)}
                details.append(err_entry)
                if reporter:
                    reporter.append_file(err_entry)
                    await _publish_work(rel_path)
                logger.error("Sync kb_id=%s [incr] modify FAILED file=%s: %s", kb.id, rel_path, exc)
                try:
                    await db.rollback()
                except Exception:
                    pass

        # Process DELETED files
        for rel_path in deleted:
            _ensure_not_cancelled(sync_log_id)
            work_index += 1
            await _publish_work(rel_path, phase="delete")
            doc_id = existing[rel_path][0]
            try:
                async with db.begin_nested():
                    await SliceRepository.delete_by_document_id(db, doc_id)
                    await DocumentRepository.delete_by_id(db, doc_id)
                    success_count += 1
                    file_entry = {"file": rel_path, "status": "deleted"}
                    details.append(file_entry)
                    if reporter:
                        reporter.append_file(file_entry)
                    logger.info("Sync kb_id=%s [incr] deleted file=%s", kb.id, rel_path)
                await db.commit()
                await _publish_work(rel_path, phase="delete")
            except SyncCancelledError:
                raise
            except Exception as exc:
                error_count += 1
                err_entry = {"file": rel_path, "status": "error", "error": str(exc)}
                details.append(err_entry)
                if reporter:
                    reporter.append_file(err_entry)
                    await _publish_work(rel_path, phase="delete")
                logger.error("Sync kb_id=%s [incr] delete FAILED file=%s: %s", kb.id, rel_path, exc)
                try:
                    await db.rollback()
                except Exception:
                    pass

        # Unchanged files logged at debug
        for rel_path in unchanged:
            details.append({"file": rel_path, "status": "unchanged"})

        # Total remaining docs = unchanged + successfully added + successfully modified
        total_doc_count = (
            len(unchanged)
            + len([d for d in details if d["status"] == "added"])
            + len([d for d in details if d["status"] == "modified"])
        )

        return {
            "details": details,
            "success_count": success_count,
            "error_count": error_count,
            "total_doc_count": total_doc_count,
            "total_slice_count": total_slice_count,
            "added_count": len(added),
            "modified_count": len(modified),
            "unchanged_count": len(unchanged),
            "deleted_count": len(deleted),
        }

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    @staticmethod
    async def _finalize_cancelled_sync(
        db: AsyncSession,
        sync_log_id: int,
        kb_id: int,
        *,
        reason: str = "cancelled by user",
    ) -> None:
        """Mark sync log cancelled; safe to call multiple times."""
        try:
            await db.rollback()
        except Exception as rb_exc:
            logger.warning("Rollback after sync cancel: %s", rb_exc)

        try:
            log_row = await SyncLogRepository.get_by_id(db, sync_log_id)
            if not log_row or log_row.status != "running":
                return

            existing_details = (
                log_row.details if isinstance(log_row.details, dict) else {}
            )
            progress = existing_details.get("progress")
            new_details = {
                **existing_details,
                "cancelled": True,
                "error": reason,
            }
            if isinstance(progress, dict):
                new_details["progress"] = {
                    **progress,
                    "message": "已停止",
                }

            await SyncLogRepository.update(db, log_row, {
                "status": "cancelled",
                "finished_at": datetime.utcnow(),
                "details": new_details,
            })

            kb_row = await KnowledgeBaseRepository.get_by_id(db, kb_id)
            if kb_row:
                kb_row.document_count = await DocumentRepository.count_by_kb(
                    db, kb_id,
                )

            await db.commit()
        except Exception as fin_exc:
            logger.error(
                "Could not persist cancelled sync log %s: %s",
                sync_log_id,
                fin_exc,
            )
            try:
                await db.rollback()
            except Exception:
                pass
        finally:
            _unregister_sync_job(sync_log_id)

    @staticmethod
    async def _finalize_failed_sync(
        db: AsyncSession, sync_log_id: int, exc: Exception
    ) -> None:
        """Mark sync log failed after rollback; never raises to caller."""
        try:
            await db.rollback()
        except Exception as rb_exc:
            logger.warning("Rollback after sync failure: %s", rb_exc)

        try:
            log_row = await SyncLogRepository.get_by_id(db, sync_log_id)
            if log_row:
                await SyncLogRepository.update(db, log_row, {
                    "status": "failed",
                    "finished_at": datetime.utcnow(),
                    "details": {"sync_mode": "unknown", "error": str(exc)},
                })
                await db.commit()
        except Exception as fin_exc:
            logger.error("Could not persist failed sync log %s: %s", sync_log_id, fin_exc)
            try:
                await db.rollback()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clip_str(value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    if len(value) <= max_len:
        return value
    if max_len <= 3:
        return value[:max_len]
    return value[: max_len - 3] + "..."


async def _save_document(
    db: AsyncSession,
    kb,
    parsed: ParsedDocument,
    *,
    content_hash: str | None = None,
) -> object:
    """Save a parsed document to the documents table."""
    doc_data = {
        "knowledge_base_id": kb.id,
        "tenant_id": kb.tenant_id,
        "title": _clip_str(parsed.title, _DOC_TITLE_MAX),
        "description": parsed.description,
        "file_path": _clip_str(parsed.file_path or "", _DOC_FILE_PATH_MAX) or "unknown",
        "source_url": _clip_str(parsed.source_url, _DOC_SOURCE_URL_MAX),
        "markdown_content": parsed.markdown_content,
        "doc_meta": parsed.doc_meta if parsed.doc_meta else None,
        "toc": parsed.toc if parsed.toc else None,
        "slice_count": len(parsed.slices),
        "content_hash": content_hash,
    }
    return await DocumentRepository.create(db, doc_data)


async def _save_slices(
    db: AsyncSession,
    kb,
    doc_record,
    parsed: ParsedDocument,
    *,
    reporter: SyncProgressReporter | None = None,
    file_index: int | None = None,
    file_total: int | None = None,
    current_file: str | None = None,
    sync_log_id: int | None = None,
) -> list:
    """Save parsed slices to the slices table, then generate embeddings."""
    if not parsed.slices:
        return []

    slice_items = []
    for s in parsed.slices:
        slice_items.append({
            "document_id": doc_record.id,
            "knowledge_base_id": kb.id,
            "tenant_id": kb.tenant_id,
            "content": s.content,
            "content_for_search": s.content_for_search or s.content,
            "toc_path": s.toc_path if s.toc_path else None,
            "toc_ancestors": s.toc_ancestors,
            "slice_meta": s.slice_meta if s.slice_meta else None,
            "doc_meta": parsed.doc_meta if parsed.doc_meta else None,
            "source_url": parsed.source_url,
            "markdown_url": f"/api/v1/knowledge-bases/{kb.id}/documents/{doc_record.id}/markdown",
            "slice_order": s.slice_order,
        })

    records = await SliceRepository.create_batch(db, slice_items)

    # Embedding in its own savepoint so failures don't poison the parent transaction
    try:
        async with db.begin_nested():
            await _generate_embeddings(
                db,
                records,
                kb_id=kb.id,
                reporter=reporter,
                file_index=file_index,
                file_total=file_total,
                current_file=current_file,
                sync_log_id=sync_log_id,
            )
    except SyncCancelledError:
        raise
    except Exception as exc:
        logger.warning("Embedding generation failed (non-fatal): %s", exc)

    return records


async def _embed_batch_resilient(
    provider, texts: list[str]
) -> list[list[float]]:
    """Call embed API; on 413 split batch or truncate single oversized input."""
    if not texts:
        return []
    try:
        return await provider.embed_batch(texts)
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 413:
            raise
        if len(texts) > 1:
            mid = len(texts) // 2
            first = await _embed_batch_resilient(provider, texts[:mid])
            second = await _embed_batch_resilient(provider, texts[mid:])
            return first + second
        t = texts[0]
        cap = min(len(t), _EMBED_MAX_CHARS_PER_TEXT)
        while cap >= 256:
            try:
                return await provider.embed_batch([t[:cap]])
            except httpx.HTTPStatusError as e2:
                if e2.response.status_code != 413:
                    raise
                cap //= 2
        logger.warning("Embedding skipped for oversized slice (413 after truncation)")
        raise


async def _generate_embeddings(
    db: AsyncSession,
    slice_records: list,
    *,
    kb_id: int | None = None,
    reporter: SyncProgressReporter | None = None,
    file_index: int | None = None,
    file_total: int | None = None,
    current_file: str | None = None,
    sync_log_id: int | None = None,
) -> None:
    """Generate embedding vectors for slices and store them."""
    from app.libs.embedding.factory import create_embedding_provider
    from app.libs.knowledge_provider import has_embedding_credentials

    _ensure_not_cancelled(sync_log_id)
    if not has_embedding_credentials():
        return

    total = len(slice_records)
    if total == 0:
        return

    provider = create_embedding_provider()
    texts = [
        (r.content_for_search or r.content)[:_EMBED_MAX_CHARS_PER_TEXT]
        for r in slice_records
    ]

    batch_size = settings.EMBEDDING_BATCH_SIZE
    concurrency = settings.EMBEDDING_BATCH_CONCURRENCY
    batches: list[tuple[list[str], list]] = []
    for i in range(0, len(texts), batch_size):
        batches.append((
            texts[i:i + batch_size],
            slice_records[i:i + batch_size],
        ))

    n_batches = len(batches)
    log_prefix = f"kb_id={kb_id} " if kb_id is not None else ""
    logger.info(
        "%sembedding: %d slice(s), %d HTTP batch(es) of up to %d, concurrency=%d",
        log_prefix, total, n_batches, batch_size, concurrency,
    )

    if reporter and file_index is not None and file_total is not None:
        await reporter.publish(
            phase="embedding",
            file_index=file_index,
            file_total=file_total,
            current_file=current_file,
            slice_count=total,
            embedding_batch=0,
            embedding_batch_total=n_batches,
        )

    sem = asyncio.Semaphore(concurrency)

    async def _embed_texts(batch_texts: list[str]) -> list[list[float]]:
        async with sem:
            return await _embed_batch_resilient(provider, batch_texts)

    for group_start in range(0, n_batches, concurrency):
        _ensure_not_cancelled(sync_log_id)
        group = batches[group_start:group_start + concurrency]
        batch_nums = list(range(group_start + 1, group_start + len(group) + 1))
        try:
            vectors_group = await asyncio.gather(
                *[_embed_texts(batch_texts) for batch_texts, _ in group]
            )
            for batch_num, (_, batch_records), vectors in zip(
                batch_nums, group, vectors_group
            ):
                for record, vector in zip(batch_records, vectors):
                    record.embedding = vector
                logger.debug(
                    "%sembedding batch %d/%d, %d slice(s)",
                    log_prefix, batch_num, n_batches, len(batch_records),
                )
            await db.flush()
            if reporter and file_index is not None and file_total is not None:
                last_batch = batch_nums[-1]
                await reporter.publish(
                    phase="embedding",
                    file_index=file_index,
                    file_total=file_total,
                    current_file=current_file,
                    slice_count=total,
                    embedding_batch=last_batch,
                    embedding_batch_total=n_batches,
                )
        except SyncCancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Embedding batch group starting at %d failed: %s",
                group_start,
                exc,
            )
