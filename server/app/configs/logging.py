import json
import logging
import sys
from datetime import datetime, timezone

from app.configs.settings import settings
from app.core.trace import TraceFilter
from app.libs.observability import get_provider

TEXT_FORMAT = (
    "%(asctime)s | %(levelname)-8s | [%(trace_id)s] "
    "%(name)s:%(funcName)s:%(lineno)d - %(message)s"
)
# Console shows the full 32-char OTel trace_id so it can be copied directly
# into Grafana / your log backend queries as an exact match — no LIKE needed.
# The same value is also returned in the X-Trace-Id HTTP response header.
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class JsonFormatter(logging.Formatter):
    """Single-line JSON formatter. Multi-line messages are preserved as escaped \\n
    inside the JSON string, so every log record is exactly one line — grep-safe."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            + "Z",
            "level": record.levelname,
            "trace_id": getattr(record, "trace_id", "-"),
            "logger": record.name,
            "func": record.funcName,
            "line": record.lineno,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging() -> None:
    level = logging.DEBUG if settings.DEBUG else logging.INFO

    root = logging.getLogger()
    root.setLevel(level)

    if root.handlers:
        root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.addFilter(TraceFilter())

    if settings.LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(TEXT_FORMAT, datefmt=DATE_FORMAT))

    root.addHandler(handler)

    # Pipe everything the app writes via stdlib logging into the configured
    # observability backend (OTLP / SigNoz / …). When the
    # backend is "noop" this returns None and we keep stdout-only behavior.
    otel_handler = get_provider().get_log_handler()
    if otel_handler is not None:
        otel_handler.setLevel(level)
        otel_handler.addFilter(TraceFilter())
        root.addHandler(otel_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DEBUG else logging.WARNING
    )
    # OpenTelemetry logs a harmless ERROR ("Failed to detach context") when a
    # span context token is detached in a different asyncio context than the one
    # that attached it — common with streaming responses / async generators. It
    # does not affect tracing or business logic, so silence this specific noise.
    logging.getLogger("opentelemetry.context").setLevel(logging.CRITICAL)
