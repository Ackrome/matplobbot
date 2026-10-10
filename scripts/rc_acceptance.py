"""Mandatory real-service RC acceptance; all containers and data are disposable."""

import argparse
import json
import subprocess
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml
from release_backup import backup, restore_drill
from release_manifest import SERVICES, run, verify


def build_compose(images, root):
    environment = {
        "MPB_ISOLATED_RC": "1",
        "ENVIRONMENT": "development",
        "BOT_TOKEN": "123456:rc-test-token",
        "JWT_SECRET_KEY": "isolated-rc-secret-never-use-in-production-123456789",
        "ADMIN_USER_IDS": "",
        "STATS_USER": "rc-admin",
        "STATS_PASS": "isolated-rc-admin-password",
        "DATABASE_URL": "postgresql://rc:isolated-rc-password@postgres:5432/rc",
        "REDIS_URL": "redis://redis:6379/0",
        "PUBLIC_API_URL": "http://api:9583",
        "PUBLIC_SITE_URL": "http://api:9583",
        "TELEGRAM_REQUEST_RETRY_ATTEMPTS": "0",
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": "/:/app",
        "PROXY_URL": "",
        "TELEGRAM_PROXY_URL": "",
        "SCHEDULE_OUTBOX_BASE_DELAY_SECONDS": "60",
    }

    def service(key):
        return {"image": images[key], "environment": environment, "networks": ["isolated"]}

    worker = service("worker")
    production = yaml.safe_load((root / "docker-compose.prod.yml").read_text(encoding="utf-8"))[
        "services"
    ]["mpb-worker"]
    for key in (
        "cap_drop",
        "cap_add",
        "security_opt",
        "pids_limit",
        "mem_limit",
        "cpus",
        "read_only",
        "tmpfs",
        "ulimits",
    ):
        if key in production:
            worker[key] = production[key]
    services = {
        "postgres": {
            "image": "postgres:15-alpine",
            "environment": {
                "POSTGRES_USER": "rc",
                "POSTGRES_DB": "rc",
                "POSTGRES_PASSWORD": "isolated-rc-password",
            },
            "volumes": ["db:/var/lib/postgresql/data"],
            "networks": ["isolated"],
            "healthcheck": {
                "test": ["CMD", "pg_isready", "-U", "rc", "-d", "rc"],
                "interval": "1s",
                "timeout": "5s",
                "retries": 60,
            },
        },
        "redis": {
            "image": "redis:7-alpine",
            "networks": ["isolated"],
            "healthcheck": {
                "test": ["CMD", "redis-cli", "ping"],
                "interval": "1s",
                "timeout": "5s",
                "retries": 60,
            },
        },
        "migrator": {**service("bot"), "command": ["alembic", "upgrade", "head"]},
        "api": service("api"),
        "worker": worker,
        "scheduler": {**service("scheduler"), "entrypoint": ["sleep", "3600"]},
    }
    return {
        "services": services,
        "networks": {"isolated": {"internal": True}},
        "volumes": {"db": {}},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--local-image",
        action="append",
        help="Development evidence only; never eligible for release attestation",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path.cwd()
    if bool(args.manifest) == bool(args.local_image):
        parser.error("Choose an immutable manifest or four development-only local images")
    if args.manifest:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        verify(manifest, root)
        images, commit = manifest["images"], manifest["commit"]
        for image in images.values():
            subprocess.run(["docker", "pull", image], check=True)
        verify(manifest, root, inspect_images=True)
    else:
        images = dict(value.split("=", 1) for value in args.local_image)
        if set(images) != set(SERVICES):
            parser.error("Four service images are required")
        commit = run("git", "rev-parse", "HEAD") + "-working-tree"
    subprocess.run(["docker", "info"], check=True, stdout=subprocess.DEVNULL)
    project = "mpb-rc-" + uuid.uuid4().hex[:12]
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "failed",
        "commit": commit,
        "images": images,
        "runtime_image_ids": {
            key: json.loads(run("docker", "image", "inspect", ref))[0]["Id"]
            for key, ref in images.items()
        },
        "started_at": datetime.now(UTC).isoformat(),
        "external_boundaries": "Synthetic Telegram login; local Telegram HTTP 503/200 fixture; seeded RUZ cache. No real users or external delivery.",
    }
    with tempfile.TemporaryDirectory(prefix=project + "-") as directory:
        work = Path(directory)
        config = work / "compose.json"
        config.write_text(json.dumps(build_compose(images, root)), encoding="utf-8")
        compose = [
            "docker",
            "compose",
            "--project-directory",
            str(root),
            "-p",
            project,
            "-f",
            str(config),
        ]

        def execute(*command, **kwargs):
            return subprocess.run([*compose, *command], check=True, **kwargs)

        try:
            execute("up", "-d", "--wait", "--wait-timeout", "90", "postgres", "redis")
            execute("run", "--rm", "migrator", timeout=180)
            execute("up", "-d", "api", "worker", "scheduler")

            def wait_api():
                for _ in range(90):
                    probe = subprocess.run(
                        [
                            *compose,
                            "exec",
                            "-T",
                            "api",
                            "python",
                            "-c",
                            "import urllib.request;urllib.request.urlopen('http://127.0.0.1:9583/api/stats/health',timeout=2)",
                        ],
                        capture_output=True,
                    )
                    if probe.returncode == 0:
                        return
                    time.sleep(1)
                raise RuntimeError("RC API did not become healthy")

            wait_api()
            execute(
                "exec", "-T", "api", "python", "-m", "fastapi_stats_app.bootstrap_admin", timeout=30
            )
            for service_name in ("api", "scheduler"):
                execute("cp", str(root / "scripts/rc_probe.py"), f"{service_name}:/tmp/rc_probe.py")
            execute(
                "cp",
                str(root / "scripts/rc_delivery_probe.py"),
                "scheduler:/tmp/rc_delivery_probe.py",
            )
            # /tmp is the worker's only writable mount under the production sandbox profile.
            with (root / "tests/test_render_sandbox.py").open("rb") as source:
                execute(
                    "exec",
                    "-T",
                    "worker",
                    "sh",
                    "-c",
                    "cat > /tmp/test_render_sandbox.py",
                    stdin=source,
                )
            execute(
                "exec",
                "-T",
                "-e",
                "RENDER_SANDBOX_INTEGRATION=1",
                "worker",
                "python",
                "-m",
                "unittest",
                "discover",
                "-s",
                "/tmp",
                "-p",
                "test_render_sandbox.py",
                "-v",
                timeout=600,
            )
            execute("exec", "-T", "api", "python", "/tmp/rc_probe.py", "prepare", timeout=120)
            execute("restart", "api")
            wait_api()
            execute("exec", "-T", "api", "python", "/tmp/rc_probe.py", "verify", timeout=600)
            execute("restart", "api")
            wait_api()
            execute(
                "exec", "-T", "api", "python", "/tmp/rc_probe.py", "after_revocation", timeout=60
            )
            execute("exec", "-T", "scheduler", "python", "/tmp/rc_probe.py", "outbox", timeout=120)
            dump = work / "rc.dump"
            backup([*compose, "exec", "-T", "postgres"], dump)
            report.update(restore_drill(dump))
            report.update(
                status="passed",
                completed_at=datetime.now(UTC).isoformat(),
                checks=[
                    "alembic fresh PostgreSQL",
                    "Telegram HTTP login and ownership isolation",
                    "project persistence across API restart",
                    "real Redis/Celery LaTeX Markdown Mermaid artifacts",
                    "production worker sandbox and six render paths",
                    "calendar profile persistence and ICS",
                    "owner export/delete and persistent session revocation",
                    "password login HTTP limits and revoked open/new WebSockets",
                    "real Redis Lua shared budgets and expiry",
                    "scheduler HTTP failure/retry/outbox dedupe",
                    "PostgreSQL SKIP LOCKED, baseline CAS and cancellation",
                    "snapshot backup/restore row fingerprints",
                ],
            )
        finally:
            if report["status"] != "passed":
                with args.output.with_suffix(".log").open("w", encoding="utf-8") as log:
                    subprocess.run(
                        [*compose, "logs", "--no-color", "--tail", "150"],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                    )
            args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            if report["status"] == "passed":
                args.output.with_suffix(".log").unlink(missing_ok=True)
            execute("down", "--volumes", "--remove-orphans", timeout=60)
    print("Real-service RC acceptance and isolated restore passed.")


if __name__ == "__main__":
    main()
