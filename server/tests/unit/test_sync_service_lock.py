"""Unit tests for knowledge-base sync locking."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictError
from app.services import sync_service


@pytest.mark.asyncio
async def test_kb_sync_lock_raises_when_busy(monkeypatch):
    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=[
        MagicMock(scalar=lambda: False),
    ])
    # The lock is held on a dedicated engine connection, not the session.
    fake_engine = MagicMock()
    fake_engine.connect = AsyncMock(return_value=conn)
    monkeypatch.setattr(sync_service.db_session, "lock_engine", fake_engine)
    db = AsyncMock()

    with pytest.raises(ConflictError, match="already in progress"):
        async with sync_service._kb_sync_lock(db, kb_id=2):
            pass

    assert conn.execute.await_count == 1


@pytest.mark.asyncio
async def test_kb_sync_lock_releases_on_exit(monkeypatch):
    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=[
        MagicMock(scalar=lambda: True),
        MagicMock(),
    ])
    fake_engine = MagicMock()
    fake_engine.connect = AsyncMock(return_value=conn)
    monkeypatch.setattr(sync_service.db_session, "lock_engine", fake_engine)
    db = AsyncMock()

    async with sync_service._kb_sync_lock(db, kb_id=2):
        pass

    unlock_sql = str(conn.execute.await_args_list[1].args[0])
    assert "pg_advisory_unlock" in unlock_sql


@pytest.mark.asyncio
async def test_probe_kb_sync_lock_returns_false_when_busy():
    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=[
        MagicMock(scalar=lambda: False),
    ])
    db = AsyncMock()
    db.connection = AsyncMock(return_value=conn)

    assert await sync_service._probe_kb_sync_lock(db, kb_id=2) is False
    assert conn.execute.await_count == 1


@pytest.mark.asyncio
async def test_probe_kb_sync_lock_releases_probe_lock():
    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=[
        MagicMock(scalar=lambda: True),
        MagicMock(),
    ])
    db = AsyncMock()
    db.connection = AsyncMock(return_value=conn)

    assert await sync_service._probe_kb_sync_lock(db, kb_id=2) is True
    assert conn.execute.await_count == 2
    unlock_sql = str(conn.execute.await_args_list[1].args[0])
    assert "pg_advisory_unlock" in unlock_sql


@pytest.mark.asyncio
async def test_release_kb_sync_lock_does_not_call_unlock_all():
    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=RuntimeError("connection closed"))

    await sync_service._release_kb_sync_lock(conn, kb_id=2)

    assert conn.execute.await_count == 1
    unlock_sql = str(conn.execute.await_args_list[0].args[0])
    assert "pg_advisory_unlock" in unlock_sql
    assert "unlock_all" not in unlock_sql


@pytest.mark.asyncio
async def test_ensure_kb_sync_available_raises_when_running_log_exists(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(
        sync_service,
        "_probe_kb_sync_lock",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        sync_service.SyncLogRepository,
        "has_running",
        AsyncMock(return_value=True),
    )

    with pytest.raises(ConflictError, match="already in progress"):
        await sync_service._ensure_kb_sync_available(db, kb_id=2)


@pytest.mark.asyncio
async def test_ensure_kb_sync_available_clears_orphan_before_retry(monkeypatch):
    db = AsyncMock()
    probe = AsyncMock(side_effect=[False, True])
    clear = AsyncMock(return_value=1)
    monkeypatch.setattr(sync_service, "_probe_kb_sync_lock", probe)
    monkeypatch.setattr(
        sync_service.SyncLogRepository,
        "has_running",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(sync_service, "_clear_orphaned_kb_sync_lock", clear)

    await sync_service._ensure_kb_sync_available(db, kb_id=2)

    clear.assert_awaited_once_with(db, 2)
    assert probe.await_count == 2


@pytest.mark.asyncio
async def test_ensure_kb_sync_available_waits_for_terminated_lock(monkeypatch):
    db = AsyncMock()
    probe = AsyncMock(side_effect=[False, False, True])
    clear = AsyncMock(return_value=1)
    sleep = AsyncMock()
    monkeypatch.setattr(sync_service, "_probe_kb_sync_lock", probe)
    monkeypatch.setattr(
        sync_service.SyncLogRepository,
        "has_running",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(sync_service, "_clear_orphaned_kb_sync_lock", clear)
    monkeypatch.setattr(sync_service.asyncio, "sleep", sleep)

    await sync_service._ensure_kb_sync_available(db, kb_id=2)

    clear.assert_awaited_once_with(db, 2)
    sleep.assert_awaited_once_with(0.2)
    assert probe.await_count == 3


@pytest.mark.asyncio
async def test_clear_orphaned_kb_sync_lock_clears_stale_non_idle_holders():
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        [(123,)],
        MagicMock(),
    ])

    cleared = await sync_service._clear_orphaned_kb_sync_lock(db, kb_id=2)

    assert cleared == 1
    first_sql = str(db.execute.await_args_list[0].args[0])
    terminate_sql = str(db.execute.await_args_list[1].args[0])
    assert "a.state = 'idle'" not in first_sql
    assert "current_database" in first_sql
    assert "a.xact_start" in first_sql
    assert "pg_terminate_backend" in terminate_sql


@pytest.mark.asyncio
async def test_start_sync_rejects_when_lock_unavailable(monkeypatch):
    db = AsyncMock()
    kb = MagicMock(id=2, tenant_id="t1", status="active")
    kb_repo = AsyncMock()
    kb_repo.get_by_id = AsyncMock(return_value=kb)
    cancel_stale = AsyncMock()
    monkeypatch.setattr(sync_service, "KnowledgeBaseRepository", kb_repo)
    monkeypatch.setattr(
        sync_service.SyncLogRepository,
        "has_running",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        sync_service.SyncLogRepository,
        "cancel_stale_running",
        cancel_stale,
    )
    monkeypatch.setattr(
        sync_service,
        "_ensure_kb_sync_available",
        AsyncMock(side_effect=ConflictError("Knowledge base sync is already in progress")),
    )

    with pytest.raises(ConflictError, match="already in progress"):
        await sync_service.SyncService.start_sync(db, kb_id=2)

    kb_repo.get_by_id.assert_awaited_once()
    cancel_stale.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_sync_cancels_stale_only_after_lock_available(monkeypatch):
    db = AsyncMock()
    kb = MagicMock(id=2, tenant_id="t1", status="active")
    kb_repo = AsyncMock()
    kb_repo.get_by_id = AsyncMock(return_value=kb)
    ensure = AsyncMock()
    cancel_stale = AsyncMock()
    call_order: list[str] = []

    async def _ensure(*_args, **_kwargs):
        call_order.append("ensure")
        return None

    async def _cancel(*_args, **_kwargs):
        call_order.append("cancel_stale")

    ensure.side_effect = _ensure
    cancel_stale.side_effect = _cancel

    monkeypatch.setattr(sync_service, "KnowledgeBaseRepository", kb_repo)
    monkeypatch.setattr(sync_service, "_ensure_kb_sync_available", ensure)
    monkeypatch.setattr(
        sync_service.SyncLogRepository,
        "has_running",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        sync_service.SyncLogRepository,
        "cancel_stale_running",
        cancel_stale,
    )
    monkeypatch.setattr(
        sync_service.SyncLogRepository,
        "create",
        AsyncMock(return_value=MagicMock(id=99)),
    )
    monkeypatch.setattr(sync_service, "_register_sync_job", lambda *_a, **_k: None)
    monkeypatch.setattr(sync_service, "_background_sync_tasks", set())

    fake_task = MagicMock()
    fake_task.add_done_callback = MagicMock()

    def _fake_create_task(coro):
        if hasattr(coro, "close"):
            coro.close()
        return fake_task

    monkeypatch.setattr(sync_service.asyncio, "create_task", _fake_create_task)

    await sync_service.SyncService.start_sync(db, kb_id=2)

    assert call_order == ["ensure", "cancel_stale"]


@pytest.mark.asyncio
async def test_run_under_kb_sync_lock_does_not_retry_job_conflict(monkeypatch):
    db = AsyncMock()
    job_calls = 0

    @asynccontextmanager
    async def _fake_lock_with_recovery(_db, _kb_id, _sync_log_id):
        yield

    async def job() -> None:
        nonlocal job_calls
        job_calls += 1
        raise ConflictError("business conflict")

    clear = AsyncMock()
    monkeypatch.setattr(
        sync_service, "_kb_sync_lock_with_recovery", _fake_lock_with_recovery,
    )
    monkeypatch.setattr(sync_service, "_clear_orphaned_kb_sync_lock", clear)

    with pytest.raises(ConflictError, match="business conflict"):
        await sync_service._run_under_kb_sync_lock(db, 2, 10, job)

    assert job_calls == 1
    clear.assert_not_awaited()


@pytest.mark.asyncio
async def test_kb_sync_lock_with_recovery_retries_after_orphan_clear(monkeypatch):
    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=[
        MagicMock(scalar=lambda: False),
        MagicMock(scalar=lambda: True),
        MagicMock(),
    ])
    fake_engine = MagicMock()
    fake_engine.connect = AsyncMock(return_value=conn)
    monkeypatch.setattr(sync_service.db_session, "lock_engine", fake_engine)
    db = AsyncMock()

    clear = AsyncMock(return_value=1)
    monkeypatch.setattr(sync_service, "_clear_orphaned_kb_sync_lock", clear)
    monkeypatch.setattr(
        sync_service.SyncLogRepository,
        "get_latest_running",
        AsyncMock(return_value=MagicMock(id=10)),
    )

    async with sync_service._kb_sync_lock_with_recovery(db, kb_id=2, sync_log_id=10):
        pass

    clear.assert_awaited_once_with(db, 2)
    assert conn.execute.await_count == 3
