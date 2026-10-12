from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import call, patch

import requests
import yaml
from packaging.version import Version
from pip_audit._dependency_source import RequirementSource
from pip_audit._service import ResolvedDependency

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_dependency_audit", ROOT / "scripts" / "run_dependency_audit.py"
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def response(status: int = 200, vulnerabilities: list | None = None) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result.url = "https://pypi.org/pypi/audit-fixture/1.0/json"
    result._content = json.dumps({"vulnerabilities": vulnerabilities or []}).encode("utf-8")
    return result


def vulnerability(identifier: str = "CVE-9999-0001") -> dict:
    return {
        "id": identifier,
        "aliases": [],
        "fixed_in": ["2.0"],
        "summary": "A fixture vulnerability mentioning timeout must still fail immediately.",
    }


class TestNetworkErrorClassification(unittest.TestCase):
    def test_transient_transport_errors(self) -> None:
        for error_type in (
            requests.ReadTimeout,
            requests.ConnectTimeout,
            requests.ConnectionError,
        ):
            with self.subTest(error=error_type.__name__):
                self.assertTrue(runner.is_transient_network_error(error_type("temporary")))

    def test_only_transient_http_statuses(self) -> None:
        for status in (200, 400, 401, 403, 404, 408, 429, 500, 501, 502, 503, 504):
            with self.subTest(status=status):
                error = requests.HTTPError(response=response(status))
                self.assertEqual(
                    runner.is_transient_network_error(error),
                    status in {429, 500, 502, 503, 504},
                )
        self.assertFalse(runner.is_transient_network_error(requests.HTTPError()))

    def test_unknown_errors_and_exit_codes_are_not_network_failures(self) -> None:
        for error in (
            RuntimeError("requests.exceptions.ReadTimeout"),
            ValueError("timeout"),
            SystemExit(1),
            SystemExit(2),
        ):
            with self.subTest(error=error):
                self.assertFalse(runner.is_transient_network_error(error))

    def test_tls_veto_applies_to_entire_exception_graph(self) -> None:
        outer = requests.ConnectionError("wrapper")
        outer.__cause__ = requests.ReadTimeout("temporary")
        outer.__context__ = requests.exceptions.SSLError("certificate verification failed")
        self.assertFalse(runner.is_transient_network_error(outer))
        self.assertFalse(
            runner.is_transient_network_error(requests.exceptions.SSLError("certificate"))
        )

    def test_chained_and_cyclic_errors_terminate(self) -> None:
        outer = SystemExit(1)
        inner = requests.ReadTimeout("temporary")
        outer.__context__ = inner
        inner.__cause__ = outer
        self.assertTrue(runner.is_transient_network_error(outer))
        plain = RuntimeError("cycle")
        plain.__context__ = plain
        self.assertFalse(runner.is_transient_network_error(plain))


