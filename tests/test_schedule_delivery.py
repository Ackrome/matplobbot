"""Regression coverage for catch-up identity and actual outbox recovery transitions."""

import copy
import importlib.util
import os
import unittest
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time, timedelta
from html import unescape
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import JSON, Integer, MetaData, UniqueConstraint, create_engine, select
from sqlalchemy.dialects.postgresql import dialect as pg_dialect
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlalchemy.orm import Session

from scheduler_app.job_health import monitor_job
from shared_lib import database, schedule_history, schedule_outbox
from shared_lib.models import (
    CachedSchedule,
    ScheduleChangeDelivery,
    ScheduleHistoryEntry,
    ScheduleNotificationSnapshot,
    User,
    UserScheduleSubscription,
)
from shared_lib.schedule_daily import (
    daily_event_key,
    daily_occurrence,
    deduplicate_daily_recipients,
)


def _history_lesson(oid, date_value, **fields):
    return {
        "lessonOid": oid,
        "date": date_value,
        "beginLesson": "09:00",
        "endLesson": "10:30",
        "discipline": "Math",
        "kindOfWork": "Lecture",
        "group": "Test group",
        "auditorium": "A",
        "lecturer_title": "Teacher",
        **fields,
    }


class TestScheduleHistoryDiff(unittest.TestCase):
    def test_material_changes_are_stable_and_exclude_private_upstream_fields(self):
        before = [
            _history_lesson(1, "2026-11-20", lecturerEmail="not-public@example.test"),
            _history_lesson(2, "2026-11-21"),
            _history_lesson(3, "2026-11-22"),
            _history_lesson(4, "2026-11-23"),
        ]
        after = [
            _history_lesson(1, "2026-11-24", auditorium="B"),
            _history_lesson(8, "2026-11-21", discipline="Physics", lecturer_title="Other"),
            _history_lesson(5, "2026-11-26"),
            _history_lesson(4, "2026-11-23", unrelatedProviderValue="ignored"),
        ]
        scope = {
            "semester_start": "2026-09-01",
            "semester_end": "2027-01-31",
            "today": date(2026, 11, 14),
        }
        changes = schedule_history.build_schedule_history(before, after, **scope)
        self.assertEqual(
            [change["kind"] for change in changes], ["replaced", "cancelled", "moved", "added"]
        )
        self.assertEqual(changes[0]["fields"], ["discipline", "teacher"])
        self.assertEqual(changes[2]["fields"], ["date", "room"])
        self.assertNotIn("lecturerEmail", changes[2]["before"])
        self.assertEqual(
            changes,
            schedule_history.build_schedule_history(before[::-1], after[::-1], **scope),
        )
        self.assertEqual(
            schedule_history.build_schedule_history(before, after + [{"date": "invalid"}], **scope),
            [],
        )
        self.assertEqual(
            schedule_history.build_schedule_history(
                [_history_lesson(1, "2026-11-20"), _history_lesson(2, "2026-11-20", discipline="Parallel")],
                [_history_lesson(3, "2026-11-20"), _history_lesson(4, "2026-11-20", discipline="Parallel")],
                **scope,
            ),
            [],
        )
        self.assertEqual(
            schedule_history.build_schedule_history(
                before,
                [_history_lesson(10, "2027-02-03")],
                **{**scope, "semester_start": "2027-02-01", "semester_end": "2027-07-15"},
            ),
            [],
        )


def _sqlite_statement(statement):
    """Translate named PostgreSQL conflict targets explicitly for this test DB."""
    conflict = getattr(statement, "_post_values_clause", None)
    target = getattr(conflict, "constraint_target", None)
    if target is None:
        return statement
    constraints = [
        constraint
        for constraint in statement.table.constraints
        if isinstance(constraint, UniqueConstraint) and constraint.name == target
    ]
    if len(constraints) != 1:
        raise AssertionError(f"Unknown or ambiguous test conflict target: {target}")
    translated = statement._generate()
    translated._post_values_clause = copy.copy(conflict)
    translated._post_values_clause.constraint_target = None
    translated._post_values_clause.inferred_target_elements = list(constraints[0].columns)
    return translated


