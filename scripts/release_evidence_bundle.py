"""Build, verify and publish exact release evidence bundles without replacing assets."""

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError

from release_baseline import MANIFEST_NAME, MAX_ARTIFACT_BYTES, BaselineUnavailable, ReleaseEvidence
from release_manifest import COMMIT_RE, validate, verify_rc_acceptance
from worker_image_audit import BOM_NAME, SUMMARY_NAME, inspect_bom

ASSET = "matplobbot-release-evidence.zip"
RECEIPT = "release-evidence.json"
SIGNER_WORKFLOW = ".github/workflows/worker-image-audit.yml"
RELEASE_TAG = re.compile(r"v\d+\.\d+\.\d+")
SHA_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
FILES = {RECEIPT, MANIFEST_NAME, SUMMARY_NAME, BOM_NAME}


def tag_commit(source, tag):
    if not RELEASE_TAG.fullmatch(tag):
        raise ValueError("Expected a stable product tag such as v1.2.0")
    ref = source.get(f"/git/ref/tags/{tag}")
    if ref["ref"] != f"refs/tags/{tag}":
        raise ValueError("GitHub returned a different tag reference")
    obj = ref["object"]
    if obj["type"] == "tag" and COMMIT_RE.fullmatch(obj["sha"]):
        obj = source.get(f"/git/tags/{obj['sha']}")["object"]
    if obj["type"] != "commit" or not COMMIT_RE.fullmatch(obj["sha"]):
        raise ValueError("Release tag must point directly to a commit or an annotated commit tag")
    return obj["sha"]


def existing_release(source, tag):
    commit = tag_commit(source, tag)
    release = source.get(f"/releases/tags/{tag}")
    if release["tag_name"] != tag or release["prerelease"] is not False:
        raise ValueError("Expected the existing stable GitHub release")
    return release, commit


def evidence_asset(release):
    assets = [item for item in release["assets"] if item.get("name") == ASSET]
    if not assets:
        return None
    if (
        len(assets) != 1
        or type(assets[0].get("id")) is not int
        or assets[0].get("state") != "uploaded"
        or not SHA_DIGEST.fullmatch(assets[0].get("digest", ""))
    ):
        raise ValueError("Invalid existing release evidence asset metadata")
    return assets[0]


def verify_attestation(source, archive, tag, commit, *, attestation=None):
    command = [
        "gh",
        "attestation",
        "verify",
        str(archive),
        "--repo",
        source.repository,
        "--signer-workflow",
        f"{source.repository}/{SIGNER_WORKFLOW}",
        "--deny-self-hosted-runners",
        "--predicate-type",
        "https://slsa.dev/provenance/v1",
    ]
    if attestation is not None:
        command += ["--bundle", str(attestation)]
    # A release event uses a tag ref, while a manual invocation must run on main.
    for policy in (
        ["--source-ref", f"refs/tags/{tag}", "--source-digest", commit],
        ["--source-ref", "refs/heads/main"],
    ):
        if subprocess.run([*command, *policy], capture_output=True, timeout=45).returncode == 0:
            return
    raise ValueError("Release evidence lacks an attestation from the trusted publication workflow")


