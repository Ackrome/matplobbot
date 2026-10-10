"""Deploy immutable manifests; retain successful state and refuse unsafe rollback."""

import argparse
import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from release_backup import backup
from release_manifest import (
    compose_override,
    run,
    source_files,
    validate,
    verify,
    verify_no_untracked_inputs,
)
from worker_security import (
    apparmor_security_option,
    docker_uses_apparmor,
    profile_text,
    verify_installed_profile,
)

ROOT = Path.cwd()
STATE = ROOT / ".release-state"


def write_private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with os.fdopen(
        os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8"
    ) as output:
        json.dump(value, output, indent=2)
    os.replace(temporary, path)


def compose(override):
    return ["docker", "compose", "-f", "docker-compose.prod.yml", "-f", str(override)]


def execute(args, **kwargs):
    subprocess.run(args, check=True, **kwargs)


def runtime_overrides(records):
    """Freeze observed worker profile alongside image identity for recovery."""
    services = {}
    for item in records:
        name = item["Config"]["Labels"]["com.docker.compose.service"]
        services[name] = {"image": item["Image"]}
        if name == "mpb-worker" and item.get("AppArmorProfile"):
            services[name]["security_opt"] = ["apparmor=" + item["AppArmorProfile"]]
    return services


def verify_saved_worker_policy(saved, legacy=False):
    """Check retained profile before stopping services or changing checkout."""
    services = json.loads((saved / "compose.json").read_text(encoding="utf-8"))["services"]
    options = services.get("mpb-worker", {}).get("security_opt", [])
    profiles = [item.removeprefix("apparmor=") for item in options if item.startswith("apparmor=")]
    if len(profiles) > 1:
        raise ValueError("Rollback has multiple worker AppArmor selections")
    if profiles and profiles[0].startswith("matplobbot-render-"):
        policy = json.loads((saved / "worker-apparmor.json").read_text(encoding="utf-8"))
        if policy["name"] != profiles[0]:
            raise ValueError("Rollback worker profile differs from saved policy")
        verify_installed_profile(policy["name"], policy["text"])
    elif not legacy and (profiles or docker_uses_apparmor()):
        raise ValueError("Rollback requires its verified managed worker AppArmor profile")
    return "apparmor=" + profiles[0] if profiles else None


def probe_worker(image, candidate):
    """Positive isolated compile on the destination kernel before live mutation."""
    worker_apparmor = apparmor_security_option(candidate)
    return run_worker_probe(
        image, candidate.resolve() / "security/worker-seccomp.json", worker_apparmor
    )


