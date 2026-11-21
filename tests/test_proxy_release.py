"""Exercise private proxy rollout state and recovery without touching Docker."""

import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import proxy_release
import release_deploy

PREVIOUS = {"image_id": "sha256:" + "1" * 64, "image": None, "commit": None}
COMMIT = "a" * 40
REFERENCE = "ghcr.io/ackrome/matplobbot-proxy@sha256:" + "2" * 64
CANDIDATE = {"image_id": "sha256:" + "3" * 64, "image": REFERENCE, "commit": COMMIT}


class TestProxyRelease(unittest.TestCase):
    def setUp(self):
        stack = self.enterContext(ExitStack())
        self.root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.state = self.root / "proxy-release.json"
        self.attempt = self.root / "proxy-attempt.json"
        for module in (proxy_release, release_deploy):
            stack.enter_context(patch.object(module, "STATE", self.root))
            stack.enter_context(patch.object(module, "PROXY_STATE", self.state))
            stack.enter_context(patch.object(module, "PROXY_ATTEMPT", self.attempt))
        self.keep = stack.enter_context(patch.object(proxy_release, "keep"))

    def test_failed_rollout_restores_previous_image_and_clears_attempt(self):
        before = {"current": PREVIOUS, "previous": None}
        with (
            patch.object(proxy_release, "switch", side_effect=[RuntimeError(), None]) as switch,
            self.assertRaisesRegex(RuntimeError, "passed recovery"),
        ):
            proxy_release.change(before, CANDIDATE)
        self.assertEqual([call.args[0] for call in switch.call_args_list], [CANDIDATE, PREVIOUS])
        self.assertEqual(proxy_release.read_state(self.state), before)
        self.assertFalse(self.attempt.exists())

    def test_interrupted_recovery_preserves_and_can_replay_journal(self):
        before = {"current": PREVIOUS, "previous": None}
        with (
            patch.object(proxy_release, "switch", side_effect=RuntimeError()),
            self.assertRaisesRegex(RuntimeError, "recovery failed"),
        ):
            proxy_release.change(before, CANDIDATE)
        self.assertEqual(proxy_release.read_state(self.attempt), {"before": before})
        with (
            patch.object(proxy_release, "check_live_checkout"),
            patch.object(proxy_release, "switch") as switch,
        ):
            proxy_release.rollback()
        switch.assert_called_once_with(PREVIOUS)
        self.assertFalse(self.attempt.exists())

    def test_local_image_override_recreates_only_proxy_and_checks_it(self):
        with (
            patch.object(proxy_release.subprocess, "run") as run,
            patch.object(proxy_release, "wait_healthy") as health,
        ):
            proxy_release.switch(CANDIDATE)
        self.assertEqual(
            run.call_args.args[0][-7:],
            ["up", "-d", "--no-deps", "--no-build", "--pull", "never", "proxy"],
        )
        self.assertEqual(
            proxy_release.read_state(self.root / "proxy-compose.json"),
            {"services": {"proxy": {"image": CANDIDATE["image_id"]}}},
        )
        health.assert_called_once_with(CANDIDATE["image_id"])

    def test_pulled_digest_must_match_expected_source_revision(self):
        observed = {
            "Id": CANDIDATE["image_id"],
            "RepoDigests": [REFERENCE],
            "Config": {
                "Labels": {
                    "org.opencontainers.image.source": proxy_release.SOURCE,
                    "org.opencontainers.image.revision": "b" * 40,
                }
            },
        }
        with (
            patch.object(proxy_release.subprocess, "run"),
            patch.object(proxy_release, "run", return_value=json.dumps([observed])),
            self.assertRaisesRegex(RuntimeError, "does not match"),
        ):
            proxy_release.resolve_candidate(REFERENCE, COMMIT)

    def test_pending_app_attempt_blocks_proxy_io(self):
        (self.root / "attempt.json").touch()
        with (
            patch.object(proxy_release, "resolve_candidate") as pull,
            self.assertRaises(release_deploy.ProductionPreflightError),
        ):
            proxy_release.apply(REFERENCE, COMMIT)
        pull.assert_not_called()

    def test_socks_probe_retries_a_transient_command_timeout(self):
        with (
            patch.object(proxy_release, "container_id", return_value="container"),
            patch.object(proxy_release, "run", return_value=f"{CANDIDATE['image_id']} healthy"),
            patch.object(proxy_release.time, "sleep"),
            patch.object(
                proxy_release.subprocess,
                "run",
                side_effect=[
                    subprocess.TimeoutExpired("curl", 10),
                    subprocess.CompletedProcess([], 0),
                ],
            ) as run,
        ):
            proxy_release.wait_healthy(CANDIDATE["image_id"])
        self.assertEqual(run.call_count, 2)
        self.assertIn("--socks5-hostname", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
