"""
Observability factory — chooses a Provider based on env config.

A single global instance is exposed via `get_provider()`. We use a module-level
singleton (rather than DI) because logging handlers and SDK lifetimes are
process-global anyway, and this keeps call sites trivially short.
"""
from __future__ import annotations

import logging

from app.configs.settings import settings
from app.libs.observability.noop import NoopProvider
from app.libs.observability.provider import ObservabilityProvider

logger = logging.getLogger(__name__)

_provider: ObservabilityProvider | None = None


def _build_provider() -> ObservabilityProvider:
    backend = (settings.OBSERVABILITY_BACKEND or "noop").lower().strip()

    if backend == "noop":
        return NoopProvider()

    if backend == "otel":
        # Auto-fallback: if marked as otel but endpoint is missing, degrade to
        # noop with a loud warning rather than crashing the app on boot.
        if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
            logger.warning(
                "OBSERVABILITY_BACKEND=otel but OTEL_EXPORTER_OTLP_ENDPOINT is empty "
                "— falling back to NoopProvider."
            )
            return NoopProvider()
        # Imported lazily so noop deployments don't need OpenTelemetry installed.
        try:
            from app.libs.observability.otel import OTelProvider
        except ImportError as exc:
            logger.warning(
                "OBSERVABILITY_BACKEND=otel but OpenTelemetry SDK is not installed "
                "(%s) — falling back to NoopProvider. Run: "
                "pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http",
                exc,
            )
            return NoopProvider()
        return OTelProvider(
            service_name=settings.OTEL_SERVICE_NAME,
            environment=settings.OTEL_DEPLOYMENT_ENVIRONMENT,
            endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
            headers=settings.OTEL_EXPORTER_OTLP_HEADERS,
            traces_pipeline_name=settings.OTEL_TRACES_PIPELINE_NAME,
            logs_table_name=settings.OTEL_LOGS_TABLE_NAME,
        )

    logger.warning(
        "Unknown OBSERVABILITY_BACKEND=%r — falling back to NoopProvider.", backend
    )
    return NoopProvider()


def get_provider() -> ObservabilityProvider:
    """Return the process-wide observability provider, building it lazily."""
    global _provider
    if _provider is None:
        _provider = _build_provider()
    return _provider


def init_observability() -> None:
    """Build and initialize the provider. Safe to call multiple times."""
    provider = get_provider()
    provider.init()
    logger.info("Observability initialized — backend=%s", provider.name)


def shutdown_observability() -> None:
    """Flush and tear down the provider."""
    global _provider
    if _provider is None:
        return
    try:
        _provider.shutdown()
    finally:
        # Keep _provider so late log calls don't blow up on a None reference;
        # shutdown() itself is idempotent.
        pass
