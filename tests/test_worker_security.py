"""Host policy preflight must reject drift without weakening renderer isolation."""

import json
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from scripts import worker_security as security


class WorkerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.template = self.root / security.POLICY_TEMPLATE
        self.template.parent.mkdir()
        self.template.write_bytes(
            b"abi <abi/4.0>,\nprofile @PROFILE_NAME@ flags=(unconfined) { userns, }\n"
        )

    def installed(self, *, content=None, uid=0, mode=0o644, symlink=False):
        target = Mock()
        target.is_symlink.return_value = symlink
        target.read_bytes.return_value = (
            security.profile_text(self.root).encode() if content is None else content
        )
        target.stat.return_value = SimpleNamespace(st_uid=uid, st_mode=stat.S_IFREG | mode)
        directory = MagicMock()
        directory.__truediv__.return_value = target
        return patch.object(security, "PROFILE_DIRECTORY", directory), target

    def test_policy_identity_changes_with_any_source_edit(self):
        name = security.profile_name(self.root)
        rendered = security.profile_text(self.root)
        self.assertIn(name, rendered)
        self.assertNotIn("@PROFILE_NAME@", rendered)
        self.template.write_bytes(self.template.read_bytes() + b"# changed policy\n")
        self.assertNotEqual(name, security.profile_name(self.root))

    def test_policy_requires_one_placeholder(self):
        self.template.write_bytes(b"profile unsafe { userns, }")
        with self.assertRaises(ValueError):
            security.profile_name(self.root)

    def test_no_apparmor_daemon_omits_option_without_host_policy_read(self):
        with (
            patch.object(security, "docker_uses_apparmor", return_value=False),
            patch.object(security, "verify_installed_profile") as verify,
        ):
            self.assertIsNone(security.apparmor_security_option(self.root))
            verify.assert_not_called()

    def test_apparmor_checks_exact_installed_bytes_without_root_only_kernel_read(self):
        installed, _ = self.installed()
        with (
            installed,
            patch.object(security, "docker_uses_apparmor", return_value=True),
            patch.object(security, "_loaded", side_effect=PermissionError) as loaded,
        ):
            self.assertEqual(
                security.apparmor_security_option(self.root),
                "apparmor=" + security.profile_name(self.root),
            )
            loaded.assert_not_called()

    def test_drift_symlink_and_writable_file_fail_closed(self):
        for options in (
            {"content": b"different"},
            {"symlink": True},
            {"uid": 1000},
            {"mode": 0o664},
        ):
            with self.subTest(options=options):
                installed, _ = self.installed(**options)
                with installed, self.assertRaises(RuntimeError):
                    security.verify_installed_profile(
                        security.profile_name(self.root), security.profile_text(self.root)
                    )

    def test_missing_policy_is_not_accepted(self):
        installed, target = self.installed()
        target.read_bytes.side_effect = FileNotFoundError
        with installed, self.assertRaisesRegex(RuntimeError, "must be provisioned"):
            security.verify_installed_profile(
                security.profile_name(self.root), security.profile_text(self.root)
            )

    def test_retained_policy_content_must_match_hash_name(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            security.verify_installed_profile(
                security.profile_name(self.root), security.profile_text(self.root) + "# changed\n"
            )
        with self.assertRaisesRegex(ValueError, "Invalid"):
            security.verify_installed_profile("../../other-policy", "content")

    def test_daemon_capability_detection_is_strict(self):
        for values, expected in (
            (["name=apparmor", "name=seccomp,profile=builtin"], True),
            ([], False),
        ):
            with patch.object(
                security.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(values))
            ):
                self.assertEqual(security.docker_uses_apparmor(), expected)
        for output in ("not-json", "null", '{"apparmor":true}', "[12]"):
            with patch.object(
                security.subprocess, "run", return_value=SimpleNamespace(stdout=output)
            ):
                with self.assertRaises(RuntimeError):
                    security.docker_uses_apparmor()
        with patch.object(
            security.subprocess, "run", side_effect=subprocess.TimeoutExpired("docker", 30)
        ):
            with self.assertRaises(RuntimeError):
                security.docker_uses_apparmor()

    def test_install_never_replaces_existing_content_or_reloads_matching_policy(self):
        directory = self.root / "installed"
        directory.mkdir()
        target = directory / security.profile_name(self.root)
        with (
            patch.object(security, "PROFILE_DIRECTORY", directory),
            patch.object(security.sys, "platform", "linux"),
            patch.object(security.os, "geteuid", return_value=0, create=True),
            patch.object(security, "docker_uses_apparmor", return_value=True),
            patch.object(security, "_loaded", return_value=True),
            patch.object(security, "verify_installed_profile"),
            patch.object(security.subprocess, "run") as run,
        ):
            target.write_bytes(b"different")
            with self.assertRaisesRegex(RuntimeError, "Refusing to replace"):
                security.install_policy(self.root)
            self.assertEqual(target.read_bytes(), b"different")
            run.assert_not_called()
            target.write_bytes(security.profile_text(self.root).encode())
            self.assertEqual(security.install_policy(self.root), security.profile_name(self.root))
            run.assert_not_called()

    def test_install_adds_only_new_hash_named_policy(self):
        directory = self.root / "installed"
        directory.mkdir()
        with (
            patch.object(security, "PROFILE_DIRECTORY", directory),
            patch.object(security.sys, "platform", "linux"),
            patch.object(security.os, "geteuid", return_value=0, create=True),
            patch.object(security, "docker_uses_apparmor", return_value=True),
            patch.object(security, "_loaded", side_effect=(False, True)),
            patch.object(security, "verify_installed_profile"),
            patch.object(security.subprocess, "run") as run,
        ):
            name = security.install_policy(self.root)
            self.assertEqual(
                (directory / name).read_bytes(), security.profile_text(self.root).encode()
            )
            run.assert_called_once()
            self.assertEqual(
                run.call_args.args[0],
                ["apparmor_parser", "--add", "--skip-cache", str(directory / name)],
            )

    def test_install_requires_root(self):
        with (
            patch.object(security.sys, "platform", "linux"),
            patch.object(security.os, "geteuid", return_value=1000, create=True),
            self.assertRaisesRegex(RuntimeError, "Linux root"),
        ):
            security.install_policy(self.root)

    def test_install_rejects_unprotected_file_before_privileged_parser(self):
        directory = self.root / "installed"
        directory.mkdir()
        (directory / security.profile_name(self.root)).write_bytes(
            security.profile_text(self.root).encode()
        )
        with (
            patch.object(security, "PROFILE_DIRECTORY", directory),
            patch.object(security.sys, "platform", "linux"),
            patch.object(security.os, "geteuid", return_value=0, create=True),
            patch.object(security, "docker_uses_apparmor", return_value=True),
            patch.object(
                security, "verify_installed_profile", side_effect=RuntimeError("unprotected policy")
            ),
            patch.object(security.subprocess, "run") as run,
            self.assertRaisesRegex(RuntimeError, "unprotected"),
        ):
            security.install_policy(self.root)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
