"""OpenTelemetry tracing (Plan 2 H1).

Decoupled from LangSmith — emit OTLP spans so the same instrumentation
works against any compatible backend (Honeycomb, Tempo, Datadog, Grafana
Cloud, Jaeger via OTLP receiver, …). LangSmith also reads OTLP, so the
LangChain-specific traces continue to work; ``LANGCHAIN_TRACING_V2=true``
is no longer required to get observability.

Configuration (env)
-------------------
- ``OTEL_EXPORTER_OTLP_ENDPOINT``  - e.g. ``http://otel-collector:4318``
- ``OTEL_EXPORTER_OTLP_HEADERS``   - auth (handled by SDK)
- ``OTEL_SERVICE_NAME``            - defaults to ``synesthesia-api``
- ``OTEL_TRACES_EXPORTER``         - "otlp" (default if endpoint set), or
                                     "none" / unset to disable export
- ``OTEL_ENABLED``                 - set to ``false`` to disable entirely

When export is disabled the spans still get created (cheap) but nothing
ships off-box, so calls to :func:`trace` and :func:`tracer` are safe in
local dev with no setup.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace as otel_trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_DEFAULT_SERVICE_NAME = "synesthesia-api"
_tracer: otel_trace.Tracer | None = None
_initialized = False


def configure_tracing(service_name: str | None = None) -> None:
    """Install the OTel TracerProvider with an OTLP exporter if configured.

    Idempotent — safe to call from both FastAPI lifespan and Taskiq worker
    startup. The first call wins; subsequent calls are no-ops.
    """
    global _tracer, _initialized
    if _initialized:
        return

    if os.getenv("OTEL_ENABLED", "true").lower() == "false":
        logger.info("OTel tracing disabled via OTEL_ENABLED=false")
        _tracer = otel_trace.get_tracer(service_name or _DEFAULT_SERVICE_NAME)
        _initialized = True
        return

    # ``Attributes`` is typed restrictively in the OTel SDK; the literals are
    # valid at runtime so we cast for mypy's benefit.
    resource_attrs: dict[str, Any] = {
        "service.name": service_name or os.getenv("OTEL_SERVICE_NAME", _DEFAULT_SERVICE_NAME),
        "service.version": "0.1.0",
    }
    resource = Resource.create(resource_attrs)
    provider = TracerProvider(resource=resource)

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    exporter_kind = os.getenv("OTEL_TRACES_EXPORTER", "otlp" if endpoint else "none")

    if exporter_kind == "otlp" and endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        logger.info("OTel OTLP exporter -> %s", endpoint)
    else:
        logger.info("OTel running without exporter (set OTEL_EXPORTER_OTLP_ENDPOINT to ship)")

    otel_trace.set_tracer_provider(provider)
    _tracer = otel_trace.get_tracer(service_name or _DEFAULT_SERVICE_NAME)
    _initialized = True


def tracer() -> otel_trace.Tracer:
    """Return the configured Tracer, lazy-initializing if not yet set up."""
    if not _initialized:
        configure_tracing()
    assert _tracer is not None
    return _tracer


@contextmanager
def trace(stage: str, **attrs) -> Iterator[otel_trace.Span]:
    """Wrap a pipeline stage in an OTel span + structured log lines.

    Compatible with the previous LangSmith-only API. Attrs become span
    attributes (under the ``synesthesia.`` namespace so they don't collide
    with OTel semantic conventions) and are also logged at INFO so plain
    structured-log consumers see them without an OTel collector.
    """
    t = tracer()
    t0 = time.perf_counter()
    logger.info("stage.start stage=%s %s", stage, attrs)

    with t.start_as_current_span(stage) as span:
        for k, v in attrs.items():
            try:
                span.set_attribute(f"synesthesia.{k}", v)
            except Exception:
                span.set_attribute(f"synesthesia.{k}", str(v))
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(otel_trace.Status(otel_trace.StatusCode.ERROR, str(exc)))
            logger.exception("stage.error stage=%s error=%s", stage, exc)
            raise
        finally:
            dt_ms = (time.perf_counter() - t0) * 1000
            span.set_attribute("synesthesia.duration_ms", dt_ms)
            logger.info("stage.end stage=%s duration_ms=%.1f", stage, dt_ms)
