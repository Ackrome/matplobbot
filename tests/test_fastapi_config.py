import importlib
import os
import unittest
from unittest.mock import patch


class TestFastAPIConfig(unittest.TestCase):
    def tearDown(self):
        import fastapi_stats_app.config as config

        importlib.reload(config)

    def test_cors_allowed_origins_can_be_loaded_from_env(self):
        import fastapi_stats_app.config as config

        with patch.dict(
            os.environ,
            {"FASTAPI_CORS_ALLOWED_ORIGINS": "https://one.example, https://two.example"},
        ):
            reloaded = importlib.reload(config)

        self.assertEqual(
            reloaded.CORS_ALLOWED_ORIGINS,
            ["https://one.example", "https://two.example"],
        )

    def test_rate_limit_settings_can_be_loaded_from_env(self):
        import fastapi_stats_app.config as config

        with patch.dict(
            os.environ,
            {
                "FASTAPI_RATE_LIMIT_SCHEDULE_SEARCH_LIMIT": "25",
                "FASTAPI_RATE_LIMIT_SCHEDULE_SEARCH_WINDOW_SECONDS": "120",
            },
        ):
            reloaded = importlib.reload(config)

        self.assertEqual(reloaded.RATE_LIMIT_SCHEDULE_SEARCH.limit, 25)
        self.assertEqual(reloaded.RATE_LIMIT_SCHEDULE_SEARCH.window_seconds, 120)
