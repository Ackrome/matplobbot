import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from shared_lib.services import schedule_freshness


def _policy(**overrides):
    values = {
        "freshness_seconds": 180,
        "live_wait_seconds": 1.0,
        "initial_live_wait_seconds": 1.0,
        "lock_ttl_seconds": 30,
        "failure_cooldown_seconds": 30,
    }
    values.update(overrides)
    return values


class TestScheduleFreshness(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await schedule_freshness.shutdown_schedule_refresh_tasks()
        schedule_freshness.reset_schedule_refresh_state_for_tests()
        self.metric_patcher = patch.object(
            schedule_freshness,
            "record_schedule_fallback_metric",
            AsyncMock(),
        )
        self.metric_patcher.start()

    async def asyncTearDown(self):
        await schedule_freshness.shutdown_schedule_refresh_tasks()
        schedule_freshness.reset_schedule_refresh_state_for_tests()
        self.metric_patcher.stop()

    async def test_fresh_cache_skips_university_request(self):
        cached = [{"date": "2026-09-24", "discipline": "Math"}]
        client = SimpleNamespace(get_schedule=AsyncMock())

        with patch.object(
            schedule_freshness,
            "get_cached_schedule_snapshot",
            AsyncMock(return_value=(cached, datetime.now(UTC))),
        ):
            result = await schedule_freshness.get_schedule_with_freshness(
                client,
                "group",
                "42",
                "2026-09-20",
                "2026-09-30",
                **_policy(),
            )

        self.assertEqual(result.freshness, "fresh_cache")
        self.assertEqual(result.schedule, cached)
        client.get_schedule.assert_not_awaited()

    async def test_stale_cache_is_replaced_by_live_schedule(self):
        cached = [{"date": "2026-09-24", "discipline": "Old"}]
        live = [{"date": "2026-09-25", "discipline": "New"}]
        checked_at = datetime.now(UTC)
        client = SimpleNamespace(get_schedule=AsyncMock(return_value=live))

        with (
            patch.object(
                schedule_freshness,
                "get_cached_schedule_snapshot",
                AsyncMock(
                    side_effect=[
                        (cached, checked_at - timedelta(hours=2)),
                        (live, checked_at),
                    ]
                ),
            ),
            patch.object(
                schedule_freshness, "upsert_cached_schedule", AsyncMock()
            ) as upsert,
            patch.object(
                schedule_freshness,
                "_failure_cooldown_active",
                AsyncMock(return_value=False),
            ),
            patch.object(
                schedule_freshness,
                "_acquire_distributed_lock",
                AsyncMock(return_value="lease-token"),
            ),
            patch.object(
                schedule_freshness, "_release_distributed_lock", AsyncMock()
            ),
            patch.object(schedule_freshness, "_clear_refresh_failure", AsyncMock()),
        ):
            result = await schedule_freshness.get_schedule_with_freshness(
                client,
                "group",
                "42",
                "2026-09-20",
                "2026-09-30",
                **_policy(),
            )

        self.assertEqual(result.freshness, "live")
        self.assertTrue(result.content_changed)
        self.assertEqual(result.schedule, live)
        upsert.assert_awaited_once_with("group", "42", live)

    async def test_concurrent_viewers_share_one_upstream_request(self):
        cached = [{"date": "2026-09-24", "discipline": "Old"}]
        live = [{"date": "2026-09-24", "discipline": "Current"}]
        stale_at = datetime.now(UTC) - timedelta(hours=2)
        checked_at = datetime.now(UTC)
        refresh_started = asyncio.Event()
        allow_refresh = asyncio.Event()
        cache_updated = False

        async def get_schedule(*_args, **_kwargs):
            refresh_started.set()
            await allow_refresh.wait()
            return live

        async def load_snapshot(*_args):
            return (live, checked_at) if cache_updated else (cached, stale_at)

        async def upsert(*_args):
            nonlocal cache_updated
            cache_updated = True

        client = SimpleNamespace(get_schedule=AsyncMock(side_effect=get_schedule))

        with (
            patch.object(
                schedule_freshness,
                "get_cached_schedule_snapshot",
                AsyncMock(side_effect=load_snapshot),
            ),
            patch.object(
                schedule_freshness,
                "upsert_cached_schedule",
                AsyncMock(side_effect=upsert),
            ),
            patch.object(
                schedule_freshness,
                "_failure_cooldown_active",
                AsyncMock(return_value=False),
            ),
            patch.object(
                schedule_freshness,
                "_acquire_distributed_lock",
                AsyncMock(return_value="lease-token"),
            ),
            patch.object(
                schedule_freshness, "_release_distributed_lock", AsyncMock()
            ),
            patch.object(schedule_freshness, "_clear_refresh_failure", AsyncMock()),
        ):
            requests = [
                asyncio.create_task(
                    schedule_freshness.get_schedule_with_freshness(
                        client,
                        "group",
                        "42",
                        "2026-09-20",
                        "2026-09-30",
                        **_policy(),
                    )
                )
                for _ in range(20)
            ]
            await refresh_started.wait()
            allow_refresh.set()
            results = await asyncio.gather(*requests)

        self.assertEqual(client.get_schedule.await_count, 1)
        self.assertTrue(all(result.schedule == live for result in results))

    async def test_refresh_failure_serves_stale_cache(self):
        cached = [{"date": "2026-09-24", "discipline": "Cached"}]
        client = SimpleNamespace(get_schedule=AsyncMock(side_effect=RuntimeError("down")))

        with (
            patch.object(
                schedule_freshness,
                "get_cached_schedule_snapshot",
                AsyncMock(
                    return_value=(cached, datetime.now(UTC) - timedelta(days=1))
                ),
            ),
            patch.object(
                schedule_freshness,
                "_failure_cooldown_active",
                AsyncMock(return_value=False),
            ),
            patch.object(
                schedule_freshness,
                "_acquire_distributed_lock",
                AsyncMock(return_value="lease-token"),
            ),
            patch.object(
                schedule_freshness, "_release_distributed_lock", AsyncMock()
            ),
            patch.object(schedule_freshness, "_mark_refresh_failure", AsyncMock()),
        ):
            result = await schedule_freshness.get_schedule_with_freshness(
                client,
                "group",
                "42",
                "2026-09-20",
                "2026-09-30",
                **_policy(),
            )

        self.assertEqual(result.freshness, "stale_fallback")
        self.assertTrue(result.is_offline)
        self.assertEqual(result.schedule, cached)

    async def test_no_cache_and_upstream_failure_is_unavailable(self):
        client = SimpleNamespace(get_schedule=AsyncMock(side_effect=RuntimeError("down")))

        with (
            patch.object(
                schedule_freshness,
                "get_cached_schedule_snapshot",
                AsyncMock(return_value=(None, None)),
            ),
            patch.object(
                schedule_freshness,
                "_failure_cooldown_active",
                AsyncMock(return_value=False),
            ),
            patch.object(
                schedule_freshness,
                "_acquire_distributed_lock",
                AsyncMock(return_value="lease-token"),
            ),
            patch.object(
                schedule_freshness, "_release_distributed_lock", AsyncMock()
            ),
            patch.object(schedule_freshness, "_mark_refresh_failure", AsyncMock()),
        ):
            with self.assertRaises(schedule_freshness.ScheduleUnavailableError):
                await schedule_freshness.get_schedule_with_freshness(
                    client,
                    "group",
                    "42",
                    "2026-09-20",
                    "2026-09-30",
                    **_policy(),
                )

    async def test_successful_empty_response_clears_old_schedule(self):
        cached = [{"date": "2026-09-24", "discipline": "Removed"}]
        checked_at = datetime.now(UTC)
        client = SimpleNamespace(get_schedule=AsyncMock(return_value=[]))

        with (
            patch.object(
                schedule_freshness,
                "get_cached_schedule_snapshot",
                AsyncMock(
                    side_effect=[
                        (cached, checked_at - timedelta(hours=2)),
                        ([], checked_at),
                    ]
                ),
            ),
            patch.object(
                schedule_freshness, "upsert_cached_schedule", AsyncMock()
            ) as upsert,
            patch.object(
                schedule_freshness,
                "_failure_cooldown_active",
                AsyncMock(return_value=False),
            ),
            patch.object(
                schedule_freshness,
                "_acquire_distributed_lock",
                AsyncMock(return_value="lease-token"),
            ),
            patch.object(
                schedule_freshness, "_release_distributed_lock", AsyncMock()
            ),
            patch.object(schedule_freshness, "_clear_refresh_failure", AsyncMock()),
        ):
            result = await schedule_freshness.get_schedule_with_freshness(
                client,
                "group",
                "42",
                "2026-09-20",
                "2026-09-30",
                **_policy(),
            )

        self.assertEqual(result.freshness, "live")
        self.assertEqual(result.schedule, [])
        self.assertTrue(result.content_changed)
        upsert.assert_awaited_once_with("group", "42", [])


if __name__ == "__main__":
    unittest.main()
