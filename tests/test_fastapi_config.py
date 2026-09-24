import importlib
import os
import unittest
from unittest.mock import patch

from shared_lib.celery_app import get_celery_redis_url
from shared_lib.redis_client import RedisClient, get_redis_url


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
                "FASTAPI_RATE_LIMIT_SCHEDULE_DATA_LIMIT": "80",
                "SCHEDULE_INTERACTIVE_FRESHNESS_SECONDS": "240",
                "SCHEDULE_INTERACTIVE_LIVE_WAIT_SECONDS": "2.5",
            },
        ):
            reloaded = importlib.reload(config)

        self.assertEqual(reloaded.RATE_LIMIT_SCHEDULE_SEARCH.limit, 25)
        self.assertEqual(reloaded.RATE_LIMIT_SCHEDULE_SEARCH.window_seconds, 120)
        self.assertEqual(reloaded.RATE_LIMIT_SCHEDULE_DATA.limit, 80)
        self.assertEqual(reloaded.SCHEDULE_INTERACTIVE_FRESHNESS_SECONDS, 240)
        self.assertEqual(reloaded.SCHEDULE_INTERACTIVE_LIVE_WAIT_SECONDS, 2.5)


class TestRedisConfig(unittest.TestCase):
    def test_redis_url_preserves_password_database_and_tls(self):
        url = "rediss://:secret@redis.example:6380/4?socket_timeout=7"
        with patch.dict(os.environ, {"REDIS_URL": url}, clear=False):
            resolved_url = get_redis_url()
            client = RedisClient(url=resolved_url)

        kwargs = client.pool.connection_kwargs
        self.assertEqual(resolved_url, url)
        self.assertEqual(kwargs["host"], "redis.example")
        self.assertEqual(kwargs["port"], 6380)
        self.assertEqual(kwargs["db"], 4)
        self.assertEqual(kwargs["password"], "secret")
        self.assertEqual(kwargs["socket_timeout"], 7.0)
        self.assertEqual(client.pool.connection_class.__name__, "SSLConnection")

    def test_host_port_database_fallback_matches_celery(self):
        with patch.dict(
            os.environ,
            {
                "REDIS_URL": "",
                "REDIS_HOST": "cache.internal",
                "REDIS_PORT": "6381",
                "REDIS_DB": "6",
            },
            clear=False,
        ):
            self.assertEqual(get_redis_url(), "redis://cache.internal:6381/6")
            self.assertEqual(get_celery_redis_url(), get_redis_url())
