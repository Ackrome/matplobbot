import ast
import os
import shutil
import stat
import subprocess
import sys
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
PRIVATE_IPV4_RESOLVER = PROJECT_ROOT / "scripts" / "resolve_private_ipv4.sh"
VALIDATION_REQUIREMENTS = PROJECT_ROOT / "requirements-validation.txt"
FRONTEND_NGINX = PROJECT_ROOT / "main_site_frontend" / "default.conf"
FRONTEND_UI_UTILS = PROJECT_ROOT / "main_site_frontend" / "js" / "ui_utils.js"
FRONTEND_STATS = PROJECT_ROOT / "main_site_frontend" / "js" / "stats.js"
SCHEDULER_MAIN = PROJECT_ROOT / "scheduler_app" / "main.py"
PROXY_DOCKERFILE = PROJECT_ROOT / "proxy" / "Dockerfile.proxy"
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
    @unittest.skipUnless(_find_bash(), "bash is required for the deployment username check")
    def test_deployment_uses_dedicated_username_instead_of_legacy_credential(self):
        pipeline = JENKINSFILE.read_text(encoding="utf-8")
        self.assertNotIn("credentials('PROD_STATS_USER')", pipeline)
        self.assertIn("string(name: 'DEPLOY_ADMIN_USERNAME'", pipeline)
        emit_username = next(
            line.strip() for line in pipeline.splitlines() if "printf 'STATS_USER=%s" in line
        )
        for override, expected in (
            ("", "matplobbot-deploy"),
            ("dedicated-admin", "dedicated-admin"),
        ):
            with self.subTest(override=override):
                result = subprocess.run(
                    [_find_bash(), "-c", emit_username],
                    env={
                        **os.environ,
                        "PROD_STATS_USER": "existing-telegram-account",
                        "DEPLOY_ADMIN_USERNAME": override,
                    },
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self.assertEqual(result.stdout, f"STATS_USER={expected}\n")

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

    def test_proxy_uses_external_read_only_subscription_secret(self):
        proxy = self.production["services"]["proxy"]
        secret_mount = next(
            volume
            for volume in proxy["volumes"]
            if isinstance(volume, dict)
            and volume.get("target") == "/run/secrets/proxy-subscriptions.json"
        )

        self.assertTrue(secret_mount["read_only"])
        self.assertFalse(secret_mount["bind"]["create_host_path"])
        self.assertIn(
            "SUB_URLS_FILE=/run/secrets/proxy-subscriptions.json",
            proxy["environment"],
        )

    def test_proxy_core_download_is_versioned_and_hash_verified(self):
        dockerfile = PROXY_DOCKERFILE.read_text(encoding="utf-8")

        self.assertIn("ARG MIHOMO_VERSION=v1.19.32", dockerfile)
        self.assertIn("sha256sum -c -", dockerfile)
        self.assertIn("MIHOMO_AMD64_SHA256", dockerfile)
        self.assertIn("MIHOMO_ARM64_SHA256", dockerfile)

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

    def test_deployment_uses_proxmox_lan_without_tailscale_auth_gate(self):
        github_workflow = GITHUB_WORKFLOW.read_text(encoding="utf-8")
        jenkinsfile = JENKINSFILE.read_text(encoding="utf-8")

        self.assertIn(
            "string(name: 'DEPLOY_HOST', defaultValue: '192.168.1.40'",
            jenkinsfile,
        )
        self.assertNotIn("app-vm.panthera-banjo.ts.net", jenkinsfile)
        self.assertEqual(
            jenkinsfile.count(
                'DEPLOY_HOST="$(bash "$WORKSPACE/scripts/resolve_private_ipv4.sh" '
                '"${DEPLOY_HOST:-192.168.1.40}")"'
            ),
            3,
        )
        self.assertIn("DEFAULT_DEPLOY_HOST_FINGERPRINT = credentials('APP_VM_SHA256')", jenkinsfile)
        self.assertIn(
            "JENKINS_LAN_URL: ${{ vars.JENKINS_LAN_URL || 'http://192.168.1.130:8080' }}",
            github_workflow,
        )
        self.assertIn(
            "APP_VM_LAN_HOST: ${{ vars.APP_VM_LAN_HOST || '192.168.1.40' }}",
            github_workflow,
        )
        self.assertIn('JENKINS_LAN_IP="$(bash scripts/resolve_private_ipv4.sh', github_workflow)
        self.assertIn('APP_VM_LAN_IP="$(bash scripts/resolve_private_ipv4.sh', github_workflow)
        self.assertIn('--noproxy "$JENKINS_HOST,$JENKINS_LAN_IP"', github_workflow)
        self.assertIn('--resolve "$JENKINS_HOST:$JENKINS_PORT:$JENKINS_LAN_IP"', github_workflow)
        self.assertIn('--data-urlencode "DEPLOY_HOST=$APP_VM_LAN_IP"', github_workflow)
        self.assertNotIn("secrets.JENKINS_URL", github_workflow)
        self.assertEqual(jenkinsfile.count("ssh-keyscan -T 5 -t ed25519"), 3)

    def test_private_ipv4_resolver_rejects_non_lan_deployment_hosts(self):
        bash = _find_bash()
        if bash is None:
            self.skipTest("bash is unavailable")

        accepted = subprocess.run(
            [bash, _bash_path(PRIVATE_IPV4_RESOLVER), "192.168.1.25"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(accepted.stdout.strip(), "192.168.1.25")

        for rejected_host in (
            "app-vm.panthera-banjo.ts.net",
            "100.126.36.2",
            "127.0.0.1",
            "203.0.113.25",
        ):
            with self.subTest(host=rejected_host):
                rejected = subprocess.run(
                    [bash, _bash_path(PRIVATE_IPV4_RESOLVER), rejected_host],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(rejected.returncode, 0)
                self.assertEqual(rejected.stdout, "")

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
        self.assertIn("http://127.0.0.1:8080/ws/stats/total_actions", jenkinsfile)
        self.assertNotIn("http://127.0.0.1:9584/ws/", jenkinsfile)
        self.assertIn("expected admin login returned HTTP", jenkinsfile)
        self.assertNotIn("falling back to protected-endpoint contract", jenkinsfile)
        self.assertIn("${PUBLIC_SITE_URL%/}/ws/stats/total_actions", jenkinsfile)

    @unittest.skipUnless(_find_bash(), "bash is required for the isolated smoke script test")
    def test_jenkins_smoke_requires_successful_expected_admin_login_at_runtime(self):
        jenkinsfile = JENKINSFILE.read_text(encoding="utf-8")
        script = jenkinsfile.rsplit("<<'REMOTE_EOF'", 1)[1].split("REMOTE_EOF", 1)[0]
        # The pipeline's Groovy string consumes one layer of escaped backslashes.
        script = script.replace("\\\\", "\\")
        fake_commands = r"""
docker() {
  if [ "$FAKE_ENV_FAILURE" = 1 ]; then return 1; fi
  STATS_USER="$TEST_STATS_USER" STATS_PASS="$TEST_STATS_PASS" PUBLIC_SITE_URL="" \
    "$SMOKE_PYTHON" -c "${@: -1}"
}
curl() {
  local output="" url="" arg="" previous="" authenticated=0
  for arg in "$@"; do
    if [ "$previous" = "-o" ]; then output="$arg"; fi
    case "$arg" in
      http*) url="$arg" ;;
      Authorization:*) authenticated=1 ;;
      username=*) [ "$arg" = "username=$TEST_STATS_USER" ] || return 99 ;;
      password=*) [ "$arg" = "password=$TEST_STATS_PASS" ] || return 99 ;;
    esac
    previous="$arg"
  done
  case "$url" in
    */api/auth/login)
      printf '{"access_token":"test-token"}' > "$output"
      printf '%s' "$FAKE_LOGIN_STATUS" ;;
    */ws/*)
      printf '%s\n' "$url" >> smoke-ws-calls.txt
      printf '101' ;;
    */api/stats/leaderboard)
      if [ "$authenticated" = 1 ]; then printf '200'; else printf '401'; fi ;;
  esac
  return 0
}
"""
        for login_status, env_failure, expected_returncode in (
            ("200", "0", 0),
            ("500", "0", 1),
            ("401", "0", 1),
            ("200", "1", 1),
        ):
            with (
                self.subTest(login_status=login_status, env_failure=env_failure),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                (root / ".env").write_text("touch smoke-dotenv-executed\n", encoding="utf-8")
                (root / "deploy.sh").write_text("[ \"$1\" = --finalize ] && touch smoke-finalized\n", encoding="utf-8")
                password = "space ' quote $HOME `touch smoke-secret-executed` $(touch smoke-secret-executed)"
                smoke = root / "smoke.sh"
                smoke.write_text(fake_commands + script, encoding="utf-8")
                result = subprocess.run(
                    [_find_bash(), _bash_path(smoke)],
                    cwd=root,
                    env={
                        **os.environ,
                        "FAKE_LOGIN_STATUS": login_status,
                        "FAKE_ENV_FAILURE": env_failure,
                        "TEST_STATS_USER": "test admin",
                        "TEST_STATS_PASS": password,
                        "SMOKE_PYTHON": sys.executable,
                    },
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(
                    result.returncode, expected_returncode, result.stdout + result.stderr
                )
                ws_calls = root / "smoke-ws-calls.txt"
                self.assertFalse((root / "smoke-dotenv-executed").exists())
                self.assertFalse((root / "smoke-secret-executed").exists())
                self.assertNotIn(password, result.stdout + result.stderr)
                self.assertEqual((root / "smoke-finalized").exists(), expected_returncode == 0)
                if expected_returncode == 0:
                    self.assertIn("127.0.0.1:8080/ws/", ws_calls.read_text(encoding="utf-8"))
                else:
                    self.assertFalse(ws_calls.exists())

    @unittest.skipUnless(_find_bash(), "bash is required for the deploy entrypoint check")
    def test_deployment_rejects_unbound_tags_and_latest(self):
        for arguments in ([], ["latest"], ["a" * 40] * 4):
            result = subprocess.run([_find_bash(), _bash_path(DEPLOY_SCRIPT), *arguments],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn("--manifest", result.stderr)

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
        tree = ast.parse(SCHEDULER_MAIN.read_text(encoding="utf-8"))
        matching_jobs = []
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_job"
                and node.args
            ):
                continue
            handler = node.args[0]
            # A monitored function still has to schedule the real delivery worker.
            if (
                isinstance(handler, ast.Call)
                and isinstance(handler.func, ast.Name)
                and handler.func.id == "monitor_job"
            ):
                self.assertEqual(len(handler.args), 2)
                handler = handler.args[1]
            if (
                isinstance(handler, ast.Name)
                and handler.id == "deliver_pending_schedule_change_notifications"
            ):
                matching_jobs.append({keyword.arg: keyword.value for keyword in node.keywords})
        self.assertEqual(len(matching_jobs), 1)
        job = matching_jobs[0]
        self.assertEqual(ast.literal_eval(job["trigger"]), "interval")
        interval = sum(
            ast.literal_eval(job[key]) * multiplier
            for key, multiplier in (("seconds", 1), ("minutes", 60), ("hours", 3600))
            if key in job
        )
        self.assertGreater(interval, 0)
        self.assertLessEqual(interval, 60)

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
