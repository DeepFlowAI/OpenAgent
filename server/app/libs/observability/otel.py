"""
OpenTelemetry-based observability provider.

Speaks standard OTLP/HTTP — works with SigNoz, Honeycomb,
Tempo, and any other OTel-compatible backend. The only vendor-specific bits
are two HTTP headers required by GreptimeDB-compatible pipelines;
they're harmless to other backends and stripped via env config when not needed.

Three named tracers are exposed so downstream queries can cleanly separate
the three log streams the product cares about:

  - tracer "conversation" → conversation lifecycle (round / user / tool / asst)
  - tracer "genai.llm"   → every LLM API call, with `gen_ai.*` semantic attrs
  - root logger handler  → stdlib `logging` records (captured automatically)

Note on imports:
    OpenTelemetry SDK is imported lazily inside `init()` so that environments
    running with `OBSERVABILITY_BACKEND=noop` do not require the OTel packages
    to be installed at all. This keeps the dependency optional in practice.
"""
from __future__ import annotations

import logging
import os
import socket
from contextlib import contextmanager
from typing import Any, Iterator

from app.libs.observability.provider import ObservabilitySpan

_CONVERSATION_TRACER = "conversation"
_LLM_TRACER = "genai.llm"

# Single HTTP-request timeout for OTLP exporters (seconds). Kept short so a
# flaky backend doesn't pile up retries and so process shutdown stays snappy.
_EXPORTER_HTTP_TIMEOUT = 5

# How long the BatchProcessor will wait for a flush during shutdown / on every
# scheduled tick (ms). Below the HTTP timeout × max retries to bound shutdown.
_BATCH_EXPORT_TIMEOUT_MS = 5000

# OTel SDK's own internal loggers. Their export-failure messages must not:
#   1) pollute the application console (treated as user-facing noise);
#   2) flow back into our LoggingHandler (would create an export → fail →
#      log → export feedback loop that masks real application logs).
_NOISY_OTEL_LOGGERS = (
    "opentelemetry.exporter.otlp.proto.http._log_exporter",
    "opentelemetry.exporter.otlp.proto.http.trace_exporter",
    "opentelemetry.sdk._logs._internal.export",
    "opentelemetry.sdk.trace.export",
)


