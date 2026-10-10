"""Bind a release to source files, schema heads and immutable OCI image digests."""

import argparse
import ast
import base64
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

SERVICES = {
    "bot": "mpb-telegram-bot",
    "api": "mpb-fastapi-stats",
    "scheduler": "mpb-scheduler",
    "worker": "mpb-worker",
}
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
IMAGE_RE = re.compile(r"ghcr\.io/ackrome/matplobbot-(bot|api|scheduler|worker)@sha256:[0-9a-f]{64}")
RELEASE_FILES = (
    "main_site_frontend",
    "alembic",
    "scripts",
    "proxy",
    "docker",
    "security",
    "Caddyfile",
    "docker-compose.prod.yml",
    "deploy.sh",
    "alembic.ini",
    "setup.py",
    "requirements.txt",
    "requirements.in",
    "Jenkinsfile.groovy",
)


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True, encoding="utf-8").strip()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_files(root):
    """Hash tracked deploy inputs; the commit binds all remaining application code."""
    paths = run("git", "ls-files", "-z", cwd=root).split("\0")
    return {
        name: sha256(root / name)
        for name in sorted(paths)
        if name
        and (
            name.startswith("Dockerfile")
            or any(name == prefix or name.startswith(prefix + "/") for prefix in RELEASE_FILES)
        )
    }


def verify_no_untracked_inputs(root):
    # Include ignored files: an ignored JavaScript/Python file can still be loaded.
    names = run("git", "ls-files", "--others", "-z", cwd=root).split("\0")
    affected = [
        name
        for name in names
        if name
        and (
            name.startswith("Dockerfile")
            or any(name == prefix or name.startswith(prefix + "/") for prefix in RELEASE_FILES)
        )
        and "__pycache__" not in Path(name).parts
        and not name.endswith((".pyc", ".pyo"))
    ]
    if affected:
        raise ValueError("Unexpected untracked deploy inputs: " + ", ".join(affected[:10]))


def schema_heads(root):
    revisions, parents = set(), set()
    for path in (root / "alembic/versions").glob("*.py"):
        values = {}
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                        values[target.id] = ast.literal_eval(node.value)
        if values.get("revision"):
            revisions.add(values["revision"])
        parent = values.get("down_revision")
        parents.update(parent if isinstance(parent, (list, tuple)) else [parent] if parent else [])
    heads = sorted(revisions - parents)
    if len(heads) != 1:
        raise ValueError("Release requires exactly one Alembic head")
    return heads


def validate(manifest):
    if manifest.get("format") != 1 or not COMMIT_RE.fullmatch(manifest.get("commit", "")):
        raise ValueError("Invalid release format or full source commit")
    images = manifest.get("images", {})
    if set(images) != set(SERVICES):
        raise ValueError("Exactly four application image digests are required")
    for service, image in images.items():
        match = IMAGE_RE.fullmatch(image)
        if not match or match.group(1) != service:
            raise ValueError(f"Invalid immutable {service} image")
    if not manifest.get("files") or len(manifest.get("schema_heads", [])) != 1:
        raise ValueError("Missing deploy-file hashes or schema head")
    for name, digest in manifest["files"].items():
        if Path(name).is_absolute() or ".." in Path(name).parts or "\\" in name:
            raise ValueError("Unsafe manifest path")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid source-file digest")
    return manifest


def verify(manifest, root, *, inspect_images=False, require_rc=False):
    validate(manifest)
    if run("git", "rev-parse", "HEAD", cwd=root) != manifest["commit"]:
        raise ValueError("Checkout differs from release commit")
    if run("git", "diff", "--name-only", "HEAD", cwd=root):
        raise ValueError("Tracked source differs from release commit")
    verify_no_untracked_inputs(root)
    if source_files(root) != manifest["files"] or schema_heads(root) != manifest["schema_heads"]:
        raise ValueError("Deploy inputs or schema differ from release manifest")
    if require_rc:
        report = manifest.get("acceptance", {})
        if (
            report.get("status") != "passed"
            or report.get("commit") != manifest["commit"]
            or report.get("images") != manifest["images"]
            or not report.get("restore_verified")
        ):
            raise ValueError("This exact release has no successful RC/restore acceptance")
    if inspect_images:
        for ref in manifest["images"].values():
            info = json.loads(run("docker", "image", "inspect", ref))[0]
            if ref not in info.get("RepoDigests", []):
                raise ValueError("Locally pulled image digest differs")
            labels = info.get("Config", {}).get("Labels") or {}
            if labels.get("org.opencontainers.image.revision") != manifest["commit"]:
                raise ValueError("Image source revision differs from release commit")


def compose_override(manifest):
    validate(manifest)
    services = {SERVICES[key]: {"image": ref} for key, ref in manifest["images"].items()}
    services["migrator"] = {"image": manifest["images"]["bot"]}
    return {"services": services}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--commit", required=True)
    create.add_argument("--ci-run", required=True)
    create.add_argument("--image", action="append", required=True)
    create.add_argument("--output", required=True, type=Path)
    decode = sub.add_parser("decode")
    decode.add_argument("--output", required=True, type=Path)
    decode.add_argument("--commit", required=True)
    decode.add_argument("--stdin", action="store_true")
    for name in ("verify", "compose", "attest"):
        cmd = sub.add_parser(name)
        cmd.add_argument("manifest", type=Path)
        if name == "verify":
            cmd.add_argument("--images", action="store_true")
            cmd.add_argument("--require-rc", action="store_true")
        else:
            cmd.add_argument("--output", required=True, type=Path)
        if name == "attest":
            cmd.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    root = Path.cwd()
    if args.command == "create":
        manifest = validate(
            {
                "format": 1,
                "commit": args.commit,
                "ci_run": args.ci_run,
                "created_at": datetime.now(UTC).isoformat(),
                "images": dict(item.split("=", 1) for item in args.image),
                "files": source_files(root),
                "schema_heads": schema_heads(root),
            }
        )
        verify(manifest, root)
        args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    elif args.command == "decode":
        import os
        import sys

        raw = base64.b64decode(
            sys.stdin.read().strip() if args.stdin else os.environ["RELEASE_MANIFEST_B64"],
            validate=True,
        )
        if len(raw) > 2_000_000:
            raise ValueError("Manifest too large")
        manifest = validate(json.loads(raw))
        if args.commit != manifest["commit"]:
            raise ValueError("Jenkins source parameter differs from manifest")
        args.output.write_bytes(raw)
    else:
        manifest = validate(json.loads(args.manifest.read_text(encoding="utf-8")))
        if args.command == "verify":
            verify(manifest, root, inspect_images=args.images, require_rc=args.require_rc)
        elif args.command == "compose":
            args.output.write_text(
                json.dumps(compose_override(manifest), indent=2), encoding="utf-8"
            )
        else:
            report = json.loads(args.report.read_text(encoding="utf-8"))
            manifest["acceptance"] = report
            verify(manifest, root, require_rc=True)
            args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
