import os

from celery import Celery, Task
from opentelemetry.trace import SpanKind, Status, StatusCode

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

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
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

            try:
                return super().__call__(*args, **kwargs)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            finally:
                reset_correlation_id(token)


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
)


def dispatch_traced_task(task: Task, *args, **kwargs):
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
        return task.apply_async(args=args, kwargs=kwargs, headers=headers)
