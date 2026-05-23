"""
Integration tests for Sync API (git sync + document parsing).

Provide a real GitHub repo + PAT via env vars to exercise authenticated paths:
    GIT_TOKEN_FOR_TESTS  — a personal access token with repo:read on GIT_URL
    GIT_URL_FOR_TESTS    — optional override of the default test repo

Tests that require auth will be skipped automatically when GIT_TOKEN_FOR_TESTS
is unset, so the suite still passes in CI without secrets.
"""
import asyncio
import os
import time
import pytest
from httpx import AsyncClient

TENANT_ID = "T_TEST_SYNC"
GIT_URL = os.getenv(
    "GIT_URL_FOR_TESTS", "https://github.com/DeepFlowAI/testagentmarkdown"
)
GIT_TOKEN = os.getenv("GIT_TOKEN_FOR_TESTS", "")

requires_git_token = pytest.mark.skipif(
    not GIT_TOKEN, reason="GIT_TOKEN_FOR_TESTS not set; skipping authenticated git tests"
)


def unique_name(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000) % 100000}"


class TestSyncAPI:

    @requires_git_token
    @pytest.mark.asyncio
    async def test_sync_public_repo_returns_200(self, client: AsyncClient):
        name = unique_name("sync-pub")
        create_resp = await client.post(
            "/api/v1/knowledge-bases",
            json={
                "tenant_id": TENANT_ID,
                "name": name,
                "git_url": GIT_URL,
                "git_branch": "main",
                "auth_type": "token",
                "auth_token": GIT_TOKEN,
            },
        )
        assert create_resp.status_code == 201
        kb_id = create_resp.json()["id"]

        sync_resp = await client.post(f"/api/v1/knowledge-bases/{kb_id}/sync")
        assert sync_resp.status_code == 200
        data = sync_resp.json()
        assert data["status"] == "running"
        assert data["sync_log_id"] > 0

        terminal_status = None
        for _ in range(90):
            await asyncio.sleep(2)
            logs_resp = await client.get(
                f"/api/v1/knowledge-bases/{kb_id}/sync-logs",
            )
            assert logs_resp.status_code == 200
            items = logs_resp.json()["items"]
            target = next(
                (log for log in items if log["id"] == data["sync_log_id"]),
                None,
            )
            if target and target["status"] in (
                "success", "partial_success", "failed",
            ):
                terminal_status = target["status"]
                break

        assert terminal_status in ("success", "partial_success")
        assert target["total_files"] is not None and target["total_files"] >= 0
        assert target["success_count"] is not None and target["success_count"] >= 0

    @pytest.mark.asyncio
    async def test_sync_nonexistent_kb_returns_404(self, client: AsyncClient):
        resp = await client.post("/api/v1/knowledge-bases/99999/sync")
        assert resp.status_code == 404
