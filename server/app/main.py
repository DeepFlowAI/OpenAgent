from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.configs.logging import setup_logging
from app.configs.settings import settings
from app.core.exceptions import register_exception_handlers
from app.db.migration import run_migrations
from app.db.seed import seed_system_defaults
from app.db.session import AsyncSessionLocal, engine, lock_engine
from app.extensions import load_extensions
from app.libs.observability import init_observability, shutdown_observability
from app.routers import register_routers

# Init order matters: observability must be ready *before* setup_logging() so
# the OTel logging handler can be attached to the root logger from the start.
init_observability()
setup_logging()


def _validate_concurrency_config() -> None:
    """Fail fast on unsafe concurrency configurations.

    Multiple API workers/replicas only serialize per-conversation rounds and
    survive detached-chat cancel/reattach when both the round lock and the
    detached-chat runtime are Redis-backed; the in-process backends are correct
    only within a single process. Catching this at startup avoids silent data
    races (two workers running the same conversation) in production.
    """
    valid_lock = {"memory", "advisory", "redis"}
    valid_detached = {"memory", "redis"}
    if settings.ROUND_LOCK_BACKEND not in valid_lock:
        raise RuntimeError(
            f"Invalid ROUND_LOCK_BACKEND={settings.ROUND_LOCK_BACKEND!r}; "
            f"expected one of {sorted(valid_lock)}."
        )
    if settings.DETACHED_CHAT_BACKEND not in valid_detached:
        raise RuntimeError(
            f"Invalid DETACHED_CHAT_BACKEND={settings.DETACHED_CHAT_BACKEND!r}; "
            f"expected one of {sorted(valid_detached)}."
        )

    redis_lock = settings.ROUND_LOCK_BACKEND == "redis"
    redis_detached = settings.DETACHED_CHAT_BACKEND == "redis"

    if (redis_lock or redis_detached) and not settings.REDIS_URL:
        raise RuntimeError(
            "ROUND_LOCK_BACKEND/DETACHED_CHAT_BACKEND='redis' requires REDIS_URL."
        )

    from app.services.detached_chat_stream_service import _configured_worker_count

    # Total processes = workers-per-replica × replicas. The replica count can't
    # be auto-detected (each process only sees its own workers), so it must be
    # declared via API_REPLICA_COUNT.
    workers = _configured_worker_count()
    total_processes = workers * settings.API_REPLICA_COUNT
    if total_processes > 1 and not (redis_lock and redis_detached):
        raise RuntimeError(
            f"Detected {total_processes} total API processes "
            f"({workers} workers x {settings.API_REPLICA_COUNT} replicas), but "
            "running >1 process requires ROUND_LOCK_BACKEND='redis' AND "
            "DETACHED_CHAT_BACKEND='redis' (in-process backends are "
            "single-process only). If you run multiple replicas, set "
            "API_REPLICA_COUNT and both redis backends."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_concurrency_config()
    run_migrations()
    async with AsyncSessionLocal() as db:
        await seed_system_defaults(db)
        await db.commit()
    if settings.REDIS_URL:
        from app.db.redis import redis_client

        await redis_client.initialize()
    try:
        yield
    finally:
        if settings.REDIS_URL:
            from app.db.redis import redis_client

            await redis_client.close()
        await engine.dispose()
        await lock_engine.dispose()
        # Flush remaining batched spans/logs before the process exits.
        shutdown_observability()


def _cors_middleware_options() -> dict:
    """Build CORSMiddleware kwargs.

    Browsers forbid Access-Control-Allow-Origin: * together with
    Access-Control-Allow-Credentials: true. We default to wildcard without
    credentials because auth uses Bearer tokens, not cross-site cookies.
    """
    raw = settings.CORS_ALLOW_ORIGINS.strip()
    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        if origins:
            return {
                "allow_origins": origins,
                "allow_credentials": settings.CORS_ALLOW_CREDENTIALS,
                "allow_methods": ["*"],
                "allow_headers": ["*"],
            }
    return {
        "allow_origins": ["*"],
        "allow_credentials": False,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, **_cors_middleware_options())
    register_exception_handlers(app)
    register_routers(app)
    load_extensions(app)
    return app


app = create_app()
