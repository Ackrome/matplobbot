"""Failure and cache integrity boundaries of the pinned Jenkins Node bootstrap."""

import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import jenkins_node


class JenkinsNodeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.cache = self.root / "cache"
        self.archive = self.root / "fixture.tar.xz"
        self.config = self.root / "pin.json"
        self.stack.enter_context(
            patch.object(jenkins_node.platform, "system", return_value="Linux")
        )
        self.stack.enter_context(
            patch.object(jenkins_node.platform, "machine", return_value="x86_64")
        )
        # Windows does not expose Linux ownership/mode semantics; archive and
        # binary handling below remain real filesystem operations on both hosts.
        self.stack.enter_context(
            patch.object(
                jenkins_node,
                "private_directory",
                side_effect=lambda p: p.mkdir(parents=True, exist_ok=True),
            )
        )
        self.download = self.stack.enter_context(
            patch.object(
                jenkins_node, "download", side_effect=lambda u, p: shutil.copyfile(self.archive, p)
            )
        )
        self.execute = self.stack.enter_context(
            patch.object(
                jenkins_node.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, '["v24.21.0","linux","x64"]'),
            )
        )
        self.fixture()

    def fixture(self, member_type=tarfile.REGTYPE):
        with tarfile.open(self.archive, "w:xz") as package:
            member = tarfile.TarInfo("node-v24.21.0-linux-x64/bin/node")
            member.type = member_type
            member.linkname = "/outside/cache"
            member.size = 12 if member_type == tarfile.REGTYPE else 0
            package.addfile(member, io.BytesIO(b"trusted-node") if member.size else None)
        self.config.write_text(
            json.dumps(
                {
                    "version": "24.21.0",
                    "platform": "linux",
                    "architecture": "x64",
                    "archive_sha256": jenkins_node.sha256(self.archive),
                }
            )
        )

    def test_verified_binary_is_restored_from_cached_archive_before_execution(self):
        directory = jenkins_node.provision(self.config, self.cache)
        self.assertEqual((directory / "node").read_bytes(), b"trusted-node")
        (directory / "node").write_bytes(b"corrupt-executable")

        def execute(args, **kwargs):
            self.assertEqual(Path(args[0]).read_bytes(), b"trusted-node")
            self.assertEqual(kwargs["env"], {"PATH": str(directory)})
            return subprocess.CompletedProcess(args, 0, '["v24.21.0","linux","x64"]')

        self.execute.side_effect = execute
        self.assertEqual(jenkins_node.provision(self.config, self.cache), directory)
        self.download.assert_called_once()
        self.assertIn("https://nodejs.org/dist/v24.21.0/", self.download.call_args.args[0])

    def test_download_checksum_failure_precedes_unpack_or_execution(self):
        data = json.loads(self.config.read_text())
        data["archive_sha256"] = hashlib.sha256(b"different").hexdigest()
        self.config.write_text(json.dumps(data))
        with patch.object(jenkins_node.tarfile, "open") as unpack:
            with self.assertRaisesRegex(ValueError, "checksum"):
                jenkins_node.provision(self.config, self.cache)
        unpack.assert_not_called()
        self.execute.assert_not_called()
        self.assertEqual(list(self.cache.rglob("node")), [])

    def test_cached_archive_corruption_fails_before_execution(self):
        jenkins_node.provision(self.config, self.cache)
        next(self.cache.rglob("*.tar.xz")).write_bytes(b"corrupt")
        self.execute.reset_mock()
        with self.assertRaisesRegex(ValueError, "checksum"):
            jenkins_node.provision(self.config, self.cache)
        self.execute.assert_not_called()
        self.download.assert_called_once()

    def test_symlink_archive_member_is_never_extracted_or_executed(self):
        self.fixture(tarfile.SYMTYPE)
        with self.assertRaisesRegex(ValueError, "regular bin/node"):
            jenkins_node.provision(self.config, self.cache)
        self.execute.assert_not_called()
        self.assertEqual(list(self.cache.rglob("node")), [])

    def test_unsupported_host_and_wrong_runtime_metadata_fail_closed(self):
        with patch.object(jenkins_node.platform, "machine", return_value="aarch64"):
            with self.assertRaisesRegex(ValueError, "Linux x86_64"):
                jenkins_node.provision(self.config, self.cache)
        self.download.assert_not_called()
        self.execute.return_value.stdout = '["v22.0.0","linux","x64"]'
        with self.assertRaisesRegex(ValueError, "version/platform"):
            jenkins_node.provision(self.config, self.cache)

    def test_both_gates_bind_the_checked_in_runtime_pin(self):
        pin = jenkins_node.configuration(ROOT / "scripts/node_runtime.json")
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci-cd.yml").read_text())
        node_steps = [
            s
            for job in workflow["jobs"].values()
            for s in job.get("steps", [])
            if s.get("uses", "").startswith("actions/setup-node@")
        ]
        self.assertTrue(node_steps)
        self.assertTrue(all(str(s["with"]["node-version"]) == pin["version"] for s in node_steps))
        pipeline = (ROOT / "Jenkinsfile.groovy").read_text()
        bootstrap = pipeline.index('NODE_BIN_DIR="$(python scripts/jenkins_node.py)"')
        self.assertLess(bootstrap, pipeline.index("coverage run --branch"))
        self.assertIn('export PATH="$NODE_BIN_DIR:$PATH"', pipeline[bootstrap:])


if __name__ == "__main__":
    unittest.main()
