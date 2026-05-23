"""Unit tests for sync cancellation helpers."""

import asyncio

import pytest

from app.services import sync_service


@pytest.mark.asyncio
async def test_request_cancel_sets_event_and_cancels_task():
    sync_log_id = 42
    started = asyncio.Event()

    async def _worker():
        started.set()
        await asyncio.sleep(60)

    task = asyncio.create_task(_worker())
    sync_service._register_sync_job(sync_log_id, task)
    await started.wait()

    assert sync_service._request_cancel_sync(sync_log_id) is True

    with pytest.raises(asyncio.CancelledError):
        await task

    sync_service._unregister_sync_job(sync_log_id)


def test_ensure_not_cancelled_raises_when_requested():
    sync_log_id = 99
    sync_service._active_sync_jobs[sync_log_id] = sync_service._SyncJobHandle()
    sync_service._active_sync_jobs[sync_log_id].cancel_event.set()

    with pytest.raises(sync_service.SyncCancelledError):
        sync_service._ensure_not_cancelled(sync_log_id)

    sync_service._unregister_sync_job(sync_log_id)
