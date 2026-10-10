"""Exercise actual rollback/finalize in a disposable Git checkout and Docker network."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from release_manifest import source_files


def execute(args, *, cwd, env, input_text=None, timeout=180):
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    if result.returncode:
        # Inputs and .env remain local. Only tool output accompanies a failure.
        raise RuntimeError(f"{args[0]} failed ({result.returncode}): {result.stderr[-4000:]}")
    return result.stdout.strip()


def fixture_compose(api_image, bot_image):
    common = {"env_file": [".env"], "networks": ["isolated"]}
    idle = {
        **common,
        "image": api_image,
        "command": ["python", "-c", "import time; time.sleep(3600)"],
    }
    services = {
        name: dict(idle)
        for name in ("mpb-telegram-bot", "mpb-scheduler", "mpb-worker", "caddy", "proxy")
    }
    services.update(
        {
            "postgres": {
                "image": "postgres:15-alpine",
                "networks": ["isolated"],
                "environment": {
                    "POSTGRES_USER": "drill",
                    "POSTGRES_DB": "drill",
                    "POSTGRES_PASSWORD": "synthetic-db-password",
                },
                "volumes": ["db:/var/lib/postgresql/data"],
                "healthcheck": {
                    "test": ["CMD", "pg_isready", "-U", "drill", "-d", "drill"],
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
            "migrator": {
                **common,
                "image": bot_image,
                "command": ["alembic", "upgrade", "head"],
                "profiles": ["tools"],
            },
            "mpb-fastapi-stats": {**common, "image": api_image},
            "main-site-frontend": {
                **common,
                "image": api_image,
                "command": ["python", "-m", "http.server", "8000", "--directory", "/fixture"],
                "volumes": ["./main_site_frontend:/fixture:ro"],
            },
        }
    )
    return {
        "services": services,
        "networks": {"isolated": {"internal": True}},
        "volumes": {"db": {}},
    }


def fixture_environment(password):
    values = {
        "MPB_ISOLATED_RC": "1",
        "ENVIRONMENT": "development",
        "BOT_TOKEN": "123456:isolated-rollback-fixture",
        "JWT_SECRET_KEY": "isolated-rollback-signing-key-never-use-in-production",
        "ADMIN_USER_IDS": "",
        "STATS_USER": "rollback-fixture-admin",
        "STATS_PASS": password,
        "DATABASE_URL": "postgresql://drill:synthetic-db-password@postgres:5432/drill",
        "REDIS_URL": "redis://redis:6379/0",
        "PUBLIC_API_URL": "http://mpb-fastapi-stats:9583",
        "PUBLIC_SITE_URL": "http://main-site-frontend:8000",
        "PROXY_URL": "",
        "TELEGRAM_PROXY_URL": "",
    }
    return "".join(f"{key}={value}\n" for key, value in values.items())


def drill(root, api_image, bot_image):
    project = "mpb-rollback-drill-" + uuid.uuid4().hex[:12]
    env = dict(os.environ, COMPOSE_PROJECT_NAME=project, PYTHONUTF8="1")
    env.pop("COMPOSE_FILE", None)
    candidate_tag = project + ":candidate"
    stage = "setup"
    report = {
        "status": "failed",
        "scope": "isolated local working-tree rollback proof; not production release attestation",
        "started_at": datetime.now(UTC).isoformat(),
        "project": project,
        "external_provider_requests": 0,
        "limitations": [
            "Same current schema for baseline/candidate; no schema downgrade or backup restoration",
            "Bot/scheduler/worker/Caddy/proxy are idle fixture services; production ingress is not exercised",
        ],
    }
    with tempfile.TemporaryDirectory(prefix=project + "-") as temporary:
        checkout = Path(temporary).resolve()
        prefix = ["docker", "compose", "-f", "docker-compose.prod.yml"]

        def run(*args, input_text=None, timeout=180):
            return execute(
                list(args), cwd=checkout, env=env, input_text=input_text, timeout=timeout
            )

        def compose(*args, **kwargs):
            return run(*prefix, *args, **kwargs)

        def progress(name):
            nonlocal stage
            stage = name
            print("Rollback drill: " + name, flush=True)

        def image_id(reference):
            return json.loads(run("docker", "image", "inspect", reference))[0]["Id"]

        def write_json(path, value):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

        def runtime_images():
            ids = compose("ps", "-q").splitlines()
            rows = json.loads(run("docker", "inspect", *ids))
            assert all(not row["HostConfig"].get("PortBindings") for row in rows)
            return {
                row["Config"]["Labels"]["com.docker.compose.service"]: row["Image"] for row in rows
            }

        def sql(query):
            return compose(
                "exec",
                "-T",
                "postgres",
                "psql",
                "-XAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "drill",
                "-d",
                "drill",
                "-c",
                query,
            )

        def await_api():
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                try:
                    compose(
                        "exec",
                        "-T",
                        "mpb-fastapi-stats",
                        "python",
                        "-c",
                        "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:9583/api/stats/health',timeout=3).status==200",
                        timeout=10,
                    )
                    return
                except RuntimeError:
                    time.sleep(1)
            raise RuntimeError("Fixture API did not become healthy")

        def login(password):
            code = """import json,sys,urllib.request,urllib.parse,urllib.error
