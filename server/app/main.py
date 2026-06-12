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


@asynccontextmanager
async def lifespan(app: FastAPI):
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
