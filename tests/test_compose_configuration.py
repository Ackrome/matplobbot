import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_COMPOSE = PROJECT_ROOT / "docker-compose.yml"
PRODUCTION_COMPOSE = PROJECT_ROOT / "docker-compose.prod.yml"
GITHUB_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci-cd.yml"
JENKINSFILE = PROJECT_ROOT / "Jenkinsfile.groovy"
DEPLOY_SCRIPT = PROJECT_ROOT / "deploy.sh"
VALIDATION_REQUIREMENTS = PROJECT_ROOT / "requirements-validation.txt"
FRONTEND_NGINX = PROJECT_ROOT / "main_site_frontend" / "default.conf"
FRONTEND_UI_UTILS = PROJECT_ROOT / "main_site_frontend" / "js" / "ui_utils.js"
FRONTEND_STATS = PROJECT_ROOT / "main_site_frontend" / "js" / "stats.js"
SCHEDULER_MAIN = PROJECT_ROOT / "scheduler_app" / "main.py"
COMMON_LONG_RUNNING_SERVICES = {
    "redis",
    "postgres",
    "mpb-telegram-bot",
    "mpb-scheduler",
    "mpb-fastapi-stats",
    "mpb-worker",
    "main-site-frontend",
    "caddy",
}


def _load_compose(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _find_bash() -> str | None:
    if os.name == "nt":
        for candidate in (
            Path("C:/Program Files/Git/bin/bash.exe"),
            Path("C:/Program Files/Git/usr/bin/bash.exe"),
        ):
            if candidate.is_file():
                return str(candidate)
    return shutil.which("bash")


def _bash_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return str(resolved)
    drive = resolved.drive.rstrip(":").lower()
    return f"/{drive}{resolved.as_posix()[2:]}"


class TestComposeConfiguration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.local = _load_compose(LOCAL_COMPOSE)
        cls.production = _load_compose(PRODUCTION_COMPOSE)

    def test_production_only_adds_the_credential_backed_proxy_service(self):
        local_services = set(self.local["services"])
        production_services = set(self.production["services"])

        self.assertEqual(production_services - local_services, {"proxy"})
        self.assertEqual(local_services - production_services, set())

    def test_shared_frontend_and_caddy_mounts_stay_aligned(self):
        for service_name in ("main-site-frontend", "caddy"):
            local_volumes = set(self.local["services"][service_name]["volumes"])
            production_volumes = set(self.production["services"][service_name]["volumes"])
            self.assertEqual(local_volumes, production_volumes)

        frontend_volumes = set(self.local["services"]["main-site-frontend"]["volumes"])
        self.assertIn(
            "./main_site_frontend/default.conf:/etc/nginx/conf.d/default.conf:ro",
            frontend_volumes,
        )

    def test_long_running_services_have_bounded_docker_logs(self):
        for compose in (self.local, self.production):
            expected_services = set(COMMON_LONG_RUNNING_SERVICES)
            if "proxy" in compose["services"]:
                expected_services.add("proxy")

            for service_name in expected_services:
                with self.subTest(service=service_name):
                    logging_config = compose["services"][service_name]["logging"]
                    self.assertEqual(logging_config["driver"], "json-file")
                    self.assertEqual(logging_config["options"]["max-size"], "10m")
                    self.assertEqual(logging_config["options"]["max-file"], "3")

    def test_structured_python_services_run_in_production_mode(self):
        for service_name in (
            "mpb-telegram-bot",
            "mpb-scheduler",
            "mpb-fastapi-stats",
        ):
            with self.subTest(service=service_name):
                environment = self.production["services"][service_name]["environment"]
                self.assertIn("ENVIRONMENT=production", environment)

    def test_quality_gates_share_validation_dependencies(self):
        github_workflow = GITHUB_WORKFLOW.read_text(encoding="utf-8")
        jenkinsfile = JENKINSFILE.read_text(encoding="utf-8")
        validation_requirements = VALIDATION_REQUIREMENTS.read_text(encoding="utf-8")

        install_command = "pip install -r requirements-validation.txt"
        self.assertIn(install_command, github_workflow)
        self.assertIn(f"python -m {install_command}", jenkinsfile)
        self.assertIn("PyYAML==6.0.3", validation_requirements)
        self.assertIn('"yaml",', jenkinsfile)

    def test_jenkins_writes_complete_remote_env_atomically(self):
        jenkinsfile = JENKINSFILE.read_text(encoding="utf-8")
        deploy_script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("DEPLOY_PATH = '~/matplobbot'", jenkinsfile)
        self.assertIn(
            '"cd $DEPLOY_PATH && bash ./deploy.sh --write-env .env $EXPECTED_ENV_KEYS"',
            jenkinsfile,
        )
        self.assertNotIn("cd '$DEPLOY_PATH'", jenkinsfile)
        self.assertNotIn("ENV_TMP", jenkinsfile)
        self.assertNotIn("for key in $EXPECTED_ENV_KEYS", jenkinsfile)
        self.assertIn('mktemp "${target_dir}/${target_name}.tmp.XXXXXX"', deploy_script)
        self.assertIn('mv -f -- "$temp_path" "$target_path"', deploy_script)
        self.assertIn("Remote .env keys verified without exposing values.", deploy_script)
        self.assertNotIn(">> .env", jenkinsfile)
        payload_start = jenkinsfile.index("EXPECTED_ENV_KEYS=")
        remote_write = jenkinsfile.index("} | ssh", payload_start)
        for key in (
            "OUTLINE_ACCESS_KEY",
            "TELEGRAM_REQUEST_RETRY_ATTEMPTS",
            "TELEGRAM_REQUEST_RETRY_DELAY_SECONDS",
        ):
            self.assertLess(jenkinsfile.index(f"printf '{key}=", payload_start), remote_write)

    def test_deploy_script_atomically_writes_env_payload(self):
        bash = _find_bash()
        if bash is None:
            self.skipTest("bash is unavailable")

        payload = "BOT_TOKEN=secret-value\nREDIS_URL=rediss://redis:6380/2\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.run(
                [
                    bash,
                    _bash_path(DEPLOY_SCRIPT),
                    "--write-env",
                    ".env",
                    "BOT_TOKEN",
                    "REDIS_URL",
                ],
                cwd=temp_dir,
                input=payload,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            target = Path(temp_dir) / ".env"
            self.assertEqual(target.read_text(encoding="utf-8"), payload)
            self.assertEqual(list(Path(temp_dir).glob(".env.tmp.*")), [])
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_deploy_script_rejects_incomplete_env_without_replacing_target(self):
        bash = _find_bash()
        if bash is None:
            self.skipTest("bash is unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / ".env"
            target.write_text("BOT_TOKEN=previous\n", encoding="utf-8")
            completed = subprocess.run(
                [
                    bash,
                    _bash_path(DEPLOY_SCRIPT),
                    "--write-env",
                    ".env",
                    "BOT_TOKEN",
                    "REDIS_URL",
                ],
                cwd=temp_dir,
                input="BOT_TOKEN=replacement\n",
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("missing REDIS_URL", completed.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "BOT_TOKEN=previous\n")
            self.assertEqual(list(Path(temp_dir).glob(".env.tmp.*")), [])

    def test_jenkins_failure_notification_avoids_secret_groovy_interpolation(self):
        jenkinsfile = JENKINSFILE.read_text(encoding="utf-8")

        self.assertNotIn('withEnv(["TG_CHAT_ID=${adminIds[0]}"])', jenkinsfile)
        self.assertIn(
            'TG_CHAT_ID="$(printf \'%s\' "$PROD_ADMIN_USER_IDS" | awk -F,',
            jenkinsfile,
        )

    def test_frontend_nginx_proxies_websocket_upgrades(self):
        nginx = FRONTEND_NGINX.read_text(encoding="utf-8")
        jenkinsfile = JENKINSFILE.read_text(encoding="utf-8")

        ws_location = nginx.split("location /ws/", 1)[1].split("location /", 1)[0]
        self.assertIn("proxy_pass $stats_api", ws_location)
        self.assertIn("proxy_http_version 1.1", ws_location)
        self.assertIn("proxy_set_header Upgrade $http_upgrade", ws_location)
        self.assertIn('proxy_set_header Connection "upgrade"', ws_location)
        self.assertIn("check_ws_upgrade", jenkinsfile)
        self.assertIn('if [ "$status" != "101" ]', jenkinsfile)
        self.assertIn("http://127.0.0.1:9584/ws/stats/total_actions", jenkinsfile)
        self.assertIn("${PUBLIC_SITE_URL%/}/ws/stats/total_actions", jenkinsfile)

    def test_stats_websocket_uses_runtime_api_origin_and_single_reconnect_timer(self):
        ui_utils = FRONTEND_UI_UTILS.read_text(encoding="utf-8")
        stats = FRONTEND_STATS.read_text(encoding="utf-8")

        self.assertIn("window.getMpbWebSocketBase", ui_utils)
        self.assertIn("apiUrl.pathname.replace(/\\/api\\/?$/", ui_utils)
        self.assertIn("window.getMpbWebSocketBase()", stats)
        self.assertIn("wsReconnectTimer", stats)
        self.assertIn("WebSocket.CONNECTING", stats)
        self.assertNotIn("window.location.host}/ws/stats", stats)

    def test_schedule_outbox_is_drained_every_minute(self):
        scheduler_main = SCHEDULER_MAIN.read_text(encoding="utf-8")

        outbox_job = scheduler_main.split(
            "scheduler.add_job(\n                deliver_pending_schedule_change_notifications,",
            1,
        )[1].split("scheduler.add_job(", 1)[0]
        self.assertIn('trigger="interval"', outbox_job)
        self.assertIn("minutes=1", outbox_job)

    def test_celery_worker_healthcheck_is_bounded_and_identical(self):
        local_health = self.local["services"]["mpb-worker"]["healthcheck"]
        production_health = self.production["services"]["mpb-worker"]["healthcheck"]

        self.assertEqual(local_health, production_health)
        command = " ".join(local_health["test"])
        self.assertIn("celery -A shared_lib.celery_app inspect ping", command)
        self.assertIn("--destination celery@$${HOSTNAME}", command)
        self.assertIn("--timeout 5", command)
        self.assertIn("grep -q pong", command)
        self.assertEqual(local_health["timeout"], "10s")
        self.assertEqual(local_health["retries"], 3)
        self.assertEqual(local_health["start_period"], "30s")


if __name__ == "__main__":
    unittest.main()
