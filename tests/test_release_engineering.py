"""Manifest tampering, deployment failure and rollback safety contracts."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import jenkins_release_parameters
import release_backup
import release_deploy
import release_manifest
from rc_acceptance import build_compose

JENKINS_SCM = b'<definition class="org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition" plugin="workflow-cps"><scm class="hudson.plugins.git.GitSCM"><userRemoteConfigs><hudson.plugins.git.UserRemoteConfig><url>https://github.com/Ackrome/matplobbot</url><credentialsId>preserved-id</credentialsId></hudson.plugins.git.UserRemoteConfig></userRemoteConfigs><branches><hudson.plugins.git.BranchSpec><name>*/main</name></hudson.plugins.git.BranchSpec></branches></scm><scriptPath>Jenkinsfile.groovy</scriptPath><lightweight>true</lightweight></definition>'


def manifest():
    return {
        "format": 1,
        "commit": "a" * 40,
        "schema_heads": ["head"],
        "files": {"deploy.sh": "b" * 64},
        "images": {
            key: f"ghcr.io/ackrome/matplobbot-{key}@sha256:" + "c" * 64
            for key in release_manifest.SERVICES
        },
    }


class TestReleaseEngineering(unittest.TestCase):
    def test_jenkins_parameter_migration_preserves_job_and_is_idempotent(self):
        import xml.etree.ElementTree as ET

        xml = (
            b'<flow-definition plugin="workflow-job"><description>Keep me</description><properties><hudson.model.ParametersDefinitionProperty><parameterDefinitions><hudson.model.StringParameterDefinition><name>DEPLOY_HOST</name><defaultValue>private-host</defaultValue></hudson.model.StringParameterDefinition></parameterDefinitions></hudson.model.ParametersDefinitionProperty></properties>'
            + JENKINS_SCM
            + b"</flow-definition>"
        )
        changed, names = jenkins_release_parameters.configure(xml)
        self.assertEqual(
            set(names), {"SOURCE_COMMIT", "RELEASE_MANIFEST_B64", "SCM_BRANCH", "FULL_SCM_CHECKOUT"}
        )
        root = ET.fromstring(changed)
        self.assertEqual(root.attrib, {"plugin": "workflow-job"})
        self.assertEqual(root.findtext("definition/scriptPath"), "Jenkinsfile.groovy")
        self.assertEqual(
            root.findtext("definition/scm/branches/hudson.plugins.git.BranchSpec/name"),
            "${SOURCE_COMMIT}",
        )
        self.assertEqual(root.findtext("definition/lightweight"), "false")
        self.assertEqual(
            root.findtext(
                "definition/scm/userRemoteConfigs/hudson.plugins.git.UserRemoteConfig/credentialsId"
            ),
            "preserved-id",
        )
        self.assertEqual(
            root.findtext(
                "properties/hudson.model.ParametersDefinitionProperty/parameterDefinitions/hudson.model.StringParameterDefinition/defaultValue"
            ),
            "private-host",
        )
        self.assertEqual(jenkins_release_parameters.configure(changed)[1], [])
        conflicting = changed.replace(
            b"hudson.model.TextParameterDefinition", b"hudson.model.StringParameterDefinition"
        )
        with self.assertRaisesRegex(ValueError, "unexpected parameter type"):
            jenkins_release_parameters.configure(conflicting)

    def test_jenkins_dry_run_concurrent_edit_and_verified_apply(self):
        from unittest.mock import Mock

        original = b"<flow-definition><properties />" + JENKINS_SCM + b"</flow-definition>"
        fetch = Mock(return_value=original)
        missing = jenkins_release_parameters.install(fetch, "http://jenkins/job/app")
        self.assertEqual(len(missing), 4)
        self.assertEqual(fetch.call_count, 1)
        fetch = Mock(side_effect=[original, b"<changed/>"])
        with self.assertRaisesRegex(RuntimeError, "changed during"):
            jenkins_release_parameters.install(fetch, "http://jenkins/job/app", True)
        self.assertEqual(fetch.call_count, 2)
        configured, _ = jenkins_release_parameters.configure(original)
        fetch = Mock(
            side_effect=[
                original,
                original,
                b'{"crumbRequestField":"Jenkins-Crumb","crumb":"synthetic"}',
                b"",
                configured,
            ]
        )
        jenkins_release_parameters.install(fetch, "http://jenkins/job/app", True)
        posted = fetch.call_args_list[3]
        self.assertEqual(posted.kwargs["data"], configured)
        self.assertEqual(posted.kwargs["headers"], {"Jenkins-Crumb": "synthetic"})

    def test_jenkins_scm_migration_rejects_unexpected_config_and_clears_defaults(self):
        import xml.etree.ElementTree as ET

        original = b"<flow-definition><properties />" + JENKINS_SCM + b"</flow-definition>"
        for old, new in (
            (b"*/main", b"*/another-branch"),
            (b"Jenkinsfile.groovy", b"other.groovy"),
            (b"hudson.plugins.git.GitSCM", b"OtherSCM"),
        ):
            with self.subTest(new=new), self.assertRaises(ValueError):
                jenkins_release_parameters.configure(original.replace(old, new))
        configured, _ = jenkins_release_parameters.configure(original)
        root = ET.fromstring(configured)
        for item in root.findall(
            "properties/hudson.model.ParametersDefinitionProperty/parameterDefinitions/*"
        ):
            item.find("defaultValue").text = "stale-release-value"
        corrected, changes = jenkins_release_parameters.configure(ET.tostring(root))
        self.assertIn("SOURCE_COMMIT_EMPTY_DEFAULT", changes)
        self.assertIn("RELEASE_MANIFEST_B64_EMPTY_DEFAULT", changes)
        self.assertNotIn(b"stale-release-value", corrected)

    def test_rejects_mutable_missing_and_mismatched_images(self):
        valid = manifest()
        release_manifest.validate(valid)
        for change in (
            lambda d: d["images"].pop("api"),
            lambda d: d["images"].update(api="ghcr.io/ackrome/matplobbot-api:latest"),
            lambda d: d["images"].update(api=d["images"]["worker"]),
        ):
            data = manifest()
            change(data)
            with self.assertRaises(ValueError):
                release_manifest.validate(data)

    def test_tampered_source_schema_and_rc_images_are_rejected(self):
        data = manifest()
        with (
            patch.object(release_manifest, "run", side_effect=[data["commit"], "", ""]),
            patch.object(release_manifest, "source_files", return_value={}),
            patch.object(release_manifest, "schema_heads", return_value=["head"]),
        ):
            with self.assertRaisesRegex(ValueError, "Deploy inputs"):
                release_manifest.verify(data, ROOT)
        data["acceptance"] = {
            "status": "passed",
            "restore_verified": True,
            "commit": data["commit"],
            "images": {},
        }
        with (
            patch.object(release_manifest, "run", side_effect=[data["commit"], "", ""]),
            patch.object(release_manifest, "source_files", return_value=data["files"]),
            patch.object(release_manifest, "schema_heads", return_value=["head"]),
        ):
            with self.assertRaisesRegex(ValueError, "no successful RC"):
                release_manifest.verify(data, ROOT, require_rc=True)

    def test_migration_heads_parse_without_importing_migration_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            versions = root / "alembic/versions"
            versions.mkdir(parents=True)
            (versions / "a.py").write_text(
                "revision='a'\ndown_revision=None\nraise RuntimeError('must not run')\n",
                encoding="utf-8-sig",
            )
            (versions / "b.py").write_text("revision: str='b'\ndown_revision: str='a'\n")
            self.assertEqual(release_manifest.schema_heads(root), ["b"])
            (versions / "c.py").write_text("revision='c'\ndown_revision='a'\n")
            with self.assertRaises(ValueError):
                release_manifest.schema_heads(root)

    def test_current_repository_migrations_parse_to_one_release_head(self):
        self.assertEqual(len(release_manifest.schema_heads(ROOT)), 1)

    def test_untracked_deploy_inputs_rejected_but_runtime_state_allowed(self):
        with patch.object(
            release_manifest,
            "run",
            return_value="scripts/hidden.py\0.env\0.release-state/current.json",
        ):
            with self.assertRaisesRegex(ValueError, "hidden.py"):
                release_manifest.verify_no_untracked_inputs(ROOT)
        with patch.object(
            release_manifest,
            "run",
            return_value=".env\0.release-state/current.json\0scripts/__pycache__/rc.pyc",
        ):
            release_manifest.verify_no_untracked_inputs(ROOT)

    def test_prior_configuration_saved_before_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "MAIL_CREDENTIAL_KEY=old-key\nJWT_SECRET_KEY=old-signing-key\n"
            )
            with (
                patch.object(release_deploy, "ROOT", root),
                patch.object(release_deploy, "STATE", root / ".release-state"),
            ):
                release_deploy.preserve_configuration()
                record = json.loads((root / ".release-state/prior-config.json").read_text())
                (root / ".env").write_text("NEW=config")
                self.assertIn("old-key", (root / record["snapshot"] / ".env").read_text())

    def test_compose_override_binds_migrator_and_all_application_services(self):
        data = manifest()
        config = release_manifest.compose_override(data)
        self.assertEqual(config["services"]["migrator"]["image"], data["images"]["bot"])
        self.assertEqual(len(config["services"]), 5)

    def test_rc_network_has_no_production_config_ports_or_egress(self):
        config = build_compose(manifest()["images"], ROOT)
        self.assertTrue(config["networks"]["isolated"]["internal"])
        postgres_health = config["services"]["postgres"]["healthcheck"]["test"]
        self.assertEqual(postgres_health[0], "CMD-SHELL")
        self.assertIn("-h 127.0.0.1", postgres_health[1])
        self.assertIn('-d "$${POSTGRES_DB}" -c "SELECT 1"', postgres_health[1])
        for service in config["services"].values():
            self.assertNotIn("env_file", service)
            self.assertNotIn("ports", service)
            self.assertNotIn("privileged", service)
        self.assertEqual(config["services"]["worker"]["cap_drop"], ["ALL"])
        self.assertIn("systempaths=unconfined", config["services"]["worker"]["security_opt"])
        for name, service in config["services"].items():
            if name != "worker":
                self.assertNotIn("systempaths=unconfined", service.get("security_opt", []))
        self.assertFalse(
            any("apparmor=" in item for item in config["services"]["worker"]["security_opt"])
        )
        profiled = build_compose(manifest()["images"], ROOT, "apparmor=matplobbot-render-test")
        self.assertEqual(
            [
                item
                for item in profiled["services"]["worker"]["security_opt"]
                if item.startswith("apparmor=")
            ],
            ["apparmor=matplobbot-render-test"],
        )

    def test_runtime_snapshot_preserves_observed_worker_profile(self):
        records = [
            {
                "Image": "sha256:worker",
                "AppArmorProfile": "matplobbot-render-old",
                "Config": {"Labels": {"com.docker.compose.service": "mpb-worker"}},
            }
        ]
        self.assertEqual(
            release_deploy.runtime_overrides(records)["mpb-worker"],
            {"image": "sha256:worker", "security_opt": ["apparmor=matplobbot-render-old"]},
        )
        records[0]["AppArmorProfile"] = "unconfined"
        self.assertEqual(
            release_deploy.runtime_overrides(records)["mpb-worker"]["security_opt"],
            ["apparmor=unconfined"],
        )
        records[0]["AppArmorProfile"] = ""
        self.assertNotIn("security_opt", release_deploy.runtime_overrides(records)["mpb-worker"])

    def test_rollback_profile_probe_failure_precedes_any_service_or_source_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / ".release-state"
            saved = state / "saved"
            saved.mkdir(parents=True)
            (saved / ".env").write_text("KEY=restored")
            (saved / "compose.json").write_text(
                json.dumps(
                    {
                        "services": {
                            "mpb-worker": {
                                "image": "sha256:old",
                                "security_opt": ["apparmor=matplobbot-render-old"],
                            }
                        }
                    }
                )
            )
            (saved / "worker-apparmor.json").write_text(
                json.dumps({"name": "matplobbot-render-old", "text": "retained policy"})
            )
            record = {
                "schema_heads": ["old"],
                "snapshot": ".release-state/saved",
                "manifest": {"commit": "a" * 40},
            }
            for name in ("current", "previous"):
                (state / (name + ".json")).write_text(json.dumps(record))
            with (
                patch.object(release_deploy, "ROOT", root),
                patch.object(release_deploy, "STATE", state),
                patch.object(release_deploy, "heads", return_value=["old"]),
                patch.object(release_deploy, "verify_installed_profile") as verify_policy,
                patch.object(
                    release_deploy, "run_worker_probe", side_effect=RuntimeError("not loaded")
                ) as probe,
                patch.object(release_deploy, "execute") as execute,
            ):
                with self.assertRaisesRegex(RuntimeError, "not loaded"):
                    release_deploy.rollback()
                verify_policy.assert_called_once_with("matplobbot-render-old", "retained policy")
                probe.assert_called_once_with(
                    "sha256:old",
                    saved.resolve() / "worker-seccomp.json",
                    "apparmor=matplobbot-render-old",
                )
                execute.assert_not_called()

    def test_no_apparmor_daemon_probe_omits_the_option(self):
        with (
            patch.object(release_deploy, "apparmor_security_option", return_value=None),
            patch.object(release_deploy, "execute") as execute,
        ):
            release_deploy.probe_worker("worker-image", ROOT)
        self.assertFalse(
            any(str(value).startswith("apparmor=") for value in execute.call_args.args[0])
        )

    def test_restore_checksum_failure_happens_before_any_docker_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "backup.dump"
            dump.write_bytes(b"tampered")
            dump.with_suffix(".json").write_text(json.dumps({"sha256": "0" * 64}))
            with patch.object(release_backup, "command") as command:
                with self.assertRaisesRegex(ValueError, "checksum"):
                    release_backup.restore_drill(dump)
                command.assert_not_called()

    def test_restore_waits_for_target_database_over_tcp_before_loading_dump(self):
        from unittest.mock import Mock

        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "backup.dump"
            dump.write_bytes(b"synthetic dump")
            dump.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "sha256": release_backup.file_sha256(dump),
                        "tables": {},
                        "schema_heads": ["head"],
                    }
                )
            )
            ready = False
            attempts = 0

            def readiness(args, **kwargs):
                nonlocal ready, attempts
                self.assertEqual(args[3:5], ["sh", "-c"])
                self.assertIn("-h 127.0.0.1", args[5])
                self.assertIn('-d "$POSTGRES_DB" -c "SELECT 1"', args[5])
                attempts += 1
                ready = attempts == 3
                return subprocess.CompletedProcess(args, 0 if ready else 2, "1\n" if ready else "")

            def command(args, **kwargs):
                if "pg_restore" in args:
                    self.assertTrue(ready, "Restore must wait for the actual target database")

            with (
                patch.object(release_backup, "command", side_effect=command),
                patch.object(release_backup.subprocess, "run", side_effect=readiness),
                patch.object(release_backup.time, "sleep") as sleep,
                patch.object(
                    release_backup, "Snapshot", return_value=Mock(query=Mock(return_value=["head"]))
                ),
                patch.object(release_backup, "witness", return_value={}),
            ):
                self.assertTrue(release_backup.restore_drill(dump)["restore_verified"])
            self.assertEqual(attempts, 3)
            self.assertEqual(sleep.call_count, 2)

    def test_deploy_bootstrap_failure_never_advances_last_successful(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / ".release-state"
            state.mkdir()
            current = state / "current.json"
            current.write_text('{"previous":"kept"}')
            (state / "attempt.json").write_text(json.dumps({"commit": manifest()["commit"]}))
            (state / "support-compose.json").write_text(
                json.dumps({"services": {"proxy": {"image": "sha256:frozen-proxy"}}})
            )
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest()))
            calls = []

            def execute(command, **kwargs):
                calls.append(command)
                if "fastapi_stats_app.bootstrap_admin" in command:
                    raise subprocess.CalledProcessError(1, command)

            with (
                patch.object(release_deploy, "STATE", state),
                patch.object(release_deploy, "verify"),
                patch.object(release_deploy, "apparmor_security_option", return_value=None),
                patch.object(release_deploy, "run", return_value=""),
                patch.object(
                    release_deploy.subprocess,
                    "run",
                    return_value=type("Result", (), {"returncode": 0})(),
                ),
                patch.object(release_deploy, "execute", side_effect=execute),
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    release_deploy.deploy(path)
            self.assertIn("stop", calls[0])
            self.assertIn("migrator", calls[2])
            self.assertIn("fastapi_stats_app.bootstrap_admin", calls[4])
            self.assertNotIn("--build", calls[3])
            self.assertIn("--no-build", calls[3])
            self.assertEqual(
                json.loads((state / "pending-compose.json").read_text())["services"]["proxy"][
                    "image"
                ],
                "sha256:frozen-proxy",
            )
            self.assertEqual(current.read_text(), '{"previous":"kept"}')
            self.assertFalse((state / "pending.json").exists())

    def test_rollback_schema_mismatch_refuses_before_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            for name in ("current", "previous"):
                (state / (name + ".json")).write_text(json.dumps({"schema_heads": ["old"]}))
            with (
                patch.object(release_deploy, "STATE", state),
                patch.object(release_deploy, "heads", return_value=["new"]),
                patch.object(release_deploy, "execute") as execute,
            ):
                with self.assertRaisesRegex(ValueError, "Schema changed"):
                    release_deploy.rollback()
                execute.assert_not_called()

    def test_prepare_stops_all_host_binds_after_baseline_before_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / ".release-state"
            candidate = root / "candidate"
            (candidate / "scripts").mkdir(parents=True)
            for name in (
                "release_deploy.py",
                "release_manifest.py",
                "release_backup.py",
                "worker_security.py",
            ):
                (candidate / "scripts" / name).write_text("# retained recovery helper")
            path = root / "accepted.json"
            path.write_text(json.dumps(manifest()))
            (root / ".env").write_text("KEY=legacy-secret")
            config = {
                "services": {
                    "frontend": {"volumes": [{"type": "bind"}]},
                    "proxy": {"volumes": [{"type": "bind"}]},
                    "postgres": {"volumes": [{"type": "volume"}]},
                }
            }

            def run(*command, **kwargs):
                if "diff" in command:
                    return ""
                if "ps" in command:
                    return "container"
                if "inspect" in command:
                    return json.dumps(
                        [
                            {
                                "Image": "sha256:legacy-" + name,
                                "Config": {"Labels": {"com.docker.compose.service": name}},
                                "State": {"Running": True},
                            }
                            for name in (
                                "postgres",
                                "redis",
                                "caddy",
                                "main-site-frontend",
                                "proxy",
                            )
                        ]
                    )
                if "rev-parse" in command:
                    return "e" * 40
                if "config" in command:
                    return json.dumps(config)
                raise AssertionError(command)

            seen = []

            def execute(command, **kwargs):
                seen.append(command)
                if "--entrypoint" in command:
                    self.assertFalse((state / "attempt.json").exists())
                    self.assertIn("--read-only", command)
                    self.assertEqual(command[command.index("--network") + 1], "none")
                    self.assertIn("no-new-privileges:true", command)
                    self.assertIn("--cap-drop", command)
                    self.assertIn("systempaths=unconfined", command)
                    self.assertEqual(command.count("apparmor=matplobbot-render-test"), 1)
                    self.assertEqual(kwargs["timeout"], 120)
                if "stop" in command or "checkout" in command:
                    self.assertTrue((state / "attempt.json").exists())
                    baseline = json.loads((state / "current.json").read_text())
                    self.assertTrue(baseline["legacy"])
                    self.assertEqual(
                        (root / baseline["snapshot"] / ".env").read_text(), "KEY=legacy-secret"
                    )
                if "checkout" in command:
                    raise subprocess.CalledProcessError(1, command)

            with (
                patch.object(release_deploy, "ROOT", root),
                patch.object(release_deploy, "STATE", state),
                patch.object(release_deploy, "verify"),
                patch.object(
                    release_deploy,
                    "apparmor_security_option",
                    return_value="apparmor=matplobbot-render-test",
                ),
                patch.object(release_deploy, "verify_no_untracked_inputs"),
                patch.object(release_deploy, "source_files", return_value={"deploy.sh": "a" * 64}),
                patch.object(release_deploy, "heads", return_value=["old"]),
                patch.object(release_deploy, "run", side_effect=run),
                patch.object(release_deploy, "execute", side_effect=execute),
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    release_deploy.prepare(path, candidate)
            self.assertEqual(seen[-2][-3:], ["stop", "frontend", "proxy"])
            self.assertTrue((state / "recovery-tools/release_deploy.py").exists())


if __name__ == "__main__":
    unittest.main()
