"""Test exact release selection, advisory rollback evidence and worker SBOM binding."""

import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rc_rollback_compat
import release_baseline
import release_evidence_bundle
import worker_image_audit
from release_manifest import SERVICES


def accepted(commit="a" * 40, head="revision-a", run_id=100):
    images = {key: f"ghcr.io/ackrome/matplobbot-{key}@sha256:" + commit[0] * 64 for key in SERVICES}
    return {
        "format": 1,
        "commit": commit,
        "schema_heads": [head],
        "ci_run": str(run_id),
        "images": images,
        "files": {"deploy.sh": "a" * 64},
        "acceptance": {
            "status": "passed",
            "restore_verified": True,
            "commit": commit,
            "images": images,
        },
    }


def archive_manifest(manifest):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as artifact:
        artifact.writestr(release_baseline.MANIFEST_NAME, json.dumps(manifest))
    return stream.getvalue()


class TrustedReleaseTests(unittest.TestCase):
    def test_resolves_the_exact_artifact_of_a_successful_smoke_job(self):
        data = accepted()
        draft = {
            "status": "completed",
            "head_repository": {"full_name": "Ackrome/matplobbot"},
            "head_branch": "main",
            "head_sha": data["commit"],
            "event": "push",
            "path": release_baseline.WORKFLOW,
            "id": 100,
        }
        artifact = archive_manifest(data)
        name = "accepted-release-" + data["commit"]
        source = release_baseline.ReleaseEvidence("Ackrome/matplobbot", "test-token")
        response = {
            "/actions/runs/100": draft,
            "/actions/runs/100/jobs?filter=latest&per_page=100": {
                "jobs": [
                    {
                        "name": release_baseline.DEPLOY_JOB,
                        "conclusion": "success",
                        "id": 222,
                        "completed_at": "2026-01-01T00:00:00Z",
                    }
                ]
            },
            f"/actions/runs/100/artifacts?name={name}": {
                "artifacts": [
                    {
                        "name": name,
                        "id": 333,
                        "expired": False,
                        "digest": "sha256:" + hashlib.sha256(artifact).hexdigest(),
                    }
                ]
            },
        }
        with (
            patch.object(source, "get", side_effect=response.__getitem__),
            patch.object(source, "read", return_value=artifact) as download,
        ):
            self.assertEqual(source.resolve(run_id=100)["manifest"], data)
            download.assert_called_once_with(
                "/actions/artifacts/333/zip", release_baseline.MAX_ARTIFACT_BYTES
            )
        with (
            patch.object(source, "get", side_effect=response.__getitem__),
            patch.object(source, "read", return_value=b"foreign"),
        ):
            with self.assertRaisesRegex(ValueError, "checksum"):
                source.resolve(run_id=100)
        draft["event"] = "pull_request"
        with (
            patch.object(source, "get", side_effect=response.__getitem__),
            patch.object(source, "read") as download,
        ):
            with self.assertRaises(release_baseline.BaselineUnavailable):
                source.resolve(run_id=100)
            download.assert_not_called()

    def test_never_redirects_the_github_token_to_the_artifact_server(self):
        request = Request("https://api.github.com/example")
        request.add_unredirected_header("Authorization", "Bearer secret")
        redirect = release_baseline.HttpsRedirects()
        result = redirect.redirect_request(
            request, None, 302, "Moved", {}, "https://artifacts.example/a"
        )
        self.assertFalse(result.has_header("Authorization"))
        with self.assertRaises(ValueError):
            redirect.redirect_request(request, None, 302, "Moved", {}, "http://artifacts.example/a")


