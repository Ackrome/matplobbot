from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from shared_lib.telemetry import configure_service_telemetry


def configure_fastapi_telemetry(app: FastAPI) -> bool:
    if not configure_service_telemetry("matplobbot-fastapi", service_version=app.version):
        return False

    if getattr(app.state, "otel_instrumented", False):
        return True

    FastAPIInstrumentor.instrument_app(app)
    app.state.otel_instrumented = True
    return True
