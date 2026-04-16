import os
import unittest
from unittest.mock import Mock

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from shared_lib.celery_app import CELERY_CORRELATION_HEADER, dispatch_traced_task
from shared_lib.request_context import correlation_scope
from shared_lib.telemetry import telemetry_enabled


class _FakeCeleryTask:
    name = "shared_lib.tasks.render_pdf"

    def __init__(self):
        self.apply_async = Mock(return_value="queued-task")


class TestTelemetry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if trace.get_tracer_provider().__class__.__name__ == "ProxyTracerProvider":
            trace.set_tracer_provider(TracerProvider())

    def test_telemetry_is_disabled_without_env_configuration(self):
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(telemetry_enabled())

    def test_telemetry_is_enabled_when_flag_is_set(self):
        with unittest.mock.patch.dict(os.environ, {"OTEL_ENABLED": "true"}, clear=True):
            self.assertTrue(telemetry_enabled())

    def test_dispatch_traced_task_injects_traceparent_and_correlation_id(self):
        fake_task = _FakeCeleryTask()
        tracer = trace.get_tracer(__name__)

        with correlation_scope(correlation_id="cid-123"):
            with tracer.start_as_current_span("parent-span"):
                result = dispatch_traced_task(fake_task, "payload", format="pdf")

        self.assertEqual(result, "queued-task")
        call = fake_task.apply_async.call_args
        self.assertEqual(call.kwargs["args"], ("payload",))
        self.assertEqual(call.kwargs["kwargs"], {"format": "pdf"})
        self.assertEqual(call.kwargs["headers"][CELERY_CORRELATION_HEADER], "cid-123")
        self.assertIn("traceparent", call.kwargs["headers"])
