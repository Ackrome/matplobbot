"""Test a deployed previous release on a disposable candidate PostgreSQL schema."""

import argparse
import json
import os
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from rc_acceptance import build_compose, wait_api
from rc_probe import CANDIDATE_STATE
from release_manifest import sha256, validate, verify, verify_local_images, verify_rc_acceptance
from worker_security import apparmor_security_option

POLICY_FILES = (
    "docker-compose.prod.yml",
    "security/worker-apparmor.template",
    "security/worker-seccomp.json",
)
SERVICE_PROBES = ("api", "worker", "scheduler")


def previous_policy(root, work, previous):
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", previous["commit"], "HEAD"],
        cwd=root,
        check=True,
    )
    for path in POLICY_FILES:
        target = work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            subprocess.check_output(["git", "show", f"{previous['commit']}:{path}"], cwd=root)
        )
        if sha256(target) != previous["files"].get(path):
            raise ValueError("Previous worker policy differs from accepted release")
    return apparmor_security_option(work)


def test_transition(root, previous, candidate, report):
    report["phase"] = "verify_immutable_images"
    for ref in previous["images"].values():
        subprocess.run(["docker", "pull", ref], check=True, timeout=480)
    for manifest in (previous, candidate):
        verify_local_images(manifest)
    project = "mpb-compat-" + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix=project + "-") as directory:
        work = Path(directory)
        worker_policy = previous_policy(root, work, previous)
        config = build_compose(previous["images"], work, worker_policy)
        config["services"]["candidate-migrator"] = {
            **config["services"]["migrator"],
            "image": candidate["images"]["bot"],
        }
        config["services"]["candidate-api"] = {
            **config["services"]["api"],
            "image": candidate["images"]["api"],
            "environment": {
                **config["services"]["api"]["environment"],
                "MPB_RC_CANDIDATE_API": "1",
                "PUBLIC_API_URL": "http://candidate-api:9583",
                "PUBLIC_SITE_URL": "http://candidate-api:9583",
            },
        }
        config_path = work / "compose.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        compose = [
            "docker",
            "compose",
            "--project-directory",
            str(work),
            "-p",
            project,
            "-f",
            str(config_path),
        ]

        def execute(*command, timeout=120, **kwargs):
            return subprocess.run(
                [*compose, *command],
                check=True,
                stdin=subprocess.DEVNULL,
                timeout=timeout,
                **kwargs,
            )

        def observed_heads():
            result = execute(
                "exec",
                "-T",
                "postgres",
                "sh",
                "-ec",
                'PGPASSWORD="$POSTGRES_PASSWORD" psql -XAtw -h 127.0.0.1 -U "$POSTGRES_USER" '
                '-d "$POSTGRES_DB" -c "SELECT version_num FROM alembic_version ORDER BY version_num"',
                capture_output=True,
                text=True,
            )
            return result.stdout.splitlines()

        def probe(service, phase, *, timeout=180):
            execute("exec", "-T", service, "python", "/tmp/rc_probe.py", phase, timeout=timeout)

        try:
            report["phase"] = "seed_previous_release"
            execute(
                "up", "-d", "--wait", "--wait-timeout", "90", "--pull", "never", "postgres", "redis"
            )
            execute("run", "--rm", "--pull", "never", "migrator", timeout=180)
            report["observed_previous_schema_heads"] = observed_heads()
            if report["observed_previous_schema_heads"] != previous["schema_heads"]:
                raise ValueError("Previous migration did not create the accepted schema")
            execute("up", "-d", "--pull", "never", *SERVICE_PROBES)
            wait_api(compose)
            for service in ("api", "scheduler"):
                execute("cp", str(root / "scripts/rc_probe.py"), f"{service}:/tmp/rc_probe.py")
            probe("api", "rollback_before")
            probe("scheduler", "rollback_seed_outbox")

            report["phase"] = "upgrade_candidate_schema"
            execute("stop", *SERVICE_PROBES)
            execute("run", "--rm", "--pull", "never", "candidate-migrator", timeout=180)
            report["observed_candidate_schema_heads"] = observed_heads()
            if report["observed_candidate_schema_heads"] != candidate["schema_heads"]:
                raise ValueError("Candidate migration did not create the accepted schema")

            report["phase"] = "candidate_api_writes"
            execute("up", "-d", "--pull", "never", "candidate-api")
            wait_api(compose, "candidate-api")
            execute("cp", str(root / "scripts/rc_probe.py"), "candidate-api:/tmp/rc_probe.py")
            probe("candidate-api", "rollback_candidate_write")
            handoff = work / CANDIDATE_STATE.name
            execute("cp", f"candidate-api:{CANDIDATE_STATE.as_posix()}", str(handoff))
            execute("stop", "candidate-api")

            report["phase"] = "previous_runtime_on_candidate_schema"
            execute("start", *SERVICE_PROBES)
            wait_api(compose)
            execute("cp", str(handoff), f"api:{CANDIDATE_STATE.as_posix()}")
            probe("api", "rollback_after", timeout=300)
            probe("scheduler", "rollback_deliver_outbox")
            if observed_heads() != candidate["schema_heads"]:
                raise ValueError("Previous runtime changed the candidate schema head")
            report["checks"] = [
                "previous sessions and durable revocation",
                "previous Studio reads, updates and renders candidate-written project",
                "previous calendar API updates and deduplicates candidate-written profile",
                "pending previous schedule delivery retries through isolated fake Telegram and deduplicates",
            ]
        finally:
            execute("down", "--volumes", "--remove-orphans", timeout=90)


def compatibility(root, args, report):
    if not args.manifest.is_file():
        return {"status": "skipped", "reason": "candidate_acceptance_unavailable"}
    candidate = validate(json.loads(args.manifest.read_bytes()))
    verify(candidate, root, require_rc=True)
    report.update(
        candidate_commit=candidate["commit"], candidate_schema_heads=candidate["schema_heads"]
    )
    baseline = json.loads(args.previous.read_bytes())
    if baseline.get("status") == "unsupported":
        return {"status": "unsupported", "reason": "previous_accepted_release_unavailable"}
    if baseline.get("status") != "passed":
        return {"status": "error", "reason": "previous_release_evidence_invalid"}
    previous = validate(baseline["manifest"])
    verify_rc_acceptance(previous)
    if previous["commit"] == candidate["commit"]:
        raise ValueError("Previous release is the candidate")
    report.update(
        previous_commit=previous["commit"],
        previous_schema_heads=previous["schema_heads"],
        previous_images=previous["images"],
        candidate_images=candidate["images"],
    )
    if previous["schema_heads"] == candidate["schema_heads"]:
        return {"status": "skipped", "reason": "schema_unchanged"}
    test_transition(root, previous, candidate, report)
    return {"status": "passed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--previous", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.unlink(missing_ok=True)
    report = {
        "version": 1,
        "status": "error",
        "started_at": datetime.now(UTC).isoformat(),
        "phase": "select_releases",
    }
    try:
        report.update(compatibility(Path.cwd(), args, report))
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as exc:
        reason = (
            "previous_runtime_compatibility_not_verified"
            if report["phase"] == "previous_runtime_on_candidate_schema"
            else "rollback_rehearsal_error"
        )
        report.update(reason=reason, error_type=type(exc).__name__)
        print(f"Rollback compatibility: {reason} ({type(exc).__name__})")
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    message = (
        f"Rollback compatibility: {report['status']} ({report.get('reason', report['phase'])})"
    )
    print(message)
    if summary := os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as step_summary:
            step_summary.write(message + "\n")
    raise SystemExit(int(report["status"] == "error"))


if __name__ == "__main__":
    main()
