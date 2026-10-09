"""Regression coverage for catch-up identity and actual outbox recovery transitions."""

import unittest
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from scheduler_app.job_health import monitor_job
from shared_lib import schedule_outbox
from shared_lib.models import ScheduleChangeDelivery, User
from shared_lib.schedule_daily import (
    daily_event_key,
    daily_occurrence,
    deduplicate_daily_recipients,
)


class TestDailyOccurrence(unittest.TestCase):
    def test_cross_midnight_catchup_keeps_original_target_date(self):
        now = datetime(2026, 10, 9, 22, tzinfo=UTC)  # 01:00 Moscow on October 10
        result = daily_occurrence(time(23, 30), "Europe/Moscow", now)
        self.assertEqual(result["target_date"], date(2026, 10, 10))
        self.assertEqual(result["scheduled_at"], datetime(2026, 10, 9, 20, 30, tzinfo=UTC))

    def test_future_and_expired_occurrences_are_not_due(self):
        now = datetime(2026, 10, 9, 8, tzinfo=UTC)
        self.assertIsNone(daily_occurrence(time(12), "Europe/Moscow", now))
        self.assertIsNone(daily_occurrence(time(4), "Europe/Moscow", now))
        self.assertIsNone(daily_occurrence(None, "Europe/Moscow", now))

    def test_fixed_offset_and_boundary(self):
        now = datetime(2026, 10, 9, 8, tzinfo=UTC)
        self.assertEqual(
            daily_occurrence(time(13), "Etc/GMT-5", now)["target_date"], date(2026, 10, 10)
        )
        self.assertIsNone(daily_occurrence(time(5), "Europe/Moscow", now, 21600))
        with self.assertRaises(ValueError):
            daily_occurrence(time(11), "UTC", now.replace(tzinfo=None))

    def test_overlapping_profiles_deduplicate_and_prefer_private_chat(self):
        base = {
            "user_id": 10,
            "entity_type": "group",
            "entity_id": "1",
            "target_date": date(2026, 10, 10),
        }
        result = deduplicate_daily_recipients(
            [
                {**base, "id": 1, "chat_id": -42},
                {**base, "id": 3, "chat_id": 10},
                {**base, "id": 2, "chat_id": 10},
                {**base, "id": 4, "chat_id": 10, "entity_id": "2"},
                {**base, "id": 5, "chat_id": 11, "user_id": 11},
            ]
        )
        self.assertEqual(len(result), 3)
        self.assertEqual(
            next(item for item in result if item["user_id"] == 10 and item["entity_id"] == "1")[
                "id"
            ],
            2,
        )
        self.assertNotEqual(
            daily_event_key("group", "1", date(2026, 10, 10)),
            daily_event_key("group", "1", date(2026, 10, 11)),
        )


