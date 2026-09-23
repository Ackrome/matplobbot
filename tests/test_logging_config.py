import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from shared_lib.logging_config import resolve_log_format, resolve_log_level

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestLoggingConfig(unittest.TestCase):
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
