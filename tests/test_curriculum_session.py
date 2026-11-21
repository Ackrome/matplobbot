"""Regression tests for local Session dates and their bounded background refresh."""

import runpy
import unittest
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from alembic.migration import MigrationContext
from alembic.operations import Operations
from shared_lib.models import CurriculumDocument, CurriculumGroup, CurriculumSessionSnapshot
from shared_lib.services import curriculum_session as dates
from shared_lib.services.curriculum_service import (
    CurriculumConflictError,
    match_session_dates,
    read_curriculum_session,
    session_date_reviews,
)
from shared_lib.services.university_api import RuzAPIError
from tests.test_curriculum_service import _AsyncSession

NOW = datetime(2026, 11, 21, 9, tzinfo=UTC)
TERM = {"semester": 5, "start_date": "2026-09-01", "end_date": "2027-01-25"}
SPRING = {"semester": 6, "start_date": "2027-02-02", "end_date": "2027-06-28"}
GROUP = "164377"
PLAN_ROW = {
    "discipline_code": "Б.1.01",
    "discipline_name": "Методы оптимизации",
    "kind": "exam",
    "source_document_id": 1,
    "source_sha256": "a" * 64,
}
RUZ_ROW = {
    "discipline": "Методы оптимизации",
    "kindOfWork": "Экзамен",
    "date": "2026-12-15",
    "beginLesson": "10:10",
    "auditorium": "303",
    "lessonOid": 456,
}


