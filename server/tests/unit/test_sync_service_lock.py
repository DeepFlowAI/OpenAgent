"""Unit tests for knowledge-base sync locking."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictError
from app.services import sync_service


@pytest.mark.asyncio
async def test_kb_sync_lock_raises_when_busy():
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        MagicMock(scalar=lambda: False),
    ])

    with pytest.raises(ConflictError, match="already in progress"):
        async with sync_service._kb_sync_lock(db, kb_id=2):
            pass


@pytest.mark.asyncio
async def test_kb_sync_lock_releases_on_exit():
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        MagicMock(scalar=lambda: True),
        MagicMock(),
    ])

    async with sync_service._kb_sync_lock(db, kb_id=2):
        pass

    assert db.execute.await_count == 2
    unlock_sql = str(db.execute.await_args_list[1].args[0])
    assert "pg_advisory_unlock" in unlock_sql
