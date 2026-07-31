"""Unit tests for tenant account management routes."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.deps import AuthContext, get_db, require_admin_session
from app.routers.v1.account import router
from app.services.account_service import AccountService


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def override_admin_session() -> AuthContext:
        return AuthContext(
            tenant_id="T_TEST",
            role="admin",
            account_id=1,
            username="admin",
        )

    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    app.dependency_overrides[require_admin_session] = override_admin_session
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_list_accounts_accepts_numeric_page_size_query(monkeypatch) -> None:
    get_paginated = AsyncMock(
        return_value={
            "items": [],
            "total": 0,
            "page": 1,
            "per_page": 20,
            "pages": 0,
        }
    )
    monkeypatch.setattr(AccountService, "get_paginated", get_paginated)

    response = _client().get("/api/v1/accounts?page=1&per_page=20")

    assert response.status_code == 200
    assert response.json()["per_page"] == 20
    assert get_paginated.await_args.kwargs["per_page"] == 20


def test_list_accounts_rejects_unsupported_page_size() -> None:
    response = _client().get("/api/v1/accounts?page=1&per_page=30")

    assert response.status_code == 422
