from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.configs.settings import settings
from app.db.session import Base
from app.models import *  # noqa: F401,F403 — ensure all models are registered

config = context.config


def _alembic_sqlalchemy_url(url: str) -> str:
    # ConfigParser treats "%" as interpolation syntax; double them for Alembic.
    return url.replace("%", "%%")


config.set_main_option("sqlalchemy.url", _alembic_sqlalchemy_url(settings.DATABASE_URL))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using a sync connection for Alembic."""
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = sync_url
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
