import logging
import subprocess
import sys

from app.configs.settings import settings

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    """Run pending Alembic migrations on startup via subprocess."""
    if not settings.AUTO_MIGRATE:
        logger.info("Auto-migrate disabled, skipping.")
        return
    logger.info("Running database migrations...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.stdout:
        logger.info("Migration stdout:\n%s", result.stdout)
    if result.returncode != 0:
        logger.error(
            "Migration FAILED (exit=%d):\nstdout: %s\nstderr: %s",
            result.returncode, result.stdout, result.stderr,
        )
        raise RuntimeError(f"Alembic migration failed: {result.stderr}")
    logger.info("Migrations complete.")