class TestRealAuditEntrypoint(unittest.TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.requirements = Path(directory.name) / "requirements.txt"
        self.requirements.write_text("audit-fixture==1.0\n", encoding="utf-8")
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    @contextmanager
    def transport(self, replies: list):
        original_argv = sys.argv
        try:
            with (
                patch.object(
                    RequirementSource,
                    "collect",
                    side_effect=lambda: iter([ResolvedDependency("audit-fixture", Version("1.0"))]),
                ),
                patch("requests.Session.get", side_effect=replies) as get,
                patch.object(runner.time, "sleep") as sleep,
                patch("pip_audit._cli.logger"),
                redirect_stdout(self.stdout),
                redirect_stderr(self.stderr),
            ):
                yield get, sleep
        finally:
            self.assertIs(sys.argv, original_argv)

    def test_clean_success_uses_configured_socket_timeout(self) -> None:
        with self.transport([response()]) as (get, sleep):
            self.assertEqual(runner.run_audit(self.requirements), 0)
            self.assertEqual(get.call_count, 1)
            self.assertEqual(get.call_args.kwargs["timeout"], 60)
            sleep.assert_not_called()
        self.assertIn("No known vulnerabilities found", self.stderr.getvalue())

    def test_read_timeout_then_success(self) -> None:
        with self.transport([requests.ReadTimeout("read timeout=15"), response()]) as (get, sleep):
            self.assertEqual(runner.run_audit(self.requirements), 0)
            self.assertEqual(get.call_count, 2)
            sleep.assert_called_once_with(5)
        self.assertIn("attempt 2/3", self.stdout.getvalue())

    def test_connect_timeout_translated_to_cli_exit_then_success(self) -> None:
        with self.transport([requests.ConnectTimeout("connect timed out"), response()]) as (
            get,
            sleep,
        ):
            self.assertEqual(runner.run_audit(self.requirements), 0)
            self.assertEqual(get.call_count, 2)
            sleep.assert_called_once_with(5)

    def test_transient_http_error_then_success(self) -> None:
        with self.transport([response(503), response()]) as (get, sleep):
            self.assertEqual(runner.run_audit(self.requirements), 0)
            self.assertEqual(get.call_count, 2)
            sleep.assert_called_once_with(5)

    def test_exhausted_timeouts_fail_closed(self) -> None:
        failures = [requests.ReadTimeout(f"timeout {index}") for index in range(3)]
        with self.transport(failures) as (get, sleep):
            self.assertEqual(runner.run_audit(self.requirements), 1)
            self.assertEqual(get.call_count, 3)
            self.assertEqual(sleep.call_args_list, [call(5), call(10)])
        self.assertIn("audit incomplete", self.stderr.getvalue())
        self.assertNotIn("No known vulnerabilities found", self.stderr.getvalue())

    def test_finding_is_not_retried(self) -> None:
        with self.transport([response(vulnerabilities=[vulnerability()])]) as (get, sleep):
            with self.assertRaises(SystemExit) as error:
                runner.run_audit(self.requirements)
            self.assertEqual(error.exception.code, 1)
            self.assertEqual(get.call_count, 1)
            sleep.assert_not_called()
        self.assertIn("Found 1 known vulnerability", self.stderr.getvalue())

    def test_finding_after_timeout_does_not_inherit_previous_error(self) -> None:
        replies = [requests.ReadTimeout("temporary"), response(vulnerabilities=[vulnerability()])]
        with self.transport(replies) as (get, sleep):
            with self.assertRaises(SystemExit) as error:
                runner.run_audit(self.requirements)
            self.assertEqual(error.exception.code, 1)
            self.assertEqual(get.call_count, 2)
            sleep.assert_called_once_with(5)

    def test_only_documented_ignore_is_applied(self) -> None:
        with self.transport([response(vulnerabilities=[vulnerability("PYSEC-2024-277")])]) as (
            get,
            sleep,
        ):
            self.assertEqual(runner.run_audit(self.requirements), 0)
            self.assertEqual(get.call_count, 1)
            sleep.assert_not_called()
        self.assertIn("1 ignored", self.stderr.getvalue())

    def test_missing_package_fails_under_strict_mode_without_retry(self) -> None:
        with self.transport([response(404)]) as (get, sleep):
            with self.assertRaises(SystemExit) as error:
                runner.run_audit(self.requirements)
            self.assertEqual(error.exception.code, 1)
            self.assertEqual(get.call_count, 1)
            sleep.assert_not_called()

    def test_tls_and_unknown_failures_propagate_without_retry(self) -> None:
        for failure in (
            requests.exceptions.SSLError("certificate verification failed"),
            ValueError("unexpected response"),
            KeyboardInterrupt(),
        ):
            with self.subTest(error=type(failure).__name__):
                with self.transport([failure]) as (get, sleep):
                    with self.assertRaises(type(failure)):
                        runner.run_audit(self.requirements)
                    self.assertEqual(get.call_count, 1)
                    sleep.assert_not_called()

    def test_invalid_requirements_path_preserves_cli_failure_and_argv(self) -> None:
        with self.transport([]) as (get, sleep):
            with self.assertRaises(SystemExit) as error:
                runner.run_audit(self.requirements.with_name("missing.txt"))
            self.assertEqual(error.exception.code, 1)
            get.assert_not_called()
            sleep.assert_not_called()


class TestAuditProviderParity(unittest.TestCase):
    def test_github_audits_use_shared_runner_with_wall_clock_limit(self) -> None:
        for workflow in ("ci-cd.yml", "dependency-audit.yml"):
            with self.subTest(workflow=workflow):
                document = yaml.safe_load(
                    (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
                )
                steps = [step for job in document["jobs"].values() for step in job["steps"]]
                audit_steps = [
                    step
                    for step in steps
                    if "scripts/run_dependency_audit.py" in step.get("run", "")
                ]
                self.assertEqual(len(audit_steps), 1)
                self.assertEqual(audit_steps[0]["timeout-minutes"], 20)
                self.assertNotIn("continue-on-error", audit_steps[0])
                self.assertFalse(any("-m pip_audit" in step.get("run", "") for step in steps))

    def test_jenkins_uses_shared_runner_with_wall_clock_limit(self) -> None:
        pipeline = (ROOT / "Jenkinsfile.groovy").read_text(encoding="utf-8")
        command = "timeout --kill-after=10s 20m python scripts/run_dependency_audit.py"
        self.assertEqual(pipeline.count(command), 1)
        self.assertNotIn("-m pip_audit", pipeline)


if __name__ == "__main__":
    unittest.main()
