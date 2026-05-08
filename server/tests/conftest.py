import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from app.configs.settings import settings
from app.core.security import create_access_token


def make_auth_header(tenant_id: str = "T_TEST_001") -> dict:
    """Create JWT auth headers for integration tests."""
    token = create_access_token({
        "sub": "1",
        "tenant_id": tenant_id,
        "username": "admin",
        "role": "admin",
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
async def client():
    test_engine = create_async_engine(
        settings.DATABASE_URL, echo=False, poolclass=NullPool
    )
    test_session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    import app.db.session as session_mod
    import app.db.deps as deps_mod
    from app.db.deps import get_db as original_get_db

    original_engine = session_mod.engine
    original_factory = session_mod.AsyncSessionLocal

    session_mod.engine = test_engine
    session_mod.AsyncSessionLocal = test_session_factory

    async def get_test_db():
        async with test_session_factory() as session:
            yield session

    deps_mod.get_db = get_test_db

    from app.main import app

    app.dependency_overrides[original_get_db] = get_test_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await test_engine.dispose()
    session_mod.engine = original_engine
    session_mod.AsyncSessionLocal = original_factory


class TestHealthRouter:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client: AsyncClient):
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