def run_worker_probe(image, seccomp_path, worker_apparmor):
    """Prove selected profile is loaded and usable, including a rollback target."""
    name = "mpb-release-probe-" + uuid.uuid4().hex[:12]
    script = (
        "import base64;from shared_lib.tasks import compile_full_latex_task;"
        "r=compile_full_latex_task.run(r'\\documentclass{article}\\begin{document}Release host probe\\end{document}');"
        "assert r.get('status')=='success',r;"
        "assert base64.b64decode(r['pdf']).startswith(b'%PDF-');"
        "print('Destination worker sandbox compile passed.')"
    )
    try:
        execute(
            [
                "docker",
                "run",
                "--rm",
                "--name",
                name,
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--security-opt",
                "seccomp=" + str(seccomp_path),
                "--security-opt",
                "systempaths=unconfined",
                *(["--security-opt", worker_apparmor] if worker_apparmor else []),
                "--memory",
                "2g",
                "--pids-limit",
                "256",
                "--tmpfs",
                "/tmp:size=512m,mode=1777",
                "--entrypoint",
                "python",
                image,
                "-c",
                script,
            ],
            timeout=120,
        )
        return worker_apparmor
    except BaseException:
        subprocess.run(
            ["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        raise


def preserve_configuration():
    """Run before Jenkins replaces .env, including the first manifest adoption."""
    saved = STATE / "pre-deploy" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    saved.mkdir(parents=True, mode=0o700)
    for name in (".env", "Caddyfile.local"):
        if (ROOT / name).exists():
            shutil.copyfile(ROOT / name, saved / name)
            (saved / name).chmod(0o600)
    write_private(STATE / "prior-config.json", {"snapshot": str(saved.relative_to(ROOT))})


def prepare(path, candidate):
    """Validate off-line, capture rollback state, then quiesce host binds before checkout."""
    manifest = validate(json.loads(path.read_text(encoding="utf-8")))
    verify(manifest, candidate.resolve(), require_rc=True)
    # Downloads and digest validation happen while the previous site is still live.
    for image in manifest["images"].values():
        execute(["docker", "pull", image])
    verify(manifest, candidate.resolve(), inspect_images=True, require_rc=True)
    worker_apparmor = probe_worker(manifest["images"]["worker"], candidate)
    if (STATE / "attempt.json").exists() or (STATE / "rollback-pending.json").exists():
        raise ValueError("Resolve the previous deployment/rollback attempt before another switch")
    if run("git", "diff", "--name-only", "HEAD", cwd=ROOT):
        raise ValueError("Live checkout has tracked edits")
    verify_no_untracked_inputs(ROOT)
    STATE.mkdir(parents=True, mode=0o700, exist_ok=True)
    preserve_configuration()
    prefix = ["docker", "compose", "-f", "docker-compose.prod.yml"]
    containers = run(*prefix, "ps", "-q").splitlines()
    runtime = json.loads(run("docker", "inspect", *containers)) if containers else []
    support_names = {"postgres", "redis", "caddy", "main-site-frontend", "proxy"}
    support = {
        item["Config"]["Labels"]["com.docker.compose.service"]: {"image": item["Image"]}
        for item in runtime
        if item["Config"]["Labels"]["com.docker.compose.service"] in support_names
        and item.get("State", {}).get("Running")
        and item.get("State", {}).get("Health", {}).get("Status", "healthy") == "healthy"
    }
    if set(support) != support_names:
        raise ValueError(
            "Release requires all five healthy existing support services; bootstrap/repair the support stack separately before an application release"
        )
    write_private(STATE / "support-compose.json", {"services": support})
    if containers and not (STATE / "current.json").exists():
        # First manifest adoption: preserve the observed legacy release without
        # pretending it passed the new acceptance contract.
        saved = STATE / "releases" / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-legacy")
        saved.mkdir(parents=True, mode=0o700)
        write_private(
            saved / "compose.json",
            {"services": runtime_overrides(runtime)},
        )
        for name in (".env", "Caddyfile.local"):
            if (ROOT / name).exists():
                shutil.copyfile(ROOT / name, saved / name)
                (saved / name).chmod(0o600)
        record = {
            "legacy": True,
            "manifest": {"commit": run("git", "rev-parse", "HEAD", cwd=ROOT)},
            "files": source_files(ROOT),
            "schema_heads": heads(prefix),
            "snapshot": str(saved.relative_to(ROOT)),
            "status": "observed-legacy",
        }
        write_private(saved / "release.json", record)
        write_private(STATE / "current.json", record)
    recovery = STATE / "recovery-tools"
    recovery.mkdir(exist_ok=True, mode=0o700)
    for name in (
        "release_deploy.py",
        "release_manifest.py",
        "release_backup.py",
        "worker_security.py",
    ):
        shutil.copyfile(candidate / "scripts" / name, recovery / name)
    # The marker precedes any visible source change or service stop.
    write_private(
        STATE / "attempt.json",
        {"commit": manifest["commit"], "phase": "prepared", "worker_apparmor": worker_apparmor},
    )
    config = json.loads(run(*prefix, "config", "--format", "json"))
    bound_services = [
        name
        for name, service in config["services"].items()
        if any(volume.get("type") == "bind" for volume in service.get("volumes", []))
    ]
    if containers and bound_services:
        execute([*prefix, "stop", *bound_services])
    execute(["git", "checkout", "--detach", manifest["commit"]])
    verify(manifest, ROOT, require_rc=True)
    print(
        "Accepted source switched in a maintenance window; previous runtime/configuration captured."
    )


def verify_target(record):
    if record.get("legacy"):
        if (
            run("git", "rev-parse", "HEAD", cwd=ROOT) != record["manifest"]["commit"]
            or source_files(ROOT) != record["files"]
        ):
            raise ValueError("Legacy rollback source differs from the observed baseline")
        verify_no_untracked_inputs(ROOT)
    else:
        verify(record["manifest"], ROOT, inspect_images=True, require_rc=True)


def heads(prefix):
    return run(
        *prefix,
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        'psql -XAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT version_num FROM alembic_version ORDER BY version_num"',
    ).splitlines()


def deploy(path):
    manifest = validate(json.loads(path.read_text(encoding="utf-8")))
    verify(manifest, ROOT, require_rc=True)
    STATE.mkdir(mode=0o700, exist_ok=True)
    if (STATE / "rollback-pending.json").exists():
        raise ValueError("Finish or explicitly resolve the pending rollback first")
    attempt = STATE / "attempt.json"
    if (
        not attempt.exists()
        or json.loads(attempt.read_text(encoding="utf-8"))["commit"] != manifest["commit"]
    ):
        raise ValueError("prepare must capture the previous runtime before deployment")
    override = STATE / "pending-compose.json"
    frozen = compose_override(manifest)
    worker_apparmor = apparmor_security_option(ROOT)
    prepared = json.loads(attempt.read_text(encoding="utf-8"))
    if worker_apparmor != prepared.get("worker_apparmor"):
        raise ValueError("Worker security policy changed after prepare")
    if worker_apparmor:
        frozen["services"]["mpb-worker"]["security_opt"] = [worker_apparmor]
    support = json.loads((STATE / "support-compose.json").read_text(encoding="utf-8"))
    frozen["services"].update(support["services"])
    write_private(override, frozen)
    prefix = compose(override)
    for image in manifest["images"].values():
        for attempt in range(3):
            pulled = subprocess.run(["docker", "pull", image])
            if pulled.returncode == 0:
                break
            if attempt == 2:
                raise RuntimeError("Immutable image pull failed after three attempts")
            time.sleep(5 * (attempt + 1))
    verify(manifest, ROOT, inspect_images=True, require_rc=True)
    # A backup is mandatory for every update of an already running database.
    existing = run(*prefix, "ps", "-q", "postgres")
    backup_path = None
    if existing:
        backup_path = STATE / "backups" / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".dump")
        backup([*prefix, "exec", "-T", "postgres"], backup_path)
    # The baseline backfill must not race the previous schedule-change scanner.
    execute([*prefix, "stop", "mpb-scheduler"])
    execute(
        [
            *prefix,
            "up",
            "-d",
            "--no-build",
            "--pull",
            "never",
            "--wait",
            "--wait-timeout",
            "90",
            "postgres",
            "redis",
        ]
    )
    execute([*prefix, "run", "--rm", "--no-deps", "migrator"])
    execute(
        [
            *prefix,
            "up",
            "-d",
            "--no-build",
            "--pull",
            "never",
            "--remove-orphans",
            "--wait",
            "--wait-timeout",
            "180",
        ]
    )
    execute(
        [
            *prefix,
            "exec",
            "-T",
            "mpb-fastapi-stats",
            "python",
            "-m",
            "fastapi_stats_app.bootstrap_admin",
        ]
    )
    actual = heads(prefix)
    if actual != manifest["schema_heads"]:
        raise RuntimeError("Running schema differs from the accepted release")
    execute([*prefix, "restart", "main-site-frontend", "caddy"])
    record = {
        "manifest": manifest,
        "schema_heads": actual,
        "deployed_at": datetime.now(UTC).isoformat(),
        "pre_migration_backup": str(backup_path) if backup_path else None,
        "prior_configuration": json.loads((STATE / "prior-config.json").read_text(encoding="utf-8"))
        if (STATE / "prior-config.json").exists()
        else None,
    }
    write_private(STATE / "pending.json", record)
    print("Release started. Last-successful pointer is unchanged until post-deploy smoke passes.")


def finalize():
    rollback_path = STATE / "rollback-pending.json"
    if rollback_path.exists():
        change = json.loads(rollback_path.read_text(encoding="utf-8"))
        record = change["target"]
        verify_target(record)
        saved = ROOT / record["snapshot"]
        if heads(compose(saved / "compose.json")) != change["actual_schema"]:
            raise RuntimeError("Schema changed after rollback")
        record["schema_heads"] = change["actual_schema"]
        record["rolled_back_at"] = datetime.now(UTC).isoformat()
        write_private(STATE / "previous.json", change["from"])
        write_private(STATE / "current.json", record)
        write_private(
            STATE / "pending-compose.json",
            json.loads((saved / "compose.json").read_text(encoding="utf-8")),
        )
        rollback_path.unlink()
        (STATE / "pending.json").unlink(missing_ok=True)
        (STATE / "attempt.json").unlink(missing_ok=True)
        print("Smoke-verified rollback recorded; schema was not downgraded.")
        return
    record = json.loads((STATE / "pending.json").read_text(encoding="utf-8"))
    verify(record["manifest"], ROOT, inspect_images=True, require_rc=True)
    prefix = compose(STATE / "pending-compose.json")
    if heads(prefix) != record["schema_heads"]:
        raise RuntimeError("Schema changed after deployment")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    saved = STATE / "releases" / (stamp + "-" + record["manifest"]["commit"][:12])
    saved.mkdir(parents=True, mode=0o700)
    # Preserve image IDs for support containers too; no post-deploy image prune.
    containers = run(*prefix, "ps", "-q").splitlines()
    records = json.loads(run("docker", "inspect", *containers))
    runtime_images = runtime_overrides(records)
    expected = apparmor_security_option(ROOT)
    actual = runtime_images.get("mpb-worker", {}).get("security_opt", [])
    if actual != ([expected] if expected else []):
        raise ValueError("Running worker AppArmor profile differs from accepted policy")
    if expected:
        write_private(
            saved / "worker-apparmor.json",
            {"name": expected.removeprefix("apparmor="), "text": profile_text(ROOT)},
        )
    shutil.copyfile(ROOT / "security/worker-seccomp.json", saved / "worker-seccomp.json")
    runtime_images["migrator"] = {"image": record["manifest"]["images"]["bot"]}
    write_private(saved / "compose.json", {"services": runtime_images})
    for name in (".env", "Caddyfile.local"):
        if (ROOT / name).exists():
            shutil.copyfile(ROOT / name, saved / name)
            (saved / name).chmod(0o600)
    record["snapshot"] = str(saved.relative_to(ROOT))
    record["status"] = "successful"
    write_private(saved / "release.json", record)
    current = STATE / "current.json"
    if current.exists():
        write_private(STATE / "previous.json", json.loads(current.read_text(encoding="utf-8")))
    write_private(current, record)
    (STATE / "pending.json").unlink()
    (STATE / "attempt.json").unlink(missing_ok=True)
    print("Successful release manifest and private configuration snapshot recorded.")


def rollback(compatible_schema=None):
    # Failed deployment restores the last successful version, not its predecessor.
    target_path = STATE / ("current.json" if (STATE / "attempt.json").exists() else "previous.json")
    target = json.loads(target_path.read_text(encoding="utf-8"))
    current = json.loads((STATE / "current.json").read_text(encoding="utf-8"))
    actual = heads(["docker", "compose", "-f", "docker-compose.prod.yml"])
    if actual != target["schema_heads"] and actual != [compatible_schema]:
        raise ValueError(
            "Schema changed: rollback refused. Review old-code compatibility explicitly or restore the pre-migration backup in a maintenance window."
        )
    saved = (ROOT / target["snapshot"]).resolve()
    if not saved.is_relative_to(STATE.resolve()) or not (saved / ".env").is_file():
        raise ValueError("Invalid or incomplete private release snapshot")
    worker_apparmor = verify_saved_worker_policy(saved, legacy=target.get("legacy", False))
    if not target.get("legacy"):
        runtime = json.loads((saved / "compose.json").read_text(encoding="utf-8"))["services"]
        run_worker_probe(
            runtime["mpb-worker"]["image"], saved / "worker-seccomp.json", worker_apparmor
        )
    live_config = json.loads(
        run("docker", "compose", "-f", "docker-compose.prod.yml", "config", "--format", "json")
    )
    bound_services = [
        name
        for name, service in live_config["services"].items()
        if any(volume.get("type") == "bind" for volume in service.get("volumes", []))
    ]
    if bound_services:
        execute(["docker", "compose", "-f", "docker-compose.prod.yml", "stop", *bound_services])
    # checkout refuses local source edits instead of destroying them.
    execute(["git", "checkout", "--detach", target["manifest"]["commit"]])
    verify_target(target)
    for name in (".env", "Caddyfile.local"):
        if (saved / name).exists():
            shutil.copyfile(saved / name, ROOT / name)
            (ROOT / name).chmod(0o600)
    prefix = compose(saved / "compose.json")
    # No automatic migrations/downgrades, pulls, builds or destructive volume work.
    execute(
        [
            *prefix,
            "up",
            "-d",
            "--no-build",
            "--pull",
            "never",
            "--no-deps",
            "mpb-telegram-bot",
            "mpb-fastapi-stats",
            "mpb-scheduler",
            "mpb-worker",
            "main-site-frontend",
            "caddy",
            "proxy",
        ]
    )
    execute(
        [
            *prefix,
            "exec",
            "-T",
            "mpb-fastapi-stats",
            "python",
            "-m",
            "fastapi_stats_app.bootstrap_admin",
        ]
    )
    write_private(
        STATE / "rollback-pending.json",
        {"target": target, "from": current, "actual_schema": actual},
    )
    print(
        "Previous source/config/images started. Run post-deploy smoke before accepting rollback; no schema downgrade was executed."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("deploy")
    start.add_argument("manifest", type=Path)
    sub.add_parser("finalize")
    sub.add_parser("preserve-config")
    pre = sub.add_parser("prepare")
    pre.add_argument("manifest", type=Path)
    pre.add_argument("--candidate", required=True, type=Path)
    revert = sub.add_parser("rollback")
    revert.add_argument(
        "--compatible-schema",
        help="Explicitly reviewed current head compatible with the previous code",
    )
    args = parser.parse_args()
    if args.command == "deploy":
        deploy(args.manifest)
    elif args.command == "finalize":
        finalize()
    elif args.command == "preserve-config":
        preserve_configuration()
    elif args.command == "prepare":
        prepare(args.manifest, args.candidate)
    else:
        rollback(args.compatible_schema)


if __name__ == "__main__":
    main()
