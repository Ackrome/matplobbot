import time

from celery import Celery, Task
from opentelemetry.trace import SpanKind, Status, StatusCode

from .redis_client import get_redis_url
from .request_context import (
    generate_correlation_id,
    get_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from .telemetry import (
    attach_correlation_id_to_span,
    configure_service_telemetry,
    extract_trace_context,
    get_tracer,
    inject_trace_context,
)


def get_celery_redis_url() -> str:
    """Resolve the broker/backend URL through the shared Redis configuration."""
    return get_redis_url()


REDIS_URL = get_celery_redis_url()
CELERY_CORRELATION_HEADER = "x-correlation-id"


class TracedTask(Task):
    abstract = True

    def __call__(self, *args, **kwargs):
        configure_service_telemetry("matplobbot-worker")

        headers = dict(getattr(self.request, "headers", None) or {})
        correlation_id = (
            str(headers.get(CELERY_CORRELATION_HEADER) or "").strip()
            or get_correlation_id()
            or generate_correlation_id(prefix="celery")
        )
        token = set_correlation_id(correlation_id)
        tracer = get_tracer("shared_lib.celery")

        with tracer.start_as_current_span(
            f"celery.process {self.name}",
            context=extract_trace_context(headers),
            kind=SpanKind.CONSUMER,
        ) as span:
            span.set_attribute("messaging.system", "celery")
            span.set_attribute("messaging.operation", "process")
            span.set_attribute("messaging.destination_kind", "queue")
            span.set_attribute(
                "messaging.destination.name",
                getattr(self.request, "delivery_info", {}).get("routing_key", "celery"),
            )
            span.set_attribute("messaging.message.id", getattr(self.request, "id", ""))
            span.set_attribute("celery.task_name", self.name)
            attach_correlation_id_to_span(span, correlation_id)
            started = time.monotonic()
            successful = False
            try:
                result = super().__call__(*args, **kwargs)
                successful = not (isinstance(result, dict) and result.get("status") == "error")
                return result
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            finally:
                reset_correlation_id(token)
                if self.name.rsplit(".", 1)[-1] in {
                    "compile_full_latex", "compile_project", "render_pdf", "render_mermaid",
                }:
                    from .operational_metrics import record_operation_sync

                    record_operation_sync(
                        "studio_compile", successful=successful,
                        duration_seconds=time.monotonic() - started,
                        error_code=None if successful else "compile_failed",
                    )


app = Celery(
    "matplobbot_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["shared_lib.tasks"],
    task_cls=TracedTask,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    result_expires=86400,
    redis_socket_timeout=5,
    redis_socket_connect_timeout=5,
)


def dispatch_traced_task(task: Task, *args, _task_id: str | None = None, **kwargs):
    tracer = get_tracer("shared_lib.celery")
    correlation_id = get_correlation_id()
    if not correlation_id or correlation_id == "-":
        correlation_id = generate_correlation_id(prefix="celery")

    headers = {CELERY_CORRELATION_HEADER: correlation_id}
    with tracer.start_as_current_span(
        f"celery.publish {task.name}",
        kind=SpanKind.PRODUCER,
    ) as span:
        span.set_attribute("messaging.system", "celery")
        span.set_attribute("messaging.operation", "publish")
        span.set_attribute("messaging.destination_kind", "queue")
        span.set_attribute("celery.task_name", task.name)
        attach_correlation_id_to_span(span, correlation_id)
        inject_trace_context(headers)
        options = {"task_id": _task_id} if _task_id else {}
        return task.apply_async(args=args, kwargs=kwargs, headers=headers, **options)