class TestCurriculumSessionDates(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        for model in CurriculumDocument, CurriculumGroup, CurriculumSessionSnapshot:
            model.__table__.create(self.engine)

        @asynccontextmanager
        async def sessions():
            with Session(self.engine, expire_on_commit=False) as db:
                yield _AsyncSession(db)

        self.enterContext(patch.object(dates, "get_session", sessions))
        self.canonical = self.enterContext(
            patch.object(
                dates,
                "get_cached_schedule_with_coverage",
                AsyncMock(return_value=(None, None, None)),
            )
        )
        self.ruz = self.enterContext(patch.object(dates, "create_ruz_api_client")).return_value
        self.ruz.get_schedule = AsyncMock()

    def add_group(self, group_id=GROUP, *, term=TERM, published=True):
        with Session(self.engine) as db:
            db.add(
                CurriculumDocument(
                    id=int(group_id),
                    title="Plan",
                    source_url="https://fa.ru/upload/plan.pdf",
                    program="Math",
                    profile="ML",
                    campus="Moscow",
                    admission_year=2024,
                    study_form="Full-time",
                    published_hash=("a" * 64 if published else None),
                )
            )
            db.add(
                CurriculumGroup(
                    group_id=group_id, document_id=int(group_id), group_name="ПМ24-1", terms=[term]
                )
            )
            db.commit()

    async def test_scheduler_preserves_last_success_on_failure_and_excludes_other_terms(self):
        self.add_group()
        self.add_group("164378", term=SPRING)
        self.add_group("164379", published=False)
        self.ruz.get_schedule.return_value = [
            {**RUZ_ROW, "lecturerEmail": "private@invalid"},
            {**RUZ_ROW, "kindOfWork": "Консультация перед экзаменом"},
        ]
        self.assertEqual(
            await dates.refresh_session_dates(object(), now=NOW), {"refreshed": 1, "failed": 0}
        )
        self.ruz.get_schedule.assert_awaited_once_with(
            "group", GROUP, TERM["start_date"], TERM["end_date"]
        )
        self.canonical.assert_not_awaited()
        key = dates._term_key(GROUP, TERM)
        with Session(self.engine) as db:
            self.assertEqual(db.get(CurriculumSessionSnapshot, key).lessons, [RUZ_ROW])

        later = NOW + timedelta(hours=7)
        self.ruz.get_schedule.side_effect = RuzAPIError("network unavailable")
        self.assertEqual(
            await dates.refresh_session_dates(object(), now=later), {"refreshed": 0, "failed": 1}
        )
        with Session(self.engine) as db:
            snapshot = db.get(CurriculumSessionSnapshot, key)
            self.assertEqual(dates._utc(snapshot.attempted_at), later)
            self.assertEqual(dates._utc(snapshot.checked_at), NOW)
            self.assertEqual(snapshot.last_error, "upstream_unavailable")
        calls = self.ruz.get_schedule.await_count
        result = await dates.cached_session_dates(GROUP, TERM, [PLAN_ROW], now=later)
        self.assertEqual(result["dates_status"], "stale")
        self.assertEqual(result["dates_checked_at"], NOW.isoformat())
        self.assertEqual([event["lesson_id"] for event in result["events"]], ["456"])
        spring = await dates.cached_session_dates(GROUP, SPRING, [PLAN_ROW], now=later)
        self.assertEqual(
            (spring["dates_status"], spring["events"], spring["dates_coverage"]),
            ("unavailable", [], []),
        )
        self.assertEqual(self.ruz.get_schedule.await_count, calls)

    async def test_invalid_source_payload_cannot_clear_verified_dates(self):
        self.add_group()
        self.ruz.get_schedule.return_value = [RUZ_ROW]
        await dates.refresh_session_dates(object(), now=NOW)
        for offset, payload in enumerate(
            ([{}], [{**RUZ_ROW, "date": "2027-02-20"}], [{**RUZ_ROW, "date": "2026-12-32"}]),
            start=7,
        ):
            with self.subTest(payload=payload):
                self.ruz.get_schedule.return_value = payload
                later = NOW + timedelta(hours=offset)
                self.assertEqual(
                    await dates.refresh_session_dates(object(), now=later),
                    {"refreshed": 0, "failed": 1},
                )
                result = await dates.cached_session_dates(GROUP, TERM, [PLAN_ROW], now=later)
                self.assertEqual(result["dates_checked_at"], NOW.isoformat())
                self.assertEqual([event["lesson_id"] for event in result["events"]], ["456"])
                coverage = await dates.admin_session_coverage(now=later)
                self.assertEqual(
                    coverage["groups"][0]["terms"][0]["last_error"], "invalid_response"
                )

    async def test_admin_coverage_distinguishes_failed_verification_from_old_evidence(self):
        self.add_group()
        self.add_group("164378", term={**SPRING, "start_date": "2027-01-03"})
        self.add_group("164379", published=False)
        self.add_group("164380", term={**TERM, "end_date": "2026-11-20"})
        initial = await dates.admin_session_coverage(now=NOW)
        self.assertEqual([group["group_id"] for group in initial["groups"]], [GROUP, "164378"])
        self.assertEqual(initial["groups"][0]["terms"][0]["dates_status"], "pending")
        self.ruz.get_schedule.side_effect = [[RUZ_ROW], RuzAPIError("private upstream body")]
        await dates.refresh_session_dates(object(), now=NOW)
        later = NOW + timedelta(hours=7)
        self.ruz.get_schedule.side_effect = RuzAPIError("private upstream body")
        await dates.refresh_session_dates(object(), now=later)
        coverage = await dates.admin_session_coverage(now=later)
        stale, pending = (group["terms"][0] for group in coverage["groups"])
        self.assertEqual(stale["dates_status"], "stale")
        self.assertEqual(stale["dates_checked_at"], NOW.isoformat())
        self.assertEqual(stale["last_attempted_at"], later.isoformat())
        self.assertEqual(stale["dates_coverage"][0]["end_date"], TERM["end_date"])
        self.assertEqual(stale["last_error"], "upstream_unavailable")
        self.assertEqual(pending["dates_status"], "pending")
        self.assertEqual(pending["dates_coverage"], [])
        self.assertNotIn("private upstream body", repr(coverage))
        self.ruz.get_schedule.side_effect = None
        self.ruz.get_schedule.return_value = []
        retry = later + timedelta(hours=1)
        await dates.refresh_session_dates(object(), now=retry)
        coverage = await dates.admin_session_coverage(now=retry)
        for group in coverage["groups"]:
            verified = group["terms"][0]
            self.assertEqual(verified["dates_status"], "checked")
            self.assertIsNone(verified["last_error"])
        self.canonical.assert_not_awaited()

    async def test_partial_bootstrap_then_authoritative_full_snapshot_survives_rollover(self):
        self.add_group()
        self.canonical.return_value = ([RUZ_ROW], NOW, ("2026-12-01", "2026-12-22"))
        partial = await dates.cached_session_dates(GROUP, TERM, [PLAN_ROW], now=NOW)
        self.assertEqual(partial["dates_status"], "partial")
        self.assertEqual([event["lesson_id"] for event in partial["events"]], ["456"])
        self.assertEqual(
            partial["dates_coverage"],
            [
                {
                    "start_date": "2026-12-01",
                    "end_date": "2026-12-22",
                    "checked_at": NOW.isoformat(),
                }
            ],
        )

        self.ruz.get_schedule.return_value = [
            RUZ_ROW,
            {**RUZ_ROW, "date": "2027-01-15", "lessonOid": 987},
        ]
        await dates.refresh_session_dates(object(), now=NOW)
        later = NOW + timedelta(hours=7)
        self.canonical.return_value = ([], later, ("2026-12-01", "2026-12-22"))
        latest = await dates.cached_session_dates(GROUP, TERM, [PLAN_ROW], now=later)
        self.assertEqual(latest["dates_status"], "stale")
        self.assertEqual(latest["dates_checked_at"], NOW.isoformat())
        self.assertEqual([event["lesson_id"] for event in latest["events"]], ["456", "987"])
        self.ruz.get_schedule.return_value = []
        await dates.refresh_session_dates(object(), now=later)
        self.canonical.return_value = ([RUZ_ROW], later, ("2026-12-01", "2026-12-22"))
        latest = await dates.cached_session_dates(GROUP, TERM, [PLAN_ROW], now=later)
        self.assertEqual(latest["dates_status"], "checked")
        self.assertEqual(latest["dates_checked_at"], later.isoformat())
        self.assertEqual(latest["events"], [])
        self.assertEqual(
            latest["dates_coverage"],
            [
                {
                    "start_date": TERM["start_date"],
                    "end_date": TERM["end_date"],
                    "checked_at": later.isoformat(),
                }
            ],
        )
        self.canonical.assert_awaited_once()

    async def test_request_cap_and_failed_attempt_cooldown_allow_other_groups(self):
        for group in range(164377, 164386):
            self.add_group(str(group))
        self.ruz.get_schedule.side_effect = RuzAPIError("network unavailable")
        self.assertEqual((await dates.refresh_session_dates(object(), now=NOW))["failed"], 8)
        self.assertEqual(self.ruz.get_schedule.await_count, 8)
        later = NOW + timedelta(minutes=15)
        self.assertEqual((await dates.refresh_session_dates(object(), now=later))["failed"], 1)
        self.ruz.get_schedule.assert_awaited_with(
            "group", "164385", TERM["start_date"], TERM["end_date"]
        )
        self.assertEqual((await dates.refresh_session_dates(object(), now=later))["failed"], 0)

    def test_compound_credit_requires_one_reviewed_form_and_valid_timetable_data(self):
        raw = {**RUZ_ROW, "kindOfWork": "Семинар + зачёт"}
        graded = {**PLAN_ROW, "kind": "graded_pass"}
        plain = {**PLAN_ROW, "kind": "pass"}
        bounds = TERM["start_date"], TERM["end_date"]
        self.assertEqual(
            [r["kind"] for r in match_session_dates([graded], [raw], *bounds)], ["graded_pass"]
        )
        self.assertEqual(
            [r["kind"] for r in match_session_dates([plain], [raw], *bounds)], ["pass"]
        )
        self.assertFalse(match_session_dates([graded, plain], [raw], *bounds))
        self.assertFalse(match_session_dates([PLAN_ROW], [raw], *bounds))
        self.assertFalse(match_session_dates([graded], [{**raw, "date": "2026-12-32"}], *bounds))
        self.assertFalse(match_session_dates([graded], [{**raw, "deletion_mark": "True"}], *bounds))
        duplicates = match_session_dates([graded], [raw, {**raw, "lessonOid": 789}], *bounds)
        self.assertIsNone(duplicates[0]["lesson_id"])

    async def test_confirm_ambiguous_date_is_scoped_to_current_event_and_publication(self):
        self.add_group()
        self.add_group("164378")
        raw = {**RUZ_ROW, "kindOfWork": "Семинар + зачёт"}
        root = int(GROUP)
        row = {
            "discipline_code": PLAN_ROW["discipline_code"],
            "discipline_name": PLAN_ROW["discipline_name"],
            "page": 1,
            "semester": TERM["semester"],
        }
        published = [{**row, "kind": "pass"}, {**row, "kind": "graded_pass"}]
        with Session(self.engine) as db:
            db.get(CurriculumDocument, root).published_assessments = published
            db.commit()
        self.ruz.get_schedule.return_value = [raw]
        await dates.refresh_session_dates(object(), now=NOW)
        review = (await dates.admin_session_reviews(GROUP, TERM["semester"]))["reviews"][0]
        self.assertEqual(review["event"]["lesson_id"], "456")
        self.assertEqual(review["event"]["assessment_label"], "Семинар + зачёт")
        self.assertCountEqual(
            [row["kind"] for row in review["candidates"]], ["pass", "graded_pass"]
        )
        self.assertTrue(
            all(row["snapshot_url"].endswith("a" * 64 + ".pdf") for row in review["candidates"])
        )
        self.assertIsNone(review["selected"])

        async def public_events():
            async with dates.get_session() as db:
                plan = await read_curriculum_session(db, GROUP, NOW.date(), TERM["semester"])
            return (await dates.cached_session_dates(GROUP, TERM, plan["assessments"], now=NOW))[
                "events"
            ]

        self.assertEqual(await public_events(), [])
        first, second = [row["candidate_key"] for row in review["candidates"]]
        event_key, review_key = review["event_key"], review["review_key"]
        with self.assertRaises(CurriculumConflictError):
            await dates.confirm_session_review(
                GROUP, {**TERM, "start_date": "2026-09-02"}, event_key, review_key, first, None
            )
        await dates.confirm_session_review(GROUP, TERM, event_key, review_key, first, None)
        await dates.confirm_session_review(GROUP, TERM, event_key, review_key, first, None)
        with self.assertRaises(CurriculumConflictError):
            await dates.confirm_session_review(GROUP, TERM, event_key, review_key, second, None)
        self.assertEqual(
            (await dates.admin_session_reviews(GROUP, TERM["semester"]))["reviews"][0]["selected"],
            first,
        )
        self.assertEqual([row["kind"] for row in await public_events()], [published[0]["kind"]])
        with Session(self.engine) as db:
            document = db.get(CurriculumDocument, root)
            self.assertEqual(document.published_assessments, published)
            self.assertEqual(
                db.get(CurriculumSessionSnapshot, dates._term_key("164378", TERM)).date_resolutions,
                {},
            )
            document.published_hash = "b" * 64
            db.commit()
        self.assertEqual(await public_events(), [])
        with self.assertRaises(CurriculumConflictError):
            await dates.confirm_session_review(GROUP, TERM, event_key, review_key, first, None)
        with Session(self.engine) as db:
            db.get(CurriculumDocument, root).published_assessments = published[1:]
            db.commit()
        self.assertEqual([row["kind"] for row in await public_events()], ["graded_pass"])

    def test_resolved_events_in_same_slot_are_kept_for_distinct_published_rows(self):
        row = {**PLAN_ROW, "source_title": "Основной план", "snapshot_url": "", "page": 1}
        second = {**row, "discipline_code": "Б.1.02", "source_document_id": 2}
        schedule = [RUZ_ROW, {**RUZ_ROW, "lessonOid": 789}]
        bounds = TERM["start_date"], TERM["end_date"]
        reviews = session_date_reviews([row, second], schedule, *bounds, GROUP, {})
        resolutions = {
            review["event_key"]: {
                "review_key": review["review_key"],
                "candidate_key": review["candidates"][index]["candidate_key"],
            }
            for index, review in enumerate(reviews)
        }
        resolved = match_session_dates(
            [row, second], schedule, *bounds, group_id=GROUP, resolutions=resolutions
        )
        self.assertCountEqual([item["discipline_code"] for item in resolved], ["Б.1.01", "Б.1.02"])
        self.assertCountEqual([item["lesson_id"] for item in resolved], ["456", "789"])

    def test_migration_upgrade_and_downgrade(self):
        module = runpy.run_path(
            str(
                Path(__file__).parents[1]
                / "alembic/versions/ea1400010003_curriculum_session_snapshots.py"
            )
        )
        table = CurriculumSessionSnapshot.__tablename__
        errors = runpy.run_path(
            str(
                Path(__file__).parents[1]
                / "alembic/versions/ea1400010005_curriculum_session_errors.py"
            )
        )
        reviews = runpy.run_path(
            str(
                Path(__file__).parents[1]
                / "alembic/versions/ea1400010006_curriculum_session_reviews.py"
            )
        )
        CurriculumSessionSnapshot.__table__.drop(self.engine)
        with (
            self.engine.begin() as connection,
            Operations.context(MigrationContext.configure(connection)),
        ):
            module["upgrade"]()
            self.assertTrue(inspect(connection).has_table(table))
            self.assertNotIn(
                "last_error", {column["name"] for column in inspect(connection).get_columns(table)}
            )
            errors["upgrade"]()
            self.assertIn(
                "last_error", {column["name"] for column in inspect(connection).get_columns(table)}
            )
            reviews["upgrade"]()
            self.assertIn(
                "date_resolutions",
                {column["name"] for column in inspect(connection).get_columns(table)},
            )
            reviews["downgrade"]()
            self.assertNotIn(
                "date_resolutions",
                {column["name"] for column in inspect(connection).get_columns(table)},
            )
            errors["downgrade"]()
            self.assertNotIn(
                "last_error", {column["name"] for column in inspect(connection).get_columns(table)}
            )
            module["downgrade"]()
            self.assertFalse(inspect(connection).has_table(table))
