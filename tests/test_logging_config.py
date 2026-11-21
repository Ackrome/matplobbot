import json
import logging
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from shared_lib.logging_config import (
    JsonFormatter,
    TextFormatter,
    resolve_log_format,
    resolve_log_level,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestLoggingConfig(unittest.TestCase):
    def test_request_credentials_are_masked_in_text_json_and_exception(self):
        secrets = ("calendar-fixture", "legacy-ws-fixture", "ticket-fixture", "jwt-fixture")
        try:
            raise RuntimeError(f"failed for /api/cal/{secrets[0]}/telegram.ics")
        except RuntimeError:
            record = logging.LogRecord(
                "uvicorn.access",
                logging.ERROR,
                __file__,
                1,
                "GET /api/cal/%s/basic.ics and /ws/stats/total_actions?token=%s "
                "Sec-WebSocket-Protocol: matplobbot, mpb-ticket.%s Authorization: Bearer %s",
                secrets,
                sys.exc_info(),
            )
        for formatter in (TextFormatter(), JsonFormatter("test")):
            with self.subTest(formatter=type(formatter).__name__):
                rendered = formatter.format(record)
                for secret in secrets:
                    self.assertNotIn(secret, rendered)
                self.assertIn("/api/cal/[redacted]/basic.ics", rendered)
                self.assertIn("token=[redacted]", rendered)
                self.assertIn("mpb-ticket.[redacted]", rendered)
                self.assertIn("Bearer [redacted]", rendered)
                self.assertIn("RuntimeError: failed for /api/cal/[redacted]/telegram.ics", rendered)

    def test_log_level_is_validated_and_aliases_are_normalized(self):
        self.assertEqual(resolve_log_level("debug"), ("DEBUG", 10))
        self.assertEqual(resolve_log_level("warn"), ("WARNING", 30))

        with self.assertRaisesRegex(ValueError, "Invalid LOG_LEVEL"):
            resolve_log_level("verbose")

    def test_production_defaults_to_json_and_development_to_text(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_log_format(environment="production"), "json")
            self.assertEqual(resolve_log_format(environment="development"), "text")

    def test_explicit_log_format_is_validated(self):
        self.assertEqual(resolve_log_format("JSON", environment="development"), "json")
        with self.assertRaisesRegex(ValueError, "Invalid LOG_FORMAT"):
            resolve_log_format("xml", environment="production")

    def test_configured_json_log_contains_stable_fields_and_correlation_id(self):
        script = """
import logging
from shared_lib.logging_config import configure_logging
from shared_lib.request_context import correlation_scope

configure_logging("logging-test")
with correlation_scope(correlation_id="cid-test-123"):
    logging.getLogger("test.logger").warning("structured message")
"""
        environment = os.environ.copy()
        environment.update(
            {
                "ENVIRONMENT": "production",
                "LOG_LEVEL": "WARNING",
                "LOG_FORMAT": "json",
                "PYTHONUTF8": "1",
            }
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        )

        payload = json.loads(completed.stderr.strip())
        self.assertEqual(payload["level"], "WARNING")
        self.assertEqual(payload["service"], "logging-test")
        self.assertEqual(payload["logger"], "test.logger")
        self.assertEqual(payload["message"], "structured message")
        self.assertEqual(payload["correlation_id"], "cid-test-123")
        self.assertTrue(payload["timestamp"].endswith("Z"))
        self.assertEqual(payload["source"]["module"], "<string>")


if __name__ == "__main__":
    unittest.main()