class _DropOTelInternalRecordsFilter(logging.Filter):
    """Drops records from the OTel SDK so we never re-export them.

    This is the second line of defence against the export-feedback loop
    described above. Even if some future SDK module logs without us
    knowing, the filter on our handler stops the cycle dead.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        return not record.name.startswith("opentelemetry")


def _silence_otel_internal_loggers() -> None:
    """Stop OTel SDK's internal export errors from reaching root.

    `propagate = False` keeps the records on their own named loggers
    (debuggers can still attach a handler) while preventing them from
    polluting console output or re-entering our pipeline.
    """
    for name in _NOISY_OTEL_LOGGERS:
        logging.getLogger(name).propagate = False


def _build_id_generator() -> Any:
    """Build an OTel IdGenerator that adopts the app's request trace_id.

    Without this, OTel auto-generates a random 128-bit trace_id per span
    that is unrelated to the ``trace_id`` shown in our console log prefix
    or returned in the ``X-Trace-Id`` HTTP response header — meaning the
    same logical request gets two different trace IDs (one in the console,
    one in your log backend) and cross-correlation becomes impossible.

    The generator pulls from the same ContextVar that ``TraceFilter`` and
    the routers populate. If unset (e.g. background task with no HTTP
    request), it falls back to OTel's standard random generator so
    every span still gets a valid id.
    """
    from opentelemetry.sdk.trace.id_generator import IdGenerator, RandomIdGenerator

    from app.core.trace import get_trace_id_int

    class _AppRequestIdGenerator(IdGenerator):  # noqa: N801 — local class
        def __init__(self) -> None:
            self._fallback = RandomIdGenerator()

        def generate_trace_id(self) -> int:
            tid = get_trace_id_int()
            if tid is not None and tid != 0:
                return tid
            return self._fallback.generate_trace_id()

        def generate_span_id(self) -> int:
            return self._fallback.generate_span_id()

    return _AppRequestIdGenerator()


def _parse_headers(raw: str) -> dict[str, str]:
    """Parse OTel-style "k=v,k=v" header strings into a dict."""
    out: dict[str, str] = {}
    if not raw:
        return out
    for pair in raw.split(","):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


class _OTelSpan:
    """Thin adapter wrapping an OTel span with our minimal interface."""

    def __init__(self, span: Any) -> None:
        self._span = span

    def set_attribute(self, key: str, value: object) -> None:
        # OTel only accepts primitive / sequence-of-primitive values; coerce
        # everything else to str so we don't drop debugging context silently.
        if isinstance(value, (str, bool, int, float)) or (
            isinstance(value, (list, tuple))
            and all(isinstance(x, (str, bool, int, float)) for x in value)
        ):
            self._span.set_attribute(key, value)
        else:
            self._span.set_attribute(key, str(value))

    def set_status_ok(self) -> None:
        # Imported lazily so noop-only deployments stay OTel-free.
        from opentelemetry.trace import Status, StatusCode

        self._span.set_status(Status(StatusCode.OK))

    def set_status_error(self, message: str) -> None:
        from opentelemetry.trace import Status, StatusCode

        self._span.set_status(Status(StatusCode.ERROR, message))

    def add_event(self, name: str, attributes: dict | None = None) -> None:
        self._span.add_event(name, attributes=attributes or {})


class OTelProvider:
    """Ships logs and traces over OTLP/HTTP."""

    name = "otel"

    def __init__(
        self,
        *,
        service_name: str,
        environment: str,
        endpoint: str,
        headers: str,
        traces_pipeline_name: str,
        logs_table_name: str,
    ) -> None:
        self._service_name = service_name
        self._environment = environment
        self._endpoint = endpoint.rstrip("/")
        self._base_headers = _parse_headers(headers)
        self._traces_pipeline_name = traces_pipeline_name
        self._logs_table_name = logs_table_name

        self._initialized = False
        self._tracer_provider: Any | None = None
        self._logger_provider: Any | None = None
        self._log_handler: logging.Handler | None = None

    # ────────────────────────────────────────────────────────────────
    # Lifecycle
    # ────────────────────────────────────────────────────────────────
    def init(self) -> None:
        if self._initialized:
            return
        if not self._endpoint:
            # Misconfiguration — fail loud rather than silently dropping data.
            raise RuntimeError(
                "OTelProvider requires OTEL_EXPORTER_OTLP_ENDPOINT to be set"
            )

        # Lazy SDK import: only required when this provider is actually used.
        from opentelemetry import trace
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http._log_exporter import (
            OTLPLogExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # Best-effort host identifier so Grafana / your log backend can group logs
        # and traces by the originating machine. Falls back to "unknown" rather
        # than failing — observability must never block app startup.
        try:
            host_name = socket.gethostname() or "unknown"
        except Exception:  # noqa: BLE001
            host_name = "unknown"

        resource = Resource.create(
            {
                "service.name": self._service_name,
                "service.instance.id": f"{self._service_name}@{host_name}:{os.getpid()}",
                "deployment.environment": self._environment,
                "host.name": host_name,
            }
        )

        # ── Traces ──
        # GreptimeDB needs the pipeline header to flatten span attributes into
        # query-friendly columns. Other backends ignore unknown headers.
        trace_headers = dict(self._base_headers)
        if self._traces_pipeline_name:
            trace_headers["x-greptime-pipeline-name"] = self._traces_pipeline_name

        span_exporter = OTLPSpanExporter(
            endpoint=f"{self._endpoint}/v1/otlp/v1/traces",
            headers=trace_headers,
            timeout=_EXPORTER_HTTP_TIMEOUT,
        )
        # Adopt the app's request trace_id as OTel's trace_id so the same
        # value shows up in console logs, X-Trace-Id headers, otel_logs.trace_id
        # and opentelemetry_traces.trace_id. Cross-tool correlation just works.
        tp = TracerProvider(resource=resource, id_generator=_build_id_generator())
        tp.add_span_processor(
            BatchSpanProcessor(
                span_exporter,
                export_timeout_millis=_BATCH_EXPORT_TIMEOUT_MS,
            )
        )
        trace.set_tracer_provider(tp)
        self._tracer_provider = tp

        # ── Logs ──
        log_headers = dict(self._base_headers)
        if self._logs_table_name:
            log_headers["X-Greptime-Log-Table-Name"] = self._logs_table_name

        log_exporter = OTLPLogExporter(
            endpoint=f"{self._endpoint}/v1/otlp/v1/logs",
            headers=log_headers,
            timeout=_EXPORTER_HTTP_TIMEOUT,
        )
        lp = LoggerProvider(resource=resource)
        lp.add_log_record_processor(
            BatchLogRecordProcessor(
                log_exporter,
                export_timeout_millis=_BATCH_EXPORT_TIMEOUT_MS,
            )
        )
        set_logger_provider(lp)
        self._logger_provider = lp

        # The handler is attached to root logger by setup_logging(); we just
        # build it here so the SDK lifetimes line up. The filter prevents
        # OTel SDK's own logs from re-entering the export pipeline.
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=lp)
        handler.addFilter(_DropOTelInternalRecordsFilter())
        self._log_handler = handler

        # Stop OTel's internal export-failure logs from reaching root so they
        # don't pollute the application console when the backend is flaky.
        _silence_otel_internal_loggers()

        self._initialized = True

    def shutdown(self) -> None:
        if not self._initialized:
            return
        try:
            if self._tracer_provider is not None:
                self._tracer_provider.shutdown()
        except Exception:  # noqa: BLE001 — best effort flush
            pass
        try:
            if self._logger_provider is not None:
                self._logger_provider.shutdown()
        except Exception:  # noqa: BLE001
            pass
        self._initialized = False

    # ────────────────────────────────────────────────────────────────
    # Console logs
    # ────────────────────────────────────────────────────────────────
    def get_log_handler(self) -> logging.Handler | None:
        return self._log_handler

    # ────────────────────────────────────────────────────────────────
    # Spans
    # ────────────────────────────────────────────────────────────────
    @contextmanager
    def start_conversation_span(
        self, name: str, attributes: dict | None = None
    ) -> Iterator[ObservabilitySpan]:
        from opentelemetry import trace

        tracer = trace.get_tracer(_CONVERSATION_TRACER)
        with tracer.start_as_current_span(name, attributes=attributes or {}) as span:
            yield _OTelSpan(span)

    @contextmanager
    def start_llm_span(
        self, name: str, attributes: dict | None = None
    ) -> Iterator[ObservabilitySpan]:
        from opentelemetry import trace

        tracer = trace.get_tracer(_LLM_TRACER)
        with tracer.start_as_current_span(name, attributes=attributes or {}) as span:
            yield _OTelSpan(span)

    def get_current_span(self) -> ObservabilitySpan:
        from opentelemetry import trace

        return _OTelSpan(trace.get_current_span())
