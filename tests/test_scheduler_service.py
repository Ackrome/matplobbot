import importlib
import sys
import types
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import aiohttp

fake_schedule_service = types.ModuleType("shared_lib.services.schedule_service")
fake_schedule_service.diff_schedules = lambda *args, **kwargs: ""


async def _fake_format_schedule(*args, **kwargs):
    return ""


fake_schedule_service.format_schedule = _fake_format_schedule
from scheduler_app.http_client import (
    build_telegram_http_client_config,
    normalize_proxy_url,
)

with patch.dict(
    sys.modules,
    {"shared_lib.services.schedule_service": fake_schedule_service},
):
    jobs = importlib.import_module("scheduler_app.jobs")

scheduler_config = importlib.import_module("scheduler_app.config")


class _AsyncSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestSchedulerHttpClient(unittest.TestCase):
    def test_normalize_proxy_url_uses_socks5h_for_socks_proxy(self):
        self.assertEqual(
            normalize_proxy_url("socks5://proxy:20170"),
            "socks5h://proxy:20170",
        )

    def test_build_telegram_http_client_config_uses_socks_connector_for_socks_proxy(self):
        timeout = aiohttp.ClientTimeout(total=30)
        fake_proxy_connector = Mock()
        fake_proxy_connector.from_url.return_value = "connector-sentinel"
        fake_aiohttp_socks = types.ModuleType("aiohttp_socks")
        fake_aiohttp_socks.ProxyConnector = fake_proxy_connector

        with patch.dict(
            sys.modules,
            {"aiohttp_socks": fake_aiohttp_socks},
        ):
            session_kwargs, request_kwargs = build_telegram_http_client_config(
                timeout, "socks5://proxy:20170"
            )

        self.assertEqual(session_kwargs["timeout"], timeout)
        self.assertEqual(session_kwargs["connector"], "connector-sentinel")
        self.assertEqual(request_kwargs, {})
        fake_proxy_connector.from_url.assert_called_once_with("socks5h://proxy:20170")

    def test_build_telegram_http_client_config_uses_request_proxy_for_http_proxy(self):
        timeout = aiohttp.ClientTimeout(total=30)

        session_kwargs, request_kwargs = build_telegram_http_client_config(
            timeout, "http://proxy.local:8080"
        )

        self.assertEqual(session_kwargs, {"timeout": timeout})
        self.assertEqual(request_kwargs, {"proxy": "http://proxy.local:8080"})


class TestSchedulerJobs(unittest.IsolatedAsyncioTestCase):
    async def test_send_telegram_message_returns_none_on_transport_error(self):
        session = Mock()
        session.post.side_effect = aiohttp.ClientConnectionError("proxy down")

        result = await jobs.send_telegram_message(session, 42, "hello")

        self.assertIsNone(result)

    async def test_send_daily_schedules_raises_when_every_delivery_fails(self):
        subscriptions = [
            {
                "id": 1,
                "user_id": 10,
                "chat_id": 100,
                "message_thread_id": None,
                "entity_type": "group",
                "entity_id": "123",
                "entity_name": "M80-101",
                "last_schedule_hash": None,
            }
        ]
        ruz_api_client = SimpleNamespace(
            get_schedule=AsyncMock(return_value=[{"discipline": "Math"}])
        )

        with (
            patch.object(
                jobs,
                "get_subscriptions_for_notification",
                AsyncMock(return_value=subscriptions),
            ),
            patch.object(jobs.translator, "get_language", AsyncMock(return_value="en")),
            patch.object(jobs, "format_schedule", AsyncMock(return_value="Schedule text")),
            patch.object(jobs, "send_telegram_message", AsyncMock(return_value=None)),
        ):
            with self.assertRaises(RuntimeError):
                await jobs.send_daily_schedules(object(), ruz_api_client)

    async def test_send_admin_summary_raises_when_matching_admin_delivery_fails(self):
        now_in_moscow = datetime.now(ZoneInfo("Europe/Moscow"))
        current_time_str = now_in_moscow.strftime("%H:%M")
        current_weekday = now_in_moscow.weekday()

        fake_db = _AsyncSessionContext()

        with (
            patch.object(scheduler_config, "ADMIN_USER_IDS", [777]),
            patch.object(
                jobs,
                "get_user_settings",
                AsyncMock(
                    return_value={
                        "admin_daily_summary_time": current_time_str,
                        "admin_summary_days": [current_weekday],
                    }
                ),
            ),
            patch.object(jobs.translator, "get_language", AsyncMock(return_value="en")),
            patch.object(jobs.translator, "gettext", return_value="Summary"),
            patch.object(jobs, "get_session", return_value=fake_db),
            patch.object(
                jobs,
                "get_admin_daily_summary",
                AsyncMock(
                    return_value={
                        "new_users": 1,
                        "total_actions": 2,
                        "new_subscriptions": 3,
                        "new_suggestions": 4,
                    }
                ),
            ),
            patch.object(jobs.redis_client.client, "lrange", AsyncMock(return_value=[])),
            patch.object(jobs, "send_telegram_message", AsyncMock(return_value=None)),
        ):
            with self.assertRaises(RuntimeError):
                await jobs.send_admin_summary(object())