class CompatibilityEvidenceTests(unittest.TestCase):
    def test_same_schema_skips_and_different_heads_run_real_transition_entrypoint(self):
        candidate, previous = accepted(), accepted(commit="b" * 40)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(manifest=root / "candidate.json", previous=root / "prior.json")
            args.manifest.write_text(json.dumps(candidate), encoding="utf-8")
            prior_evidence = {"status": "passed", "manifest": previous}
            args.previous.write_text(json.dumps(prior_evidence), encoding="utf-8")
            report = {}
            with (
                patch.object(rc_rollback_compat, "verify"),
                patch.object(rc_rollback_compat, "test_transition") as transition,
            ):
                result = rc_rollback_compat.compatibility(root, args, report)
                self.assertEqual(result, {"status": "skipped", "reason": "schema_unchanged"})
                transition.assert_not_called()
                previous["schema_heads"] = ["old-schema"]
                args.previous.write_text(json.dumps(prior_evidence), encoding="utf-8")
                result = rc_rollback_compat.compatibility(root, args, report)
                self.assertEqual(result, {"status": "passed"})
                transition.assert_called_once_with(root, previous, candidate, report)
                self.assertEqual(report["candidate_schema_heads"], ["revision-a"])
                self.assertEqual(report["previous_schema_heads"], ["old-schema"])