def verify_bundle(raw, tag, commit):
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        members = bundle.infolist()
        if (
            len(members) != len(FILES)
            or {item.filename for item in members} != FILES
            or sum(item.file_size for item in members) > MAX_ARTIFACT_BYTES
        ):
            raise ValueError("Unexpected release evidence ZIP members")
        receipt, manifest, summary, bom = (
            json.loads(bundle.read(name))
            for name in (RECEIPT, MANIFEST_NAME, SUMMARY_NAME, BOM_NAME)
        )
    validate(manifest)
    verify_rc_acceptance(manifest)
    if (
        receipt.get("format") != 1
        or receipt.get("tag") != tag
        or manifest["commit"] != commit
        or receipt.get("commit") != commit
        or receipt.get("worker") != manifest["images"]["worker"]
        or type(receipt.get("run_id")) is not int
        or str(receipt["run_id"]) != str(manifest.get("ci_run"))
        or type(receipt.get("deployment_job_id")) is not int
        or not SHA_DIGEST.fullmatch(receipt.get("artifact_digest", ""))
        or summary.get("commit") != commit
        or summary.get("image") != receipt["worker"]
        or summary.get("evidence_run_id") != receipt["run_id"]
        or summary.get("status") != "passed"
        or summary.get("findings_policy") != "report_only"
    ):
        raise ValueError(
            "Release evidence differs from the accepted tag, deployment or worker image"
        )
    version = summary.get("scanner_version", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid evidence scanner version")
    details = inspect_bom(bom, manifest, scanner_version=version)
    if not all(details["inventory"].values()) or any(
        summary.get(key) != value for key, value in details.items()
    ):
        raise ValueError("Release worker inventory differs from its audited summary")
    return {"status": "passed", **receipt, "manifest": manifest}


def read_published(source, asset, tag, commit):
    raw = source.read(
        f"/releases/assets/{asset['id']}", MAX_ARTIFACT_BYTES, accept="application/octet-stream"
    )
    if asset["digest"] != "sha256:" + hashlib.sha256(raw).hexdigest():
        raise ValueError("Release bundle differs from its asset checksum")
    with tempfile.TemporaryDirectory(prefix="mpb-release-evidence-") as directory:
        archive = Path(directory) / ASSET
        archive.write_bytes(raw)
        verify_attestation(source, archive, tag, commit)
    return verify_bundle(raw, tag, commit)


def select(source, *, tag=None, run_id=None, prefer_published=False):
    if tag:
        release, commit = existing_release(source, tag)
        if asset := evidence_asset(release):
            read_published(source, asset, tag, commit)
            return {"status": "already_published", "tag": tag}
        if release.get("immutable"):
            raise ValueError("The published release is immutable and has no evidence attachment")
        return {**source.resolve(commit=commit), "publication_tag": tag}
    if prefer_published:
        try:
            release = source.get("/releases/latest")
        except HTTPError as exc:
            if exc.code != 404:
                raise
        else:
            if asset := evidence_asset(release):
                if release.get("draft") is not False or release.get("prerelease") is not False:
                    raise ValueError("Expected published stable release evidence")
                tag = release["tag_name"]
                return read_published(source, asset, tag, tag_commit(source, tag))
    return source.resolve(run_id=run_id)


def pack(baseline_path, audit_directory, output):
    baseline = json.loads(baseline_path.read_bytes())
    manifest = baseline["manifest"]
    receipt = {
        "format": 1,
        "tag": baseline["publication_tag"],
        "commit": manifest["commit"],
        "worker": manifest["images"]["worker"],
        "run_id": baseline["run_id"],
        "deployment_job_id": baseline["deployment_job_id"],
        "artifact_digest": baseline["artifact_digest"],
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(RECEIPT, json.dumps(receipt, indent=2) + "\n")
        bundle.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2) + "\n")
        for filename in (SUMMARY_NAME, BOM_NAME):
            bundle.write(audit_directory / filename, filename)
    archive = stream.getvalue()
    verify_bundle(archive, receipt["tag"], receipt["commit"])
    output.write_bytes(archive)


def publish(source, tag, archive, *, attestation=None):
    if archive.name != ASSET:
        raise ValueError("Unexpected release attachment name")
    release, commit = existing_release(source, tag)
    if asset := evidence_asset(release):
        read_published(source, asset, tag, commit)
        return
    if release.get("immutable"):
        raise ValueError("The published release cannot accept evidence attachments")
    verify_bundle(archive.read_bytes(), tag, commit)
    verify_attestation(source, archive, tag, commit, attestation=attestation)
    subprocess.run(
        ["gh", "release", "upload", tag, str(archive), "--repo", source.repository],
        check=True,
        timeout=120,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    resolve = sub.add_parser("select")
    mode = resolve.add_mutually_exclusive_group()
    mode.add_argument("--tag")
    mode.add_argument("--run-id", type=int)
    mode.add_argument("--prefer-published", action="store_true")
    resolve.add_argument("--output", type=Path, required=True)
    create = sub.add_parser("pack")
    create.add_argument("--baseline", type=Path, required=True)
    create.add_argument("--audit-directory", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    upload = sub.add_parser("publish")
    upload.add_argument("--tag", required=True)
    upload.add_argument("--archive", type=Path, required=True)
    upload.add_argument("--attestation", type=Path)
    args = parser.parse_args()
    if args.command == "pack":
        args.output.unlink(missing_ok=True)
        pack(args.baseline, args.audit_directory, args.output)
        return
    source = ReleaseEvidence(os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GH_TOKEN", ""))
    if args.command == "publish":
        publish(source, args.tag, args.archive, attestation=args.attestation)
        return
    args.output.unlink(missing_ok=True)
    try:
        result = select(
            source, tag=args.tag, run_id=args.run_id, prefer_published=args.prefer_published
        )
    except BaselineUnavailable:
        result = {
            "status": "error" if args.tag else "unsupported",
            "reason": "accepted_release_evidence_unavailable",
        }
    except (
        OSError,
        URLError,
        ValueError,
        TypeError,
        KeyError,
        zipfile.BadZipFile,
        subprocess.SubprocessError,
    ):
        result = {"status": "error", "reason": "release_source_unavailable_or_invalid"}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Worker release evidence: {result['status']}")
    raise SystemExit(int(result["status"] == "error"))


if __name__ == "__main__":
    main()