data=json.load(sys.stdin)
try:
 response=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:9583/api/auth/login',data=urllib.parse.urlencode(data).encode()),timeout=10)
 token=json.load(response)['access_token']
 me=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:9583/api/auth/me',headers={'Authorization':'Bearer '+token}),timeout=10)
 print(json.dumps({'status':response.status,'role':json.load(me)['role']}))
except urllib.error.HTTPError as error:
 print(json.dumps({'status':error.code}))
"""
            return json.loads(
                compose(
                    "exec",
                    "-T",
                    "mpb-fastapi-stats",
                    "python",
                    "-c",
                    code,
                    input_text=json.dumps(
                        {"username": "rollback-fixture-admin", "password": password}
                    ),
                )
            )

        old_password, new_password = "synthetic-baseline-password", "synthetic-candidate-password"
        try:
            api_id, bot_id = image_id(api_image), image_id(bot_image)
            config = fixture_compose(api_id, bot_id)
            write_json(checkout / "docker-compose.prod.yml", config)
            (checkout / "main_site_frontend").mkdir()
            (checkout / "main_site_frontend/index.html").write_text(
                "baseline-canary-A", encoding="utf-8"
            )
            (checkout / "Caddyfile").write_text("# synthetic baseline A\n", encoding="utf-8")
            (checkout / ".gitignore").write_text(
                ".env\nCaddyfile.local\n.release-state/\n__pycache__/\n", encoding="utf-8"
            )
            (checkout / ".env").write_text(fixture_environment(old_password), encoding="utf-8")
            (checkout / "Caddyfile.local").write_text(
                "# synthetic private baseline A\n", encoding="utf-8"
            )
            (checkout / "scripts").mkdir()
            helper_hashes = {}
            for name in ("release_deploy.py", "release_manifest.py", "release_backup.py"):
                shutil.copyfile(root / "scripts" / name, checkout / "scripts" / name)
                helper_hashes[name] = hashlib.sha256(
                    (checkout / "scripts" / name).read_bytes()
                ).hexdigest()
            report["helper_sha256"] = helper_hashes
            run("git", "init", "--quiet")
            run("git", "config", "user.name", "Synthetic rollback fixture")
            run("git", "config", "user.email", "fixture@example.invalid")
            run("git", "config", "core.autocrlf", "false")
            run("git", "config", "commit.gpgsign", "false")
            run("git", "add", ".")
            run("git", "commit", "--quiet", "-m", "Synthetic baseline A")
            baseline_commit = run("git", "rev-parse", "HEAD")
            progress("starting isolated baseline")
            compose("up", "-d", "--pull", "never", "--wait", "postgres", "redis")
            network = json.loads(run("docker", "network", "inspect", project + "_isolated"))[0]
            assert network["Internal"] is True
            compose("run", "--rm", "--no-deps", "migrator")
            compose("up", "-d", "--pull", "never", "--no-build")
            await_api()
            compose(
                "exec",
                "-T",
                "mpb-fastapi-stats",
                "python",
                "-m",
                "fastapi_stats_app.bootstrap_admin",
            )
            assert login(old_password) == {"status": 200, "role": "admin"}
            baseline_runtime = runtime_images()
            baseline_schema = sql(
                "SELECT version_num FROM alembic_version ORDER BY version_num"
            ).splitlines()
            assert len(baseline_schema) == 1
            state = checkout / ".release-state"
            snapshot = state / "releases" / "synthetic-observed-baseline"
            snapshot.mkdir(parents=True)
            for name in (".env", "Caddyfile.local"):
                shutil.copyfile(checkout / name, snapshot / name)
            write_json(
                snapshot / "compose.json",
                {"services": {name: {"image": value} for name, value in baseline_runtime.items()}},
            )
            record = {
                "legacy": True,
                "manifest": {"commit": baseline_commit},
                "files": source_files(checkout),
                "schema_heads": baseline_schema,
                "snapshot": str(snapshot.relative_to(checkout)),
                "status": "observed-legacy",
            }
            write_json(snapshot / "release.json", record)
            write_json(state / "current.json", record)

            progress("applying synthetic candidate source/settings/image")
            # A label-only image creates a genuine different runtime image ID,
            # with the current API code and no registry/network download.
            run(
                "docker",
                "build",
                "--network",
                "none",
                "--pull=false",
                "-t",
                candidate_tag,
                "-",
                input_text=f"FROM {api_image}\nLABEL matplobbot.rollback-fixture={project}\n",
            )
            candidate_id = image_id(candidate_tag)
            assert candidate_id != api_id
            config["services"]["mpb-fastapi-stats"]["image"] = candidate_id
            write_json(checkout / "docker-compose.prod.yml", config)
            (checkout / "main_site_frontend/index.html").write_text(
                "candidate-canary-B", encoding="utf-8"
            )
            (checkout / "Caddyfile").write_text("# synthetic candidate B\n", encoding="utf-8")
            (checkout / ".env").write_text(fixture_environment(new_password), encoding="utf-8")
            (checkout / "Caddyfile.local").write_text(
                "# synthetic private candidate B\n", encoding="utf-8"
            )
            run("git", "add", ".")
            run("git", "commit", "--quiet", "-m", "Synthetic candidate B")
            candidate_commit = run("git", "rev-parse", "HEAD")
            write_json(
                state / "attempt.json", {"commit": candidate_commit, "phase": "synthetic-candidate"}
            )
            compose("up", "-d", "--pull", "never", "--no-build")
            await_api()
            compose(
                "exec",
                "-T",
                "mpb-fastapi-stats",
                "python",
                "-m",
                "fastapi_stats_app.bootstrap_admin",
            )
            assert login(new_password) == {"status": 200, "role": "admin"}
            assert login(old_password) == {"status": 401}
            assert runtime_images()["mpb-fastapi-stats"] == candidate_id
            progress("invoking actual rollback helper")
            run(
                sys.executable, str(checkout / "scripts/release_deploy.py"), "rollback", timeout=240
            )
            assert (state / "rollback-pending.json").exists()
            assert not json.loads((state / "current.json").read_text(encoding="utf-8")).get(
                "rolled_back_at"
            )
            assert run("git", "rev-parse", "HEAD") == baseline_commit
            assert source_files(checkout) == record["files"]
            for name in (".env", "Caddyfile.local"):
                assert (checkout / name).read_bytes() == (snapshot / name).read_bytes()
            await_api()
            restored_runtime = runtime_images()
            assert restored_runtime == baseline_runtime
            assert (
                sql("SELECT version_num FROM alembic_version ORDER BY version_num").splitlines()
                == baseline_schema
            )
            assert (
                sql("SELECT count(*) FROM web_accounts WHERE username='rollback-fixture-admin'")
                == "1"
            )
            assert login(old_password) == {"status": 200, "role": "admin"}
            assert login(new_password) == {"status": 401}
            canary = compose(
                "exec",
                "-T",
                "mpb-fastapi-stats",
                "python",
                "-c",
                "import urllib.request; print(urllib.request.urlopen('http://main-site-frontend:8000',timeout=10).read().decode())",
            )
            assert canary == "baseline-canary-A"
            progress("smoke passed; invoking actual finalize helper")
            run(sys.executable, str(checkout / "scripts/release_deploy.py"), "finalize")
            final = json.loads((state / "current.json").read_text(encoding="utf-8"))
            assert final["manifest"]["commit"] == baseline_commit and final["rolled_back_at"]
            assert (
                not (state / "attempt.json").exists()
                and not (state / "rollback-pending.json").exists()
            )
            report.update(
                {
                    "status": "passed",
                    "schema_heads": baseline_schema,
                    "baseline_fixture_commit": baseline_commit,
                    "candidate_fixture_commit": candidate_commit,
                    "baseline_runtime_images": baseline_runtime,
                    "candidate_api_image": candidate_id,
                    "checks": {
                        name: True
                        for name in (
                            "internal_network",
                            "no_host_ports",
                            "candidate_password_changed",
                            "candidate_runtime_changed",
                            "tracked_source_restored",
                            "private_configuration_restored",
                            "runtime_images_restored",
                            "schema_preserved",
                            "account_row_preserved",
                            "old_password_accepted_new_rejected",
                            "frontend_canary_restored",
                            "pointer_unchanged_before_smoke",
                            "finalize_advances_after_smoke",
                        )
                    },
                }
            )
        except Exception as error:
            report.update(
                {
                    "failed_stage": stage,
                    "error_type": type(error).__name__,
                    "error": str(error)[-4000:],
                }
            )
        finally:
            progress("removing only disposable fixture containers and volumes")
            try:
                compose("down", "--volumes", "--remove-orphans", timeout=90)
                containers = run(
                    "docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project
                )
                networks = run(
                    "docker",
                    "network",
                    "ls",
                    "-q",
                    "--filter",
                    "label=com.docker.compose.project=" + project,
                )
                volumes = run(
                    "docker",
                    "volume",
                    "ls",
                    "-q",
                    "--filter",
                    "label=com.docker.compose.project=" + project,
                )
                assert not containers and not networks and not volumes
                report["cleanup_verified"] = True
            except Exception as error:
                report.update(
                    {
                        "status": "failed",
                        "cleanup_verified": False,
                        "cleanup_error": str(error)[-2000:],
                    }
                )
            subprocess.run(
                ["docker", "image", "rm", candidate_tag], capture_output=True, timeout=30
            )
    report["finished_at"] = datetime.now(UTC).isoformat()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-image", default="matplobbot-rc-api:local")
    parser.add_argument("--bot-image", default="matplobbot-rc-bot:local")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = drill(root, args.api_image, args.bot_image)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "cleanup_verified": report.get("cleanup_verified"),
                "report": str(args.output),
            },
            indent=2,
        )
    )
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