class WorkerAuditTests(unittest.TestCase):
    @staticmethod
    def create_bom(manifest):
        return {
            "bomFormat": "CycloneDX",
            "metadata": {
                "component": {
                    "type": "container",
                    "name": manifest["images"]["worker"],
                    "properties": [
                        {
                            "name": "aquasecurity:trivy:Labels:org.opencontainers.image.revision",
                            "value": manifest["commit"],
                        }
                    ],
                },
                "tools": {
                    "components": [{"name": "trivy", "version": worker_image_audit.SCANNER_VERSION}]
                },
            },
            "components": [
                {"purl": "pkg:deb/debian/chromium@1"},
                {"purl": "pkg:deb/debian/texlive-latex-base@1"},
                {"purl": "pkg:npm/%40mermaid-js/mermaid-cli@1"},
            ],
            "vulnerabilities": [{"id": "synthetic-finding"}],
        }

    def test_vulnerabilities_are_report_only_but_incomplete_inventory_is_an_error(self):
        manifest = accepted()
        bom = self.create_bom(manifest)
        baseline = {"status": "passed", "manifest": manifest, "run_id": 100}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def scanner(command, **_kwargs):
                self.assertIn("remote", command)
                self.assertEqual(command[-1], manifest["images"]["worker"])
                Path(command[command.index("--output") + 1]).write_text(
                    json.dumps(bom), encoding="utf-8"
                )

            with patch.object(worker_image_audit.subprocess, "run", side_effect=scanner):
                report = worker_image_audit.audit(baseline, Path("trivy"), root, {})
                self.assertEqual(report["status"], "passed")
                self.assertEqual(report["vulnerabilities_count"], 1)
                output = root / worker_image_audit.BOM_NAME
                self.assertTrue(output.is_file())
                output.unlink()
                bom["components"].pop()
                self.assertEqual(
                    worker_image_audit.audit(baseline, Path("trivy"), root, {})["status"], "error"
                )
                self.assertFalse(output.exists())

    def test_foreign_digest_cannot_be_published(self):
        manifest = accepted()
        bom = self.create_bom(manifest)
        bom["metadata"]["component"]["name"] = "wrong-digest"
        with self.assertRaisesRegex(ValueError, "accepted worker digest"):
            worker_image_audit.inspect_bom(bom, manifest)

    def test_unavailable_baseline_writes_a_skip_without_reusing_a_previous_sbom(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.json"
            baseline.write_text('{"status": "unsupported"}', encoding="utf-8")
            (root / worker_image_audit.BOM_NAME).write_text("stale", encoding="utf-8")
            args = [
                "worker_image_audit",
                "--baseline",
                str(baseline),
                "--scanner",
                "unused",
                "--output-dir",
                str(root),
            ]
            with patch.object(sys, "argv", args):
                with self.assertRaises(SystemExit) as stopped:
                    worker_image_audit.main()
            self.assertEqual(stopped.exception.code, 0)
            self.assertFalse((root / worker_image_audit.BOM_NAME).exists())
            report = json.loads((root / worker_image_audit.SUMMARY_NAME).read_bytes())
            self.assertEqual(report["status"], "skipped")


class VersionedEvidenceTests(unittest.TestCase):
    def test_tag_peels_one_annotated_tag_and_pack_binds_evidence_to_exact_worker(self):
        manifest = accepted()
        tag = "v1.2.0"
        annotated_sha = "b" * 40
        source = release_baseline.ReleaseEvidence("Ackrome/matplobbot", "fixture")
        refs = {
            f"/git/ref/tags/{tag}": {
                "ref": f"refs/tags/{tag}",
                "object": {"type": "tag", "sha": annotated_sha},
            },
            f"/git/tags/{annotated_sha}": {"object": {"type": "commit", "sha": manifest["commit"]}},
        }
        with patch.object(source, "get", side_effect=refs.__getitem__):
            self.assertEqual(release_evidence_bundle.tag_commit(source, tag), manifest["commit"])
            with self.assertRaises(ValueError):
                release_evidence_bundle.tag_commit(source, "refs/heads/main")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.json"
            baseline.write_text(
                json.dumps(
                    {
                        "manifest": manifest,
                        "publication_tag": tag,
                        "run_id": 100,
                        "deployment_job_id": 999,
                        "artifact_digest": "sha256:" + "a" * 64,
                    }
                ),
                encoding="utf-8",
            )
            bom = WorkerAuditTests.create_bom(manifest)
            (root / worker_image_audit.BOM_NAME).write_text(json.dumps(bom), encoding="utf-8")
            summary = {
                **worker_image_audit.inspect_bom(bom, manifest),
                "status": "passed",
                "commit": manifest["commit"],
                "image": manifest["images"]["worker"],
                "evidence_run_id": 100,
                "findings_policy": "report_only",
                "scanner_version": worker_image_audit.SCANNER_VERSION,
            }
            (root / worker_image_audit.SUMMARY_NAME).write_text(
                json.dumps(summary), encoding="utf-8"
            )
            archive = root / release_evidence_bundle.ASSET
            release_evidence_bundle.pack(baseline, root, archive)
            result = release_evidence_bundle.verify_bundle(
                archive.read_bytes(), tag, manifest["commit"]
            )
            self.assertEqual(result["worker"], manifest["images"]["worker"])
            with self.assertRaises(ValueError):
                release_evidence_bundle.verify_bundle(archive.read_bytes(), tag, "c" * 40)

    def test_prefers_verified_release_and_falls_back_only_when_asset_absent(self):
        source = release_baseline.ReleaseEvidence("Ackrome/matplobbot", "fixture")
        tag = "v1.2.0"
        asset = {
            "name": release_evidence_bundle.ASSET,
            "id": 5,
            "state": "uploaded",
            "digest": "sha256:" + "a" * 64,
        }
        release = {"tag_name": tag, "draft": False, "prerelease": False, "assets": [asset]}
        with (
            patch.object(source, "get", return_value=release),
            patch.object(
                source, "resolve", return_value={"status": "passed", "fallback": True}
            ) as fallback,
            patch.object(release_evidence_bundle, "tag_commit", return_value="a" * 40),
            patch.object(
                release_evidence_bundle, "read_published", side_effect=ValueError("invalid receipt")
            ),
        ):
            with self.assertRaises(ValueError):
                release_evidence_bundle.select(source, prefer_published=True)
            fallback.assert_not_called()
            release["assets"] = []
            self.assertTrue(
                release_evidence_bundle.select(source, prefer_published=True)["fallback"]
            )

    def test_republishing_an_existing_attested_asset_performs_no_upload(self):
        source = release_baseline.ReleaseEvidence("Ackrome/matplobbot", "fixture")
        release = {
            "assets": [
                {
                    "name": release_evidence_bundle.ASSET,
                    "id": 5,
                    "state": "uploaded",
                    "digest": "sha256:" + "a" * 64,
                }
            ]
        }
        with (
            patch.object(
                release_evidence_bundle, "existing_release", return_value=(release, "a" * 40)
            ),
            patch.object(release_evidence_bundle, "read_published") as verified,
            patch.object(release_evidence_bundle.subprocess, "run") as upload,
        ):
            release_evidence_bundle.publish(source, "v1.2.0", Path(release_evidence_bundle.ASSET))
            verified.assert_called_once()
            upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
