"""Extension loader for closed-source modules.

This package is intentionally empty in the open-source distribution. Private
deployments overlay closed-source modules into this package before docker
build (see deploy.sh / .github/workflows/deploy.yml).

On startup, every subpackage that defines a top-level callable
``register(app: FastAPI) -> None`` is auto-loaded — typically registering
extra routers or replacing default service implementations.

Adding a new extension is purely additive: drop a new subpackage under
``private/extensions/server/<name>/`` with a ``register(app)`` function;
nothing in the open-source code needs to change.
"""
import importlib
import logging
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


def _augment_path_with_private_overlay() -> None:
    """In local development, mount ``private/extensions/server`` into this package.

    Production deploy copies private extensions into ``server/app/extensions/`` at
    build time (see deploy.sh). In a local checkout we keep them in ``private/``
    and extend ``__path__`` instead so ``pkgutil.iter_modules`` finds them as
    additional ``app.extensions.<name>`` subpackages — no copy required.
    No-op when the directory is absent (e.g. inside the OSS docker image).
    """
    repo_root = Path(__file__).resolve().parents[3]
    private_dir = repo_root / "private" / "extensions" / "server"
    if not private_dir.is_dir():
        return
    path_str = str(private_dir)
    if path_str not in __path__:
        __path__.append(path_str)


_augment_path_with_private_overlay()


def load_extensions(app: "FastAPI") -> list[str]:
    """Discover and register all extension subpackages.

    Returns the list of successfully-loaded extension names (for logging).
    Extension import / register failures are logged but never raise — a
    broken extension must not prevent the rest of the app from booting.
    """
    loaded: list[str] = []
    seen: set[str] = set()
    for _finder, name, ispkg in pkgutil.iter_modules(__path__):
        if not ispkg or name.startswith("_") or name in seen:
            continue
        seen.add(name)
        try:
            mod = importlib.import_module(f"{__name__}.{name}")
        except Exception:
            logger.exception("Failed to import extension '%s'", name)
            continue
        register = getattr(mod, "register", None)
        if not callable(register):
            logger.warning("Extension '%s' has no register(app) function — skipped", name)
            continue
        try:
            register(app)
        except Exception:
            logger.exception("register() failed for extension '%s'", name)
            continue
        loaded.append(name)
        logger.info("Loaded extension: %s", name)
    if loaded:
        logger.info("Loaded %d extension(s): %s", len(loaded), ", ".join(loaded))
    # Single source of truth for any handler that needs to know which
    # closed-source modules are active in this build (e.g. /system/info).
    app.state.loaded_extensions = loaded
    return loaded
