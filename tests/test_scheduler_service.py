import hashlib
import importlib
import json
import sys
import types
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import aiohttp

fake_schedule_service = types.ModuleType("shared_lib.services.schedule_service")
fake_schedule_service.diff_schedules = lambda *args, **kwargs: ""
fake_schedule_service.get_semester_bounds = lambda: ("2026-08-25", "2027-01-31")
fake_schedule_service.refresh_cached_schedule_entity_ids_and_semester_cache = AsyncMock(
    return_value={
        "total": 0,
        "processed": 0,
        "refreshed": 0,
        "remapped": 0,
        "skipped": 0,
        "failed": 0,
        "subscriptions_updated": 0,
        "subscriptions_merged": 0,
        "web_profiles_updated": 0,
    }
)


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
schedule_outbox = importlib.import_module("shared_lib.schedule_outbox")


class _AsyncSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _BoundAsyncSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeTelegramResponse:
    def __init__(self, status, payload=None, text=""):
        self.status = status
        self._payload = payload or {}
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return self._text


class TestSchedulerHttpClient(unittest.TestCase):
    def test_normalize_proxy_url_keeps_connector_compatible_socks_scheme(self):
        self.assertEqual(
            normalize_proxy_url("socks5://proxy:20170"),
            "socks5://proxy:20170",
        )
        self.assertEqual(
            normalize_proxy_url("socks5h://proxy:20170"),
            "socks5://proxy:20170",
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
        fake_proxy_connector.from_url.assert_called_once_with("socks5://proxy:20170")

    def test_build_telegram_http_client_config_uses_request_proxy_for_http_proxy(self):
        timeout = aiohttp.ClientTimeout(total=30)

        session_kwargs, request_kwargs = build_telegram_http_client_config(
            timeout, "http://proxy.local:8080"
        )

        self.assertEqual(session_kwargs, {"timeout": timeout})
        self.assertEqual(request_kwargs, {"proxy": "http://proxy.local:8080"})


class TestSchedulerJobs(unittest.IsolatedAsyncioTestCase):
    async def test_schedule_transition_commits_outbox_cache_and_hash_atomically(self):
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(rowcount=1)

        with patch.object(
            schedule_outbox,
            "get_session",
            return_value=_BoundAsyncSessionContext(session),
        ):
            inserted = await schedule_outbox.commit_schedule_change_transition(
                event_key="a" * 64,
                entity_type="group",
                entity_id="123",
                entity_name="M80-101",
                schedule_data=[{"discipline": "Math"}],
                new_hash="new-hash",
                deliveries=[
                    {
                        "user_id": 10,
                        "chat_id": 10,
                        "message_thread_id": None,
                        "payload": "Changed",
                    }
                ],
            )

        self.assertEqual(inserted, 1)
        self.assertEqual(session.execute.await_count, 3)
        session.commit.assert_awaited_once()
        statements = [str(call.args[0]) for call in session.execute.await_args_list]
        self.assertIn("schedule_change_deliveries", statements[0])
        self.assertIn("cached_schedules", statements[1])
        self.assertIn("user_schedule_subscriptions", statements[2])

    async def test_send_telegram_message_returns_none_on_transport_error(self):
        session = Mock()
        session.post.side_effect = aiohttp.ClientConnectionError("proxy down")

        result = await jobs.send_telegram_message(session, 42, "hello", retry_attempts=0)

        self.assertIsNone(result)

    async def test_send_telegram_message_retries_transport_error(self):
        session = Mock()
        session.post.side_effect = [
            aiohttp.ClientConnectionError("proxy down"),
            _FakeTelegramResponse(200, {"result": {"message_id": 7}}),
        ]

        with patch.object(jobs.asyncio, "sleep", AsyncMock()) as sleep:
            result = await jobs.send_telegram_message(
                session,
                42,
                "hello",
                retry_attempts=1,
                retry_delay_seconds=0.25,
            )

        self.assertEqual(result, {"message_id": 7})
        self.assertEqual(session.post.call_count, 2)
        sleep.assert_awaited_once_with(0.25)

    async def test_send_telegram_message_honors_telegram_retry_after(self):
        session = Mock()
        session.post.side_effect = [
            _FakeTelegramResponse(
                429,
                {"parameters": {"retry_after": 3}},
                text="rate limited",
            ),
            _FakeTelegramResponse(200, {"result": {"message_id": 8}}),
        ]

        with patch.object(jobs.asyncio, "sleep", AsyncMock()) as sleep:
            result = await jobs.send_telegram_message(
                session,
                42,
                "hello",
                retry_attempts=1,
                retry_delay_seconds=0.25,
            )

        self.assertEqual(result, {"message_id": 8})
        sleep.assert_awaited_once_with(3.0)

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
                "get_subscriptions_due_for_notification",
                AsyncMock(return_value=subscriptions),
            ),
            patch.object(
                jobs,
                "get_subscriptions_for_notification",
                AsyncMock(return_value=subscriptions),
            ),
            patch.object(jobs.translator, "get_language", AsyncMock(return_value="en")),
            patch.object(jobs, "format_schedule", AsyncMock(return_value="Schedule text")),
            patch.object(jobs, "send_telegram_message", AsyncMock(return_value=None)),
            self.assertRaises(RuntimeError),
        ):
            await jobs.send_daily_schedules(object(), ruz_api_client)

    async def test_send_daily_schedules_uses_timestamped_cache_fallback(self):
        subscriptions = [
            {
                "id": 1,
                "user_id": 10,
                "chat_id": 100,
                "message_thread_id": None,
                "entity_type": "group",
                "entity_id": "123",
                "entity_name": "M80-101",
                "timezone": "Europe/Moscow",
            }
        ]
        source_checked_at = datetime(2026, 9, 24, 15, 30, tzinfo=UTC)
        ruz_api_client = SimpleNamespace(
            get_schedule=AsyncMock(side_effect=RuntimeError("RUZ is down"))
        )

        with (
            patch.object(
                jobs,
                "get_subscriptions_due_for_notification",
                AsyncMock(return_value=subscriptions),
            ),
            patch.object(
                jobs,
                "get_cached_schedule_snapshot",
                AsyncMock(return_value=([{"discipline": "Math"}], source_checked_at)),
            ),
            patch.object(jobs.translator, "get_language", AsyncMock(return_value="en")),
            patch.object(
                jobs.translator,
                "gettext",
                side_effect=lambda _lang, _key, **kwargs: f"Cached; checked {kwargs['checked_at']}",
            ),
            patch.object(jobs, "format_schedule", AsyncMock(return_value="Schedule text")),
            patch.object(
                jobs,
                "send_telegram_message",
                AsyncMock(return_value={"message_id": 1}),
            ) as send_message,
            patch.object(jobs.asyncio, "sleep", AsyncMock()),
        ):
            await jobs.send_daily_schedules(object(), ruz_api_client)

        sent_text = send_message.await_args.args[2]
        self.assertIn("Schedule text", sent_text)
        self.assertIn("2026-09-24 18:30 MSK", sent_text)

    async def test_send_daily_schedules_raises_without_live_or_cached_source(self):
        subscriptions = [
            {
                "id": 1,
                "user_id": 10,
                "chat_id": 100,
                "entity_type": "group",
                "entity_id": "123",
                "entity_name": "M80-101",
            }
        ]
        ruz_api_client = SimpleNamespace(
            get_schedule=AsyncMock(side_effect=RuntimeError("RUZ is down"))
        )

        with (
            patch.object(
                jobs,
                "get_subscriptions_due_for_notification",
                AsyncMock(return_value=subscriptions),
            ),
            patch.object(
                jobs,
                "get_cached_schedule_snapshot",
                AsyncMock(return_value=(None, None)),
            ),
            self.assertRaisesRegex(RuntimeError, "could not fetch any schedule data"),
        ):
            await jobs.send_daily_schedules(object(), ruz_api_client)

    async def test_send_daily_schedules_continues_after_one_entity_has_no_source(self):
        subscriptions = [
            {
                "id": 1,
                "user_id": 10,
                "chat_id": 100,
                "entity_type": "group",
                "entity_id": "missing",
                "entity_name": "Missing",
            },
            {
                "id": 2,
                "user_id": 20,
                "chat_id": 200,
                "entity_type": "group",
                "entity_id": "live",
                "entity_name": "Live",
            },
        ]
        ruz_api_client = SimpleNamespace(
            get_schedule=AsyncMock(
                side_effect=[RuntimeError("RUZ error for one entity"), [{"discipline": "Math"}]]
            )
        )

        with (
            patch.object(
                jobs,
                "get_subscriptions_due_for_notification",
                AsyncMock(return_value=subscriptions),
            ),
            patch.object(
                jobs,
                "get_cached_schedule_snapshot",
                AsyncMock(return_value=(None, None)),
            ),
            patch.object(jobs.translator, "get_language", AsyncMock(return_value="en")),
            patch.object(jobs, "format_schedule", AsyncMock(return_value="Schedule text")),
            patch.object(
                jobs,
                "send_telegram_message",
                AsyncMock(return_value={"message_id": 1}),
            ) as send_message,
            patch.object(jobs.asyncio, "sleep", AsyncMock()),
        ):
            await jobs.send_daily_schedules(object(), ruz_api_client)

        send_message.assert_awaited_once()
        self.assertEqual(send_message.await_args.args[1], 200)

    async def test_outbox_retries_only_failed_recipient(self):
        first_batch = [
            {
                "id": 1,
                "chat_id": 101,
                "message_thread_id": None,
                "payload": "first",
                "attempt_count": 1,
            },
            {
                "id": 2,
                "chat_id": 102,
                "message_thread_id": None,
                "payload": "second",
                "attempt_count": 1,
            },
        ]
        retry_batch = [{**first_batch[1], "attempt_count": 2}]

        with (
            patch.object(
                jobs,
                "claim_schedule_change_deliveries",
                AsyncMock(side_effect=[first_batch, retry_batch]),
            ),
            patch.object(
                jobs,
                "send_telegram_message",
                AsyncMock(side_effect=[{"message_id": 1}, None, {"message_id": 2}]),
            ) as send_message,
            patch.object(jobs, "mark_schedule_change_delivery_sent", AsyncMock()) as mark_sent,
            patch.object(jobs, "reschedule_schedule_change_delivery", AsyncMock()) as reschedule,
        ):
            first_summary = await jobs.deliver_pending_schedule_change_notifications(object())
            second_summary = await jobs.deliver_pending_schedule_change_notifications(object())

        self.assertEqual(first_summary, {"claimed": 2, "sent": 1, "rescheduled": 1, "failed": 0})
        self.assertEqual(second_summary, {"claimed": 1, "sent": 1, "rescheduled": 0, "failed": 0})
        self.assertEqual([call.args[1] for call in send_message.await_args_list], [101, 102, 102])
        self.assertEqual([call.args[0] for call in mark_sent.await_args_list], [1, 2])
        reschedule.assert_awaited_once()
        self.assertEqual(reschedule.await_args.args[0], 2)

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
            self.assertRaises(RuntimeError),
        ):
            await jobs.send_admin_summary(object())

    async def test_check_for_schedule_updates_refreshes_cache_when_hash_is_unchanged(self):
        schedule_data = [{"date": "2026.08.21", "discipline": "Math"}]
        existing_hash = hashlib.sha256(
            json.dumps(schedule_data, sort_keys=True).encode()
        ).hexdigest()
        subscriptions = [
            {
                "id": 1,
                "user_id": 10,
                "chat_id": 100,
                "message_thread_id": None,
                "entity_type": "group",
                "entity_id": "123",
                "entity_name": "M80-101",
                "last_schedule_hash": existing_hash,
            }
        ]
        ruz_api_client = SimpleNamespace(get_schedule=AsyncMock(return_value=schedule_data))

        with (
            patch.object(
                jobs,
                "deliver_pending_schedule_change_notifications",
                AsyncMock(return_value={}),
            ),
            patch.object(
                jobs, "get_all_active_subscriptions", AsyncMock(return_value=subscriptions)
            ),
            patch.object(jobs, "get_all_short_names", AsyncMock(return_value={})),
            patch.object(jobs, "batch_update_subscription_hashes", AsyncMock()) as update_hashes,
            patch.object(jobs, "upsert_cached_schedule", AsyncMock()) as upsert_cache,
            patch.object(jobs.asyncio, "sleep", AsyncMock()),
        ):
            await jobs.check_for_schedule_updates(object(), ruz_api_client)

        upsert_cache.assert_awaited_once_with("group", "123", schedule_data)
        update_hashes.assert_awaited_once_with("group", "123", existing_hash)

    async def test_check_for_schedule_updates_commits_one_delivery_per_user(self):
        old_schedule = [{"date": "2026.09.24", "discipline": "Old"}]
        new_schedule = [{"date": "2026.09.24", "discipline": "New"}]
        source_checked_at = datetime(2026, 9, 24, 15, 0, tzinfo=UTC)
        subscriptions = [
            {
                "id": 1,
                "user_id": 10,
                "chat_id": -100,
                "message_thread_id": 7,
                "entity_type": "group",
                "entity_id": "123",
                "entity_name": "M80-101",
                "last_schedule_hash": "old-hash",
            },
            {
                "id": 2,
                "user_id": 10,
                "chat_id": 10,
                "message_thread_id": None,
                "entity_type": "group",
                "entity_id": "123",
                "entity_name": "M80-101",
                "last_schedule_hash": "old-hash",
            },
        ]
        ruz_api_client = SimpleNamespace(get_schedule=AsyncMock(return_value=new_schedule))

        with (
            patch.object(
                jobs,
                "deliver_pending_schedule_change_notifications",
                AsyncMock(return_value={}),
            ),
            patch.object(
                jobs, "get_all_active_subscriptions", AsyncMock(return_value=subscriptions)
            ),
            patch.object(jobs, "get_all_short_names", AsyncMock(return_value={})),
            patch.object(
                jobs,
                "get_cached_schedule_snapshot",
                AsyncMock(return_value=(old_schedule, source_checked_at)),
            ),
            patch.object(jobs.translator, "get_language", AsyncMock(return_value="en")),
            patch.object(jobs.translator, "gettext", return_value="Changed"),
            patch.object(jobs, "diff_schedules", return_value="Diff"),
            patch.object(
                jobs, "commit_schedule_change_transition", AsyncMock(return_value=1)
            ) as commit_transition,
            patch.object(jobs.asyncio, "sleep", AsyncMock()),
        ):
            await jobs.check_for_schedule_updates(object(), ruz_api_client)

        commit_transition.assert_awaited_once()
        kwargs = commit_transition.await_args.kwargs
        self.assertEqual(kwargs["entity_type"], "group")
        self.assertEqual(kwargs["entity_id"], "123")
        self.assertEqual(kwargs["schedule_data"], new_schedule)
        self.assertEqual(len(kwargs["deliveries"]), 1)
        self.assertEqual(kwargs["deliveries"][0]["chat_id"], 10)
        self.assertEqual(kwargs["deliveries"][0]["payload"], "Changed\n\nDiff")

    async def test_check_for_schedule_updates_repairs_hashes_without_duplicate_event(self):
        schedule_data = [{"date": "2026.09.24", "discipline": "Math"}]
        current_hash = hashlib.sha256(
            json.dumps(schedule_data, sort_keys=True).encode()
        ).hexdigest()
        subscriptions = [
            {
                "id": 1,
                "user_id": 10,
                "chat_id": 10,
                "entity_type": "group",
                "entity_id": "123",
                "entity_name": "M80-101",
                "last_schedule_hash": "stale-hash",
            },
            {
                "id": 2,
                "user_id": 20,
                "chat_id": 20,
                "entity_type": "group",
                "entity_id": "123",
                "entity_name": "M80-101",
                "last_schedule_hash": current_hash,
            },
        ]
        ruz_api_client = SimpleNamespace(get_schedule=AsyncMock(return_value=schedule_data))

        with (
            patch.object(
                jobs,
                "deliver_pending_schedule_change_notifications",
                AsyncMock(return_value={}),
            ),
            patch.object(
                jobs, "get_all_active_subscriptions", AsyncMock(return_value=subscriptions)
            ),
            patch.object(jobs, "get_all_short_names", AsyncMock(return_value={})),
            patch.object(
                jobs, "commit_schedule_change_transition", AsyncMock()
            ) as commit_transition,
            patch.object(jobs, "upsert_cached_schedule", AsyncMock()),
            patch.object(jobs, "batch_update_subscription_hashes", AsyncMock()) as update_hashes,
            patch.object(jobs.asyncio, "sleep", AsyncMock()),
        ):
            await jobs.check_for_schedule_updates(object(), ruz_api_client)

        commit_transition.assert_not_awaited()
        update_hashes.assert_awaited_once_with("group", "123", current_hash)

    async def test_check_for_schedule_updates_does_not_advance_legacy_checkpoint_on_commit_failure(
        self,
    ):
        old_schedule = [{"date": "2026.09.24", "discipline": "Old"}]
        new_schedule = [{"date": "2026.09.24", "discipline": "New"}]
        subscriptions = [
            {
                "id": 1,
                "user_id": 10,
                "chat_id": 10,
                "entity_type": "group",
                "entity_id": "123",
                "entity_name": "M80-101",
                "last_schedule_hash": "old-hash",
            }
        ]
        ruz_api_client = SimpleNamespace(get_schedule=AsyncMock(return_value=new_schedule))

        with (
            patch.object(
                jobs,
                "deliver_pending_schedule_change_notifications",
                AsyncMock(return_value={}),
            ),
            patch.object(
                jobs, "get_all_active_subscriptions", AsyncMock(return_value=subscriptions)
            ),
            patch.object(jobs, "get_all_short_names", AsyncMock(return_value={})),
            patch.object(
                jobs,
                "get_cached_schedule_snapshot",
                AsyncMock(return_value=(old_schedule, datetime.now(UTC))),
            ),
            patch.object(jobs.translator, "get_language", AsyncMock(return_value="en")),
            patch.object(jobs.translator, "gettext", return_value="Changed"),
            patch.object(jobs, "diff_schedules", return_value="Diff"),
            patch.object(
                jobs,
                "commit_schedule_change_transition",
                AsyncMock(side_effect=RuntimeError("database unavailable")),
            ),
            patch.object(jobs, "batch_update_subscription_hashes", AsyncMock()) as update_hashes,
            patch.object(jobs, "upsert_cached_schedule", AsyncMock()) as upsert_cache,
            patch.object(jobs.asyncio, "sleep", AsyncMock()),
        ):
            await jobs.check_for_schedule_updates(object(), ruz_api_client)

        update_hashes.assert_not_awaited()
        upsert_cache.assert_not_awaited()

    def test_schedule_change_event_key_is_stable_for_retry_and_unique_for_later_cycle(self):
        checked_at = datetime(2026, 9, 24, 15, 0, tzinfo=UTC)
        first = jobs.build_schedule_change_event_key("group", "123", "old", "new", checked_at)
        retry = jobs.build_schedule_change_event_key("group", "123", "old", "new", checked_at)
        later = jobs.build_schedule_change_event_key(
            "group", "123", "old", "new", datetime(2026, 9, 24, 16, 0, tzinfo=UTC)
        )

        self.assertEqual(first, retry)
        self.assertNotEqual(first, later)

    async def test_update_schedule_cache_uses_shared_semester_bounds(self):
        schedule_data = [{"date": "2026.08.27", "discipline": "Math"}]
        entities = [
            {
                "entity_type": "group",
                "entity_id": "162426",
                "entity_name": "ПМ23-1",
            }
        ]
        ruz_api_client = SimpleNamespace(get_schedule=AsyncMock(return_value=schedule_data))

        with (
            patch.object(
                jobs, "get_unique_active_subscription_entities", AsyncMock(return_value=entities)
            ),
            patch.object(jobs, "upsert_cached_schedule", AsyncMock()) as upsert_cache,
            patch.object(jobs.asyncio, "sleep", AsyncMock()),
        ):
            await jobs.update_schedule_cache(object(), ruz_api_client)

        ruz_api_client.get_schedule.assert_awaited_once_with(
            "group", "162426", start="2026-08-25", finish="2027-01-31"
        )
        upsert_cache.assert_awaited_once_with("group", "162426", schedule_data)

    async def test_refresh_schedule_entity_ids_delegates_to_cache_refresh_service(self):
        ruz_api_client = SimpleNamespace()
        service_result = {
            "total": 1,
            "processed": 1,
            "refreshed": 1,
            "remapped": 1,
            "skipped": 0,
            "failed": 0,
            "subscriptions_updated": 2,
            "subscriptions_merged": 0,
            "web_profiles_updated": 1,
        }

        with patch.object(
            jobs,
            "refresh_cached_schedule_entity_ids_and_semester_cache",
            AsyncMock(return_value=service_result),
        ) as refresh_service:
            await jobs.refresh_schedule_entity_ids(ruz_api_client)

        refresh_service.assert_awaited_once_with(ruz_api_client)