class TestOutboxRecovery(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        User.__table__.create(self.engine)
        ScheduleChangeDelivery.__table__.create(self.engine)
        with Session(self.engine) as session:
            session.add(User(user_id=10, full_name="Test"))
            session.commit()
        self.now = datetime(2026, 10, 9, 12, tzinfo=UTC)

        @asynccontextmanager
        async def sessions():
            with Session(self.engine) as session:

                class Adapter:
                    async def execute(self, statement):
                        return session.execute(statement)

                    async def commit(self):
                        session.commit()

                yield Adapter()

        self.patcher = patch.object(schedule_outbox, "get_session", sessions)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.engine.dispose)

    def insert(self, ident, **kwargs):
        with Session(self.engine) as session:
            session.add(
                ScheduleChangeDelivery(
                    id=ident,
                    event_key=f"event-{ident}",
                    user_id=10,
                    entity_type="group",
                    entity_id="1",
                    chat_id=10,
                    payload="Schedule",
                    next_attempt_at=self.now - timedelta(minutes=1),
                    created_at=self.now - timedelta(hours=1),
                    updated_at=self.now,
                    **kwargs,
                )
            )
            session.commit()

    def rows(self):
        with Session(self.engine) as session:
            return {
                row.id: (row.status, row.attempt_count, row.last_error)
                for row in session.scalars(select(ScheduleChangeDelivery))
            }

    async def test_final_attempt_crash_is_failed_not_stuck_processing(self):
        self.insert(
            1, status="processing", attempt_count=8, locked_at=self.now - timedelta(hours=1)
        )
        self.insert(2, status="processing", attempt_count=8, locked_at=self.now)
        self.insert(
            3, status="processing", attempt_count=7, locked_at=self.now - timedelta(hours=1)
        )
        claimed = await schedule_outbox.claim_schedule_change_deliveries(now_utc=self.now)
        self.assertEqual([item["id"] for item in claimed], [3])
        self.assertEqual(claimed[0]["attempt_count"], 8)
        self.assertEqual(self.rows()[1][0], "failed")
        self.assertIn("unconfirmed", self.rows()[1][2])
        self.assertEqual(self.rows()[2][0], "processing")

    async def test_expired_daily_messages_and_exhausted_pending_are_terminal(self):
        self.insert(
            1, status="pending", attempt_count=0, delivery_kind="daily", expires_at=self.now
        )
        self.insert(2, status="pending", attempt_count=8)
        self.insert(3, status="sent", attempt_count=1)
        self.assertEqual(
            await schedule_outbox.claim_schedule_change_deliveries(now_utc=self.now), []
        )
        self.assertEqual([row[0] for row in self.rows().values()], ["failed", "failed", "sent"])

    async def test_stale_worker_cannot_finalize_reclaimed_attempt(self):
        self.insert(
            1, status="processing", attempt_count=1, locked_at=self.now - timedelta(hours=1)
        )
        await schedule_outbox.claim_schedule_change_deliveries(now_utc=self.now)
        await schedule_outbox.mark_schedule_change_delivery_sent(
            1, expected_attempt_count=1, now_utc=self.now
        )
        self.assertEqual(self.rows()[1][:2], ("processing", 2))
        await schedule_outbox.reschedule_schedule_change_delivery(
            1, expected_attempt_count=1, error="late", delay_seconds=1
        )
        self.assertEqual(self.rows()[1][:2], ("processing", 2))
        await schedule_outbox.mark_schedule_change_delivery_sent(
            1, expected_attempt_count=2, now_utc=self.now
        )
        self.assertEqual(self.rows()[1][0], "sent")

    async def test_health_counts_oldest_pending_without_message_data(self):
        self.insert(1, status="pending", attempt_count=0)
        self.insert(2, status="failed", attempt_count=8)
        summary = await schedule_outbox.get_schedule_outbox_health(self.now)
        self.assertEqual(
            summary,
            {"pending": 1, "processing": 0, "failed": 1, "oldest_pending_age_seconds": 3600},
        )


class TestJobHealth(unittest.IsolatedAsyncioTestCase):
    async def test_partial_job_failure_does_not_advance_success_heartbeat(self):
        with patch("scheduler_app.job_health.record_operation", AsyncMock()) as record:
            result = await monitor_job("daily_schedules", AsyncMock(return_value={"failed": 1}))()
        self.assertEqual(result, {"failed": 1})
        self.assertFalse(record.await_args.kwargs["successful"])

    async def test_unexpected_failure_records_error_and_propagates(self):
        with patch("scheduler_app.job_health.record_operation", AsyncMock()) as record:
            with self.assertRaises(RuntimeError):
                await monitor_job(
                    "outbox_delivery", AsyncMock(side_effect=RuntimeError("private"))
                )()
        self.assertEqual(record.await_args.kwargs["error_code"], "job_exception")

    async def test_scheduler_health_rejects_stalled_jobs_or_old_outbox(self):
        from scheduler_app import main

        @asynccontextmanager
        async def database():
            from types import SimpleNamespace

            yield SimpleNamespace(execute=AsyncMock())

        cases = [
            (
                {
                    "available": True,
                    "operations": [
                        {"name": "daily_schedules", "status": "stale", "stale_after_seconds": 180}
                    ],
                },
                0,
            ),
            ({"available": True, "operations": []}, 1801),
            ({"available": False, "operations": []}, 0),
        ]
        for operations, age in cases:
            with (
                self.subTest(operations=operations, age=age),
                patch.object(main, "get_session", database),
                patch.object(main.redis_client.client, "llen", AsyncMock(return_value=0)),
                patch.object(main, "get_operational_snapshot", AsyncMock(return_value=operations)),
                patch.object(
                    main,
                    "get_schedule_outbox_health",
                    AsyncMock(return_value={"pending": 1, "oldest_pending_age_seconds": age}),
                ),
                patch.object(main, "SCHEDULE_OUTBOX_ALERT_AGE_SECONDS", 1800),
            ):
                _, code = await main.build_scheduler_health(True)
                self.assertEqual(code, 503)
