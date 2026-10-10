"""Safety boundaries for the disposable real-service rollback drill."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rollback_drill


class RollbackDrillSafetyTests(unittest.TestCase):
    def test_every_service_is_internal_without_host_ports_or_privileged_mounts(self):
        compose = rollback_drill.fixture_compose("synthetic-api", "synthetic-bot")
        self.assertEqual(compose["networks"], {"isolated": {"internal": True}})
        readiness = compose["services"]["postgres"]["healthcheck"]["test"]
        self.assertEqual(readiness[readiness.index("-h") + 1], "127.0.0.1")
        for name, service in compose["services"].items():
            with self.subTest(service=name):
                self.assertEqual(service["networks"], ["isolated"])
                self.assertNotIn("ports", service)
                self.assertNotIn("network_mode", service)
                self.assertFalse(service.get("privileged"))
                for volume in service.get("volumes", []):
                    self.assertIn(
                        volume, {"db:/var/lib/postgresql/data", "./main_site_frontend:/fixture:ro"}
                    )

    def test_provider_capable_roles_are_idle_and_only_api_is_real(self):
        services = rollback_drill.fixture_compose("synthetic-api", "synthetic-bot")["services"]
        self.assertNotIn("command", services["mpb-fastapi-stats"])
        self.assertEqual(services["migrator"]["command"], ["alembic", "upgrade", "head"])
        for name in ("mpb-telegram-bot", "mpb-scheduler", "mpb-worker", "caddy", "proxy"):
            self.assertEqual(
                services[name]["command"], ["python", "-c", "import time; time.sleep(3600)"]
            )

    def test_fixture_credentials_do_not_inherit_operator_environment(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "operator-database",
                "STATS_PASS": "operator-secret",
                "BOT_TOKEN": "operator-token",
            },
        ):
            values = rollback_drill.fixture_environment("synthetic-test-password")
        self.assertNotIn("operator-", values)
        self.assertIn("STATS_PASS=synthetic-test-password\n", values)
        self.assertIn("@postgres:5432/drill\n", values)
        self.assertIn("MPB_ISOLATED_RC=1\n", values)


if __name__ == "__main__":
    unittest.main()
