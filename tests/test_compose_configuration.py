import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_COMPOSE = PROJECT_ROOT / "docker-compose.yml"
PRODUCTION_COMPOSE = PROJECT_ROOT / "docker-compose.prod.yml"
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


if __name__ == "__main__":
    unittest.main()
