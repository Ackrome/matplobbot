"""Exercise the real Jenkins transport against a local disposable HTTP fixture."""

import base64
import json
import shutil
import sys
import tempfile
import threading
import unittest
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from jenkins_deploy_wait import DeploymentError, JenkinsTransport, deploy

COMMIT = "a" * 40
JOB = "/job/matplobbot-deploy"
FORM_PATH = JOB + "/buildWithParameters"
QUEUE_PATH = "/queue/item/72/api/json"
BUILD_PATH = JOB + "/145/api/json"
PROOF_PATH = JOB + "/145/artifact/release-smoke.json"
FAILURE_PATH = JOB + "/145/artifact/release-failure.json"
EXPECTED_AUTH = "Basic " + base64.b64encode(b"ci-fixture:local-test-token").decode()


@unittest.skipUnless(shutil.which("curl"), "requires curl")
class TestJenkinsDeployment(unittest.TestCase):
    def setUp(self):
        fixture = self
        self.calls = Counter()
        self.report = []
        self.forms = []
        self.overrides = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_request(self):
                path = urlsplit(self.path).path
                fixture.calls[(self.command, path)] += 1
                if self.headers.get("Authorization") != EXPECTED_AUTH:
                    code, headers, value = 403, {}, {}
                else:
                    code, headers, value = fixture.respond(self, path)
                if code is None:
                    self.close_connection = True
                    return
                self.send_response(code)
                for name, header in headers.items():
                    self.send_header(name, header)
                self.end_headers()
                self.wfile.write(json.dumps(value).encode())

            do_GET = do_POST = handle_request

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(self.server.shutdown)
        private = self.enterContext(tempfile.TemporaryDirectory())
        self.origin = f"http://jenkins.local:{self.server.server_port}"
        self.transport = JenkinsTransport(
            self.origin + JOB, "127.0.0.1", "ci-fixture", "local-test-token", Path(private)
        )

    def respond(self, request, path):
        if path == JOB + "/api/json":
            code, headers, payload = (
                200,
                {},
                {
                    "property": [
                        {
                            "parameterDefinitions": [
                                {"name": name}
                                for name in ("SOURCE_COMMIT", "RELEASE_MANIFEST_B64", "DEPLOY_HOST")
                            ],
                        }
                    ],
                },
            )
        elif path == FORM_PATH and request.command == "POST":
            raw = request.rfile.read(int(request.headers["Content-Length"])).decode()
            self.forms.append(parse_qs(raw))
            code, headers, payload = (
                201,
                {"Location": "http://configured.example/queue/item/72/"},
                {},
            )
        elif path == QUEUE_PATH:
            queued = self.calls[("GET", path)] == 1
            executable = (
                None if queued else {"number": 145, "url": f"http://configured.example{JOB}/145/"}
            )
            code, headers, payload = 200, {}, {"id": 72, "executable": executable}
        elif path == BUILD_PATH:
            poll = self.calls[("GET", path)]
            building = poll == 1
            code, headers, payload = (
                200,
                {},
                {
                    "number": 145,
                    "queueId": 72,
                    "building": building,
                    "inProgress": poll < 3,
                    "result": None if building else "SUCCESS",
                },
            )
        elif path == PROOF_PATH:
            code, headers, payload = (
                200,
                {},
                {
                    "commit": COMMIT,
                    "number": 145,
                    "status": "smoke_verified",
                },
            )
        else:
            code, headers, payload = 404, {}, {}
        return self.overrides.get(path, (code, headers, payload))

    def go(self, *, timeout=3):
        deploy(
            self.transport,
            COMMIT,
            b"private-manifest-fixture",
            "192.168.1.40",
            timeout=timeout,
            interval=0.01,
            report=self.report.append,
        )

    def test_exact_queue_and_build_link_and_successful_smoke(self):
        self.go()
        self.assertEqual(self.calls[("POST", FORM_PATH)], 1)
        self.assertEqual(self.calls[("GET", QUEUE_PATH)], 2)
        self.assertEqual(self.calls[("GET", BUILD_PATH)], 3)
        self.assertEqual(self.calls[("GET", PROOF_PATH)], 1)
        self.assertEqual(self.forms[0]["SOURCE_COMMIT"], [COMMIT])
        self.assertEqual(self.forms[0]["DEPLOY_HOST"], ["192.168.1.40"])
        self.assertEqual(
            base64.b64decode(self.forms[0]["RELEASE_MANIFEST_B64"][0]), b"private-manifest-fixture"
        )
        report = "\n".join(self.report)
        self.assertIn(self.origin + "/queue/item/72/", report)
        self.assertIn(self.origin + JOB + "/145/", report)
        self.assertIn("passed smoke tests", report)
        for secret in ("local-test-token", "private-manifest-fixture", "configured.example"):
            self.assertNotIn(secret, report)

    def test_failed_build_is_not_reported_as_deployed(self):
        self.fail_build()
        with self.assertRaisesRegex(DeploymentError, "finished with FAILURE"):
            self.go()
        self.assertEqual(self.calls[("GET", PROOF_PATH)], 0)
        self.assertEqual(self.calls[("GET", FAILURE_PATH)], 1)

    def fail_build(self):
        self.overrides[BUILD_PATH] = (
            200,
            {},
            {
                "number": 145,
                "queueId": 72,
                "building": False,
                "inProgress": False,
                "result": "FAILURE",
            },
        )

    def test_failure_artifact_reports_exact_stage_and_code(self):
        self.fail_build()
        self.overrides[FAILURE_PATH] = (200, {}, self.failure_artifact())
        with self.assertRaisesRegex(DeploymentError, "finished with FAILURE"):
            self.go()
        self.assertEqual(self.calls[("GET", PROOF_PATH)], 0)
        self.assertIn(
            "Jenkins failure in Production Preflight: `production_tracked_changes`.", self.report
        )

    def test_failure_artifact_reports_late_prepare_code(self):
        self.fail_build()
        self.overrides[FAILURE_PATH] = (
            200,
            {},
            self.failure_artifact(stage="Deploy to Production", code="production_release_pending"),
        )
        with self.assertRaisesRegex(DeploymentError, "finished with FAILURE"):
            self.go()
        self.assertIn(
            "Jenkins failure in Deploy to Production: `production_release_pending`.", self.report
        )

    def failure_artifact(self, **overrides):
        return {
            "commit": COMMIT,
            "number": 145,
            "stage": "Production Preflight",
            "code": "production_tracked_changes",
            **overrides,
        }

    def test_failure_artifact_rejects_foreign_build_or_unapproved_fields(self):
        self.fail_build()
        for payload in (
            self.failure_artifact(commit="b" * 40),
            self.failure_artifact(number=146),
            self.failure_artifact(stage="Pre-Deploy Quality Gate"),
            self.failure_artifact(
                stage="Deploy to Production", code="production_preflight_timeout"
            ),
            self.failure_artifact(code="private-debug-value"),
            self.failure_artifact(extra="private-debug-value"),
            {"malformed": True},
        ):
            with self.subTest(payload=payload):
                self.report.clear()
                self.overrides[FAILURE_PATH] = (200, {}, payload)
                with self.assertRaisesRegex(DeploymentError, "finished with FAILURE"):
                    self.go()
                self.assertNotIn("Jenkins failure in", "\n".join(self.report))
                self.assertNotIn("private-debug-value", "\n".join(self.report))
        self.assertEqual(self.calls[("GET", PROOF_PATH)], 0)

    def test_jenkins_deduplication_reuses_existing_queue(self):
        self.overrides[FORM_PATH] = (303, {"Location": "/queue/item/72/"}, {})
        self.go()
        self.assertEqual(self.calls[("POST", FORM_PATH)], 1)
        self.assertEqual(self.calls[("GET", PROOF_PATH)], 1)

    def test_smoke_attestation_with_wrong_commit_is_rejected(self):
        self.overrides[PROOF_PATH] = (
            200,
            {},
            {"commit": "b" * 40, "number": 145, "status": "smoke_verified"},
        )
        with self.assertRaisesRegex(DeploymentError, "smoke proof does not match"):
            self.go()

    def test_cancelled_queue_fails_without_checking_latest_build(self):
        self.overrides[QUEUE_PATH] = (200, {}, {"id": 72, "cancelled": True})
        with self.assertRaisesRegex(DeploymentError, "cancelled"):
            self.go()
        self.assertEqual(self.calls[("GET", BUILD_PATH)], 0)

    def test_foreign_build_is_never_read(self):
        self.overrides[QUEUE_PATH] = (
            200,
            {},
            {
                "id": 72,
                "executable": {"number": 145, "url": "https://other.example/job/other/145/"},
            },
        )
        with self.assertRaisesRegex(DeploymentError, "does not reference the expected job"):
            self.go()
        self.assertEqual(self.calls[("GET", BUILD_PATH)], 0)

    def test_wait_timeout_never_submits_again(self):
        self.overrides[QUEUE_PATH] = (200, {}, {"id": 72, "executable": None})
        with self.assertRaisesRegex(DeploymentError, "Timed out waiting for Jenkins queue"):
            self.go(timeout=0.12)
        self.assertEqual(self.calls[("POST", FORM_PATH)], 1)

    def test_unknown_dispatch_is_never_retried(self):
        self.overrides[FORM_PATH] = (None, {}, {})
        with self.assertRaisesRegex(DeploymentError, "dispatch outcome is unknown"):
            self.go()
        self.assertEqual(self.calls[("POST", FORM_PATH)], 1)