class TestSQLiteConflictAdapter(unittest.TestCase):
    def test_named_targets_preserve_columns_and_original_postgresql_statement(self):
        statements = [
            pg_insert(CachedSchedule).on_conflict_do_update(
                constraint="uq_cached_schedule_entity", set_={"entity_name": "Updated"}
            ),
            pg_insert(ScheduleChangeDelivery).on_conflict_do_nothing(
                constraint="uq_schedule_change_delivery_event_user"
            ),
        ]
        for original in statements:
            with self.subTest(table=original.table.name):
                target = original._post_values_clause.constraint_target
                translated = _sqlite_statement(original)
                columns = translated._post_values_clause.inferred_target_elements
                sqlite_sql = str(translated.compile(dialect=sqlite_dialect()))
                self.assertIn(
                    "ON CONFLICT (" + ", ".join(column.name for column in columns) + ")",
                    sqlite_sql,
                )
                self.assertIn(
                    "ON CONFLICT ON CONSTRAINT " + target,
                    str(original.compile(dialect=pg_dialect())),
                )
                self.assertEqual(original._post_values_clause.constraint_target, target)
        with self.assertRaisesRegex(AssertionError, "Unknown or ambiguous"):
            _sqlite_statement(
                pg_insert(CachedSchedule).on_conflict_do_nothing(constraint="missing")
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
        delivery_metadata = MetaData()
        User.__table__.to_metadata(delivery_metadata)
        delivery_table = ScheduleChangeDelivery.__table__.to_metadata(delivery_metadata)
        delivery_table.c.id.type = Integer()
        delivery_table.create(self.engine)
        UserScheduleSubscription.__table__.create(self.engine)
        cache_table = CachedSchedule.__table__.to_metadata(MetaData())
        cache_table.c.schedule_data.type = JSON()
        cache_table.create(self.engine)
        ScheduleNotificationSnapshot.__table__.create(self.engine)
        ScheduleHistoryEntry.__table__.create(self.engine)
        with Session(self.engine) as session:
            session.add(User(user_id=10, full_name="Test"))
            session.add(
                UserScheduleSubscription(
                    id=1,
                    user_id=10,
                    chat_id=10,
                    entity_type="group",
                    entity_id="1",
                    entity_name="Test group",
                    notification_time=time(20),
                    is_active=True,
                )
            )
            session.commit()
        self.now = datetime(2026, 10, 9, 12, tzinfo=UTC)

        @asynccontextmanager
        async def sessions():
            with Session(self.engine) as session:

                class Adapter:
                    async def execute(self, statement, parameters=None):
                        if (
                            getattr(self_test, "fail_outbox", False)
                            and getattr(getattr(statement, "table", None), "name", None)
                            == "schedule_change_deliveries"
                        ):
                            raise RuntimeError("injected write failure")
                        return session.execute(_sqlite_statement(statement), parameters)

                    async def scalars(self, statement):
                        return session.scalars(statement)

                    async def scalar(self, statement):
                        return session.scalar(statement)

                    async def commit(self):
                        session.commit()

                    async def get(self, model, ident):
                        return session.get(model, ident)

                    async def flush(self):
                        session.flush()

                    async def refresh(self, obj):
                        session.refresh(obj)

                yield Adapter()

        self_test = self
        self.patcher = patch.object(schedule_outbox, "get_session", sessions)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.engine.dispose)
        self.sessions = sessions

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
                    updated_at=kwargs.pop("updated_at", self.now),
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

    async def test_permanent_delivery_cancel_clears_payload_without_recent_failure(self):
        self.insert(1, status="pending", attempt_count=0)
        claimed = await schedule_outbox.claim_schedule_change_deliveries(now_utc=self.now)
        self.assertEqual(claimed[0]["attempt_count"], 1)

        await schedule_outbox.cancel_schedule_change_delivery(
            1,
            expected_attempt_count=1,
            error="telegram_forbidden",
            now_utc=self.now,
        )

        self.assertEqual(self.rows()[1], ("cancelled", 1, "telegram_forbidden"))
        health = await schedule_outbox.get_schedule_outbox_health(self.now)
        self.assertEqual(health["oldest_pending_age_seconds"], 0)
        self.assertEqual(health["recently_failed"], 0)

    async def test_health_counts_oldest_pending_without_message_data(self):
        self.insert(1, status="pending", attempt_count=0)
        self.insert(2, status="failed", attempt_count=8)
        summary = await schedule_outbox.get_schedule_outbox_health(self.now)
        self.assertEqual(
            summary,
            {
                "pending": 1,
                "processing": 0,
                "failed": 1,
                "cancelled": 0,
                "oldest_pending_age_seconds": 3600,
                "recently_failed": 0,
                "recent_failure_window_seconds": 3600,
            },
        )

    async def test_delete_and_pause_cancel_pending_and_claimed_delivery(self):
        for mode in ("delete", "pause"):
            with self.subTest(mode=mode):
                self.insert(1 if mode == "delete" else 2, status="pending", attempt_count=0)
                if mode == "delete":
                    await schedule_outbox.claim_schedule_change_deliveries(now_utc=self.now)
                with patch.object(database, "get_session", self.sessions):
                    if mode == "delete":
                        self.assertEqual(
                            await database.remove_schedule_subscription(1, 10), "Test group"
                        )
                    else:
                        self.assertEqual(
                            await database.toggle_subscription_status(1, 10), (False, "Test group")
                        )
                self.assertEqual(self.rows()[1 if mode == "delete" else 2][0], "cancelled")
                if mode == "delete":
                    with Session(self.engine) as session:
                        session.add(
                            UserScheduleSubscription(
                                id=1,
                                user_id=10,
                                chat_id=10,
                                entity_type="group",
                                entity_id="1",
                                entity_name="Test group",
                                notification_time=time(20),
                                is_active=True,
                            )
                        )
                        session.commit()

    async def test_other_active_profile_at_same_destination_keeps_delivery(self):
        with Session(self.engine) as session:
            session.add(
                UserScheduleSubscription(
                    id=2,
                    user_id=10,
                    chat_id=10,
                    entity_type="group",
                    entity_id="1",
                    entity_name="Test group",
                    notification_time=time(21),
                    is_active=True,
                )
            )
            session.commit()
        self.insert(1, status="pending", attempt_count=0)
        with patch.object(database, "get_session", self.sessions):
            await database.remove_schedule_subscription(1, 10)
        claims = await schedule_outbox.claim_schedule_change_deliveries(now_utc=self.now)
        self.assertEqual(len(claims), 1)
        self.assertTrue(await schedule_outbox.is_schedule_delivery_current(1, 1))
        with patch.object(database, "get_session", self.sessions):
            await database.remove_schedule_subscription(2, 10)
        self.assertFalse(await schedule_outbox.is_schedule_delivery_current(1, 1))

    async def test_other_chat_does_not_authorize_private_delivery(self):
        with Session(self.engine) as session:
            session.get(UserScheduleSubscription, 1).chat_id = -42
            session.commit()
        self.insert(1, status="pending", attempt_count=0)
        self.assertEqual(
            await schedule_outbox.claim_schedule_change_deliveries(now_utc=self.now), []
        )
        self.assertEqual(self.rows()[1][0], "cancelled")

    async def test_expiry_is_reported_once_and_recent_health_then_recovers(self):
        self.insert(1, status="pending", attempt_count=0, expires_at=self.now)
        summary = {"failed": 0}
        self.assertEqual(
            await schedule_outbox.claim_schedule_change_deliveries(
                now_utc=self.now, summary=summary
            ),
            [],
        )
        self.assertEqual(summary["failed"], 1)
        health = await schedule_outbox.get_schedule_outbox_health(self.now)
        self.assertEqual(health["recently_failed"], 1)
        await schedule_outbox.claim_schedule_change_deliveries(now_utc=self.now, summary=summary)
        self.assertEqual(summary["failed"], 1)
        later = await schedule_outbox.get_schedule_outbox_health(self.now + timedelta(hours=2))
        self.assertEqual(later["recently_failed"], 0)
        self.assertEqual(later["failed"], 1)

    async def test_expiry_records_failed_drain_even_without_a_network_attempt(self):
        from scheduler_app import jobs

        self.insert(1, status="pending", attempt_count=0, expires_at=self.now)
        with (
            patch("scheduler_app.job_health.record_operation", AsyncMock()) as record,
            patch.object(jobs, "send_telegram_message", AsyncMock()) as send,
        ):
            result = await monitor_job(
                "outbox_delivery", jobs.deliver_pending_schedule_change_notifications
            )(None)
        self.assertEqual(result["failed"], 1)
        self.assertFalse(record.await_args.kwargs["successful"])
        send.assert_not_awaited()

    async def test_cancelled_claim_never_crosses_network_boundary(self):
        from scheduler_app import jobs

        self.insert(1, status="pending", attempt_count=0)
        original_claim = schedule_outbox.claim_schedule_change_deliveries

        async def claim_then_unsubscribe(**kwargs):
            rows = await original_claim(**kwargs)
            with patch.object(database, "get_session", self.sessions):
                await database.remove_schedule_subscription(1, 10)
            return rows

        with (
            patch.object(jobs, "claim_schedule_change_deliveries", claim_then_unsubscribe),
            patch.object(jobs, "send_telegram_message", AsyncMock()) as send,
        ):
            result = await jobs.deliver_pending_schedule_change_notifications(None)
        self.assertEqual(result["cancelled"], 1)
        send.assert_not_awaited()

    async def test_retention_preserves_live_rows_and_daily_dedupe_window(self):
        old = self.now - timedelta(days=40)
        self.insert(1, status="sent", attempt_count=1, updated_at=old)
        self.insert(2, status="failed", attempt_count=8, updated_at=old)
        self.insert(3, status="pending", attempt_count=1, updated_at=old)
        self.insert(4, status="processing", attempt_count=1, updated_at=old)
        self.insert(5, status="sent", attempt_count=1, delivery_kind="daily")
        self.assertEqual(
            await schedule_outbox.prune_schedule_delivery_history(
                now_utc=self.now, retention_days=0
            ),
            2,
        )
        self.assertEqual(set(self.rows()), {3, 4, 5})
        self.assertEqual(
            await schedule_outbox.get_existing_schedule_deliveries([("event-5", 10)]),
            {("event-5", 10)},
        )

    async def test_cache_refresh_cannot_consume_notification_baseline(self):
        from scheduler_app import jobs
        from shared_lib.services.schedule_service import diff_schedules

        old = [
            {
                "lessonOid": 1,
                "date": "2099-10-10",
                "discipline": "Math",
                "kindOfWork": "Lecture",
                "beginLesson": "09:00",
                "endLesson": "10:30",
                "auditorium": "A",
                "lecturer_title": "T",
            }
        ]
        new = [{**old[0], "auditorium": "B"}]
        await schedule_outbox.commit_schedule_change_transition(
            event_key="initial",
            entity_type="group",
            entity_id="1",
            entity_name="Test group",
            schedule_data=old,
            new_hash=schedule_outbox.schedule_snapshot_hash(old),
            deliveries=[],
        )
        # Execute the exact cache writer used by interactive and periodic refresh.
        with patch.object(database, "get_session", self.sessions):
            await database.upsert_cached_schedule("group", "1", new)
        with (
            patch.object(database, "get_session", self.sessions),
            patch.object(
                jobs, "get_unique_active_subscription_entities", AsyncMock(return_value=[])
            ),
            patch.object(jobs, "get_semester_bounds", return_value=("2099-09-01", "2100-01-31")),
            patch.dict(os.environ, {"PUBLIC_SITE_URL": "https://schedule.example"}),
            patch.object(jobs, "get_all_short_names", AsyncMock(return_value={})),
            patch.object(jobs.translator, "get_language", AsyncMock(return_value="en")),
            patch.object(jobs, "diff_schedules", diff_schedules),
            patch.object(
                jobs, "deliver_pending_schedule_change_notifications", AsyncMock(return_value={})
            ),
            patch.object(jobs.asyncio, "sleep", AsyncMock()),
        ):
            api = SimpleNamespace(
                get_schedule=AsyncMock(side_effect=lambda *args, **kwargs: copy.deepcopy(new))
            )
            self.assertEqual(await jobs.check_for_schedule_updates(None, api), {"failed": 0})
            self.assertEqual(await jobs.check_for_schedule_updates(None, api), {"failed": 0})
        with Session(self.engine) as session:
            rows = list(session.scalars(select(ScheduleChangeDelivery)))
            self.assertEqual(len(rows), 1)
            self.assertIn("A", rows[0].payload)
            self.assertIn("B", rows[0].payload)
            history = list(session.scalars(select(ScheduleHistoryEntry)))
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0].event_key, rows[0].event_key)
            self.assertEqual(history[0].before_lesson["room"], "A")
            self.assertEqual(history[0].after_lesson["room"], "B")
            href = unescape(rows[0].payload.split('href="', 1)[1].split('"', 1)[0])
            link = urlsplit(href)
            self.assertEqual((link.hostname, link.path), ("schedule.example", "/schedule"))
            params = parse_qs(link.query)
            self.assertEqual(params["change_event"], [rows[0].event_key])
            self.assertEqual(params["lesson"], ["1"])
            self.assertEqual(params["lesson_date"], ["2099-10-10"])
        snapshot = await schedule_outbox.get_schedule_notification_snapshot("group", "1")
        self.assertEqual(snapshot["revision"], 2)
        self.assertNotIn("date_obj", snapshot["schedule_data"][0])

    async def test_baseline_cas_and_outbox_write_are_atomic(self):
        kwargs = dict(
            event_key="event",
            entity_type="group",
            entity_id="1",
            entity_name="Test",
            schedule_data=[],
            new_hash="a" * 64,
            deliveries=[],
        )
        await schedule_outbox.commit_schedule_change_transition(**kwargs)
        history = [{"kind": "added", "before": None, "after": {"date": "2099-10-10"}, "fields": []}]
        self.fail_outbox = True
        with self.assertRaisesRegex(RuntimeError, "injected"):
            await schedule_outbox.commit_schedule_change_transition(
                **{**kwargs, "deliveries": [{"user_id": 10, "chat_id": 10, "payload": "Changed"}]},
                expected_revision=1,
                history=history,
            )
        self.fail_outbox = False
        self.assertEqual(
            (await schedule_outbox.get_schedule_notification_snapshot("group", "1"))["revision"], 1
        )
        self.assertEqual(self.rows(), {})
        with Session(self.engine) as session:
            self.assertEqual(list(session.scalars(select(ScheduleHistoryEntry))), [])
        await schedule_outbox.commit_schedule_change_transition(
            **kwargs, expected_revision=1, history=history
        )
        with self.assertRaises(schedule_outbox.ScheduleBaselineConflict):
            await schedule_outbox.commit_schedule_change_transition(
                **kwargs, expected_revision=1, history=history
            )
        self.assertEqual(
            (await schedule_outbox.get_schedule_notification_snapshot("group", "1"))["revision"], 2
        )
        with patch.object(schedule_history, "get_session", self.sessions):
            self.assertEqual(
                len((await schedule_history.read_schedule_history("group", "1", "event"))["items"]),
                1,
            )
            self.assertEqual(
                (await schedule_history.read_schedule_history("group", "2", "event"))["items"], []
            )

    async def test_slow_source_cannot_reverse_a_concurrent_scanner_transition(self):
        from scheduler_app import jobs
        from shared_lib.services.schedule_service import diff_schedules

        lesson = {
            "lessonOid": 1,
            "date": "2099-10-10",
            "discipline": "Math",
            "kindOfWork": "Lecture",
            "beginLesson": "09:00",
            "endLesson": "10:30",
            "auditorium": "A",
            "lecturer_title": "T",
        }

        async def advance(data, revision):
            await schedule_outbox.commit_schedule_change_transition(
                event_key="concurrent-source",
                entity_type="group",
                entity_id="1",
                entity_name="Test group",
                schedule_data=data,
                new_hash=schedule_outbox.schedule_snapshot_hash(data),
                deliveries=[],
                expected_revision=revision,
            )

        await advance([lesson], None)
        winner = [{**lesson, "auditorium": "C"}]

        async def delayed_source(*args, **kwargs):
            # A second scanner commits while this scanner awaits its older reply.
            await advance(winner, 1)
            return [{**lesson, "auditorium": "B"}]

        with (
            patch.object(database, "get_session", self.sessions),
            patch.object(
                jobs, "get_unique_active_subscription_entities", AsyncMock(return_value=[])
            ),
            patch.object(jobs, "get_all_short_names", AsyncMock(return_value={})),
            patch.object(jobs.translator, "get_language", AsyncMock(return_value="en")),
            patch.object(jobs, "diff_schedules", diff_schedules),
            patch.object(
                jobs, "deliver_pending_schedule_change_notifications", AsyncMock(return_value={})
            ),
            patch.object(jobs.asyncio, "sleep", AsyncMock()),
        ):
            result = await jobs.check_for_schedule_updates(
                None, SimpleNamespace(get_schedule=delayed_source)
            )
        self.assertEqual(result, {"failed": 1})
        baseline = await schedule_outbox.get_schedule_notification_snapshot("group", "1")
        self.assertEqual(baseline["revision"], 2)
        self.assertEqual(baseline["schedule_data"], winner)
        self.assertEqual(self.rows(), {})

    async def test_web_only_source_records_history_without_enqueuing_telegram(self):
        from scheduler_app import jobs

        entity = {"entity_type": "group", "entity_id": "12", "entity_name": "Test"}
        original = _history_lesson(1, "2099-10-10")
        await schedule_outbox.commit_schedule_change_transition(
            event_key="baseline",
            **entity,
            schedule_data=[original],
            new_hash=schedule_outbox.schedule_snapshot_hash([original]),
            deliveries=[],
        )
        with (
            patch.object(jobs, "get_all_active_subscriptions", AsyncMock(return_value=[])),
            patch.object(
                jobs, "get_unique_active_subscription_entities", AsyncMock(return_value=[entity])
            ),
            patch.object(jobs, "get_semester_bounds", return_value=("2099-09-01", "2100-01-31")),
            patch.object(
                jobs, "deliver_pending_schedule_change_notifications", AsyncMock(return_value={})
            ),
            patch.object(jobs.asyncio, "sleep", AsyncMock()),
            patch.object(schedule_history, "get_session", self.sessions),
        ):
            api = SimpleNamespace(get_schedule=AsyncMock(return_value=[]))
            self.assertEqual(await jobs.check_for_schedule_updates(None, api), {"failed": 0})
            items = (await schedule_history.read_schedule_history("group", "12"))["items"]
        self.assertEqual([item["kind"] for item in items], ["cancelled"])
        self.assertFalse(self.rows())

    async def test_migration_backfill_and_downgrade(self):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        migration_path = (
            Path(__file__).parents[1]
            / "alembic/versions/fe4e5f607182_schedule_notification_baseline.py"
        )
        spec = importlib.util.spec_from_file_location("delivery_migration", migration_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with self.engine.begin() as connection:
            ScheduleNotificationSnapshot.__table__.drop(connection)
            connection.exec_driver_sql("DROP INDEX ix_schedule_change_deliveries_failed_at")
            connection.exec_driver_sql(
                "ALTER TABLE schedule_change_deliveries DROP COLUMN failed_at"
            )
            connection.execute(
                CachedSchedule.__table__.insert().values(
                    entity_type="group",
                    entity_id="1",
                    entity_name="Test",
                    schedule_data=[{"date_obj": "ignored", "discipline": "Math"}],
                    updated_at=None,
                )
            )
            with patch.object(migration, "op", Operations(MigrationContext.configure(connection))):
                migration.upgrade()
                row = connection.execute(select(ScheduleNotificationSnapshot)).mappings().one()
                self.assertEqual(row["schedule_data"], [{"discipline": "Math"}])
                self.assertIsNotNone(row["updated_at"])
                self.assertEqual(
                    row["schedule_hash"],
                    schedule_outbox.schedule_snapshot_hash(row["schedule_data"]),
                )
                migration.downgrade()
                from sqlalchemy import inspect

                self.assertNotIn(
                    "schedule_notification_snapshots", inspect(connection).get_table_names()
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

        with (
            patch.object(main, "get_session", database),
            patch.object(main.redis_client.client, "llen", AsyncMock(return_value=0)),
            patch.object(
                main,
                "get_operational_snapshot",
                AsyncMock(return_value={"available": True, "operations": []}),
            ),
            patch.object(
                main,
                "get_schedule_outbox_health",
                AsyncMock(return_value={"oldest_pending_age_seconds": 0, "recently_failed": 1}),
            ),
        ):
            _, code = await main.build_scheduler_health(True)
            self.assertEqual(code, 503)

        with (
            patch.object(main, "get_session", database),
            patch.object(main.redis_client.client, "llen", AsyncMock(return_value=0)),
            patch.object(
                main,
                "get_operational_snapshot",
                AsyncMock(return_value={"available": True, "operations": []}),
            ),
            patch.object(
                main,
                "get_schedule_outbox_health",
                AsyncMock(
                    return_value={
                        "pending": 0,
                        "processing": 0,
                        "failed": 0,
                        "cancelled": 1,
                        "oldest_pending_age_seconds": 0,
                        "recently_failed": 0,
                    }
                ),
            ),
        ):
            _, code = await main.build_scheduler_health(True)
            self.assertEqual(code, 200)
