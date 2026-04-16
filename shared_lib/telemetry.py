import logging
import os
import socket

from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_FALSE_VALUES = {"0", "false", "no", "off"}
_configured_service_name: str | None = None
_aiohttp_instrumented = False


def telemetry_enabled() -> bool:
    raw_value = os.getenv("OTEL_ENABLED")
    if raw_value is not None:
        return raw_value.strip().lower() not in _FALSE_VALUES

    return bool(
        (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
        or (os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or "").strip()
    )


def _build_resource(service_name: str, service_version: str | None = None) -> Resource:
    attributes = {
        "service.name": service_name,
        "service.namespace": os.getenv("OTEL_SERVICE_NAMESPACE", "matplobbot"),
        "deployment.environment": os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT", "development"),
        "service.instance.id": f"{socket.gethostname()}-{os.getpid()}",
    }
    if service_version:
        attributes["service.version"] = service_version
    return Resource.create(attributes)


def configure_service_telemetry(
    service_name: str,
    *,
    service_version: str | None = None,
) -> bool:
    global _configured_service_name, _aiohttp_instrumented

    if not telemetry_enabled():
        return False

    if _configured_service_name is None:
        provider = TracerProvider(resource=_build_resource(service_name, service_version))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        _configured_service_name = service_name
        logger.info("OpenTelemetry tracing enabled for %s", service_name)
    elif _configured_service_name != service_name:
        logger.debug(
            "OpenTelemetry already configured for %s; keeping existing provider in %s",
            _configured_service_name,
            service_name,
        )

    if not _aiohttp_instrumented:
        AioHttpClientInstrumentor().instrument()
        _aiohttp_instrumented = True

    return True


def get_tracer(name: str):
    return trace.get_tracer(name)


def inject_trace_context(carrier: dict[str, str]) -> None:
    propagate.inject(carrier)


def extract_trace_context(carrier: dict[str, str] | None):
    return propagate.extract(carrier or {})


def attach_correlation_id_to_span(span, correlation_id: str | None) -> None:
    if not correlation_id or correlation_id == "-":
        return
    if span is not None and span.is_recording():
        span.set_attribute("correlation_id", correlation_id)
