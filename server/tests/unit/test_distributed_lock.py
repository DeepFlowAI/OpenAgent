"""Unit tests for the Redis distributed lock's renew/abort safety: when renewal
can't confirm ownership (transient errors past the lease, or an explicit lost
lock), the holder task must be cancelled so the body can't run unguarded."""
import asyncio

import pytest

from app.services import distributed_lock as dl


class _FakeRedis:
    """Minimal stand-in: SET NX always wins; eval behavior is test-injected."""

    def __init__(self, eval_impl) -> None:
        self._eval_impl = eval_impl

    async def set(self, key, value, nx=False, px=None):
        return True

    async def eval(self, *args, **kwargs):
        return await self._eval_impl(*args, **kwargs)


@pytest.fixture
def patch_redis(monkeypatch):
    def _install(eval_impl):
        monkeypatch.setattr(dl.redis_client, "_client", _FakeRedis(eval_impl))
    return _install


@pytest.mark.asyncio
async def test_lock_aborts_holder_on_persistent_renew_error(patch_redis):
    async def _raise(*_a, **_k):
        raise RuntimeError("redis down")

    patch_redis(_raise)

    async def body():
        async with dl.redis_lock("k", wait_timeout=1, lease_ms=30):
            await asyncio.sleep(5)  # long body; should be cancelled by renew

    task = asyncio.create_task(body())
    # interval = 10ms; lease window = 30ms => abort within ~40ms. Give margin.
    await asyncio.sleep(0.3)

    assert task.cancelled() or (task.done() and task.exception() is None)
    if not task.done():
        task.cancel()


@pytest.mark.asyncio
async def test_lock_aborts_holder_when_renew_returns_zero(patch_redis):
    async def _lost(*_a, **_k):
        return 0  # token mismatch => lock lost/re-taken

    patch_redis(_lost)

    async def body():
        async with dl.redis_lock("k", wait_timeout=1, lease_ms=30):
            await asyncio.sleep(5)

    task = asyncio.create_task(body())
    await asyncio.sleep(0.1)  # first renew tick (~10ms) sees 0 and aborts

    assert task.cancelled() or (task.done() and task.exception() is None)
    if not task.done():
        task.cancel()


@pytest.mark.asyncio
async def test_lock_releases_cleanly_on_normal_exit(patch_redis):
    async def _ok(*_a, **_k):
        return 1  # renew + release both succeed

    patch_redis(_ok)

    async with dl.redis_lock("k", wait_timeout=1, lease_ms=30):
        pass  # short body, exits before any renew tick

    # No exception => clean acquire/release path works.
