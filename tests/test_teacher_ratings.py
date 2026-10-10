"""Real cache/migration persistence and bounded HTML-to-public-API contracts."""

import asyncio
import importlib.util
import time
import unittest
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi_stats_app.routers import teacher_ratings_router as router
from shared_lib.models import TeacherRatingCache
from shared_lib.services import teacher_rating_source as source
from shared_lib.services import teacher_ratings as ratings
from tests.test_teacher_rating_source import (
    NAME,
    OTHER_PROFILE,
    PROFILE,
    card,
    catalogue,
    structured,
    teacher,
)


class AsyncSessionBridge:
    """Execute the actual generic SQL on SQLite without mocking DB results."""

    def __init__(self, session):
        self.session = session

    def add(self, value):
        self.session.add(value)

    async def execute(self, *args, **kwargs):
        return self.session.execute(*args, **kwargs)

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()


class HtmlResponse:
    def __init__(self, body="", *, status=200, headers=None, delay=0, failure=None):
        self.body = body.encode() if isinstance(body, str) else body
        self.status = status
        self.headers = {"Content-Type": "text/html; charset=utf-8", **(headers or {})}
        self.content_length = len(self.body)
        self.content = self
        self.delay = delay
        self.failure = failure
        self.owner = None

    async def __aenter__(self):
        if self.failure:
            raise self.failure
        self.owner.active += 1
        self.owner.max_active = max(self.owner.max_active, self.owner.active)
        return self

    async def __aexit__(self, *_args):
        self.owner.active -= 1

    async def iter_chunked(self, size):
        if self.delay:
            await asyncio.sleep(self.delay)
        for index in range(0, len(self.body), size):
            yield self.body[index : index + size]


class HtmlSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.starts = []
        self.active = self.max_active = 0

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        self.starts.append(time.monotonic())
        response = self.responses.pop(0)
        response.owner = self
        return response


class TeacherCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        TeacherRatingCache.__table__.create(self.engine)
        self.instances = []
        self.interval = patch.object(ratings, "HTTP_START_INTERVAL_SECONDS", 0)
        self.interval.start()

    async def asyncTearDown(self):
        for service in self.instances:
            await service.close()
        self.interval.stop()
        self.engine.dispose()

    @asynccontextmanager
    async def sessions(self):
        with Session(self.engine, expire_on_commit=False) as session:
            yield AsyncSessionBridge(session)

    def service(self, http=None):
        instance = ratings.TeacherRatingsService(
            http or HtmlSession(), session_factory=self.sessions
        )
        self.instances.append(instance)
        return instance

    def row(self):
        with Session(self.engine) as session:
            row = session.scalars(select(TeacherRatingCache)).one()
            return {column.name: getattr(row, column.name) for column in row.__table__.columns}

    def expire(self):
        with Session(self.engine) as session:
            session.execute(
                update(TeacherRatingCache).values(
                    checked_at=datetime.now(UTC) - timedelta(hours=25),
                    next_check_at=datetime.now(UTC) - timedelta(seconds=1),
                )
            )
            session.commit()

    def matching_http(self, **profile_changes):
        return HtmlSession(
            HtmlResponse(catalogue()), HtmlResponse(structured(teacher(**profile_changes)))
        )

    async def test_real_html_match_persists_and_survives_service_restart(self):
        first = self.service(self.matching_http())
        with patch.object(ratings, "get_global_http_proxy_url", return_value="http://proxy:8080"):
            result = await first.get(NAME)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["profile"]["url"], PROFILE)
        self.assertEqual(result["profile"]["rating_percent"], 5)
        self.assertFalse(result["stale"])
        self.assertEqual(len(first.http_session.calls), 2)
        for _, options in first.http_session.calls:
            self.assertFalse(options["allow_redirects"])
            self.assertFalse(options["auto_decompress"])
            self.assertEqual(options["proxy"], "http://proxy:8080")
        stored = self.row()
        self.assertEqual(stored["university_key"], "fa")
        self.assertEqual(stored["provenance"]["profile_url"], PROFILE)
        self.assertEqual(stored["provenance"]["identity_method"], "exact_full_name_and_university")
        self.assertIsNone(stored["refresh_token"])
        self.assertNotIn("review_text", stored["profile"])
        second = self.service()
        cached = await second.get(" чупреева_алена николаевна ")
        self.assertEqual(cached["profile"], result["profile"])
        self.assertEqual(cached["query_name"], "чупреева алена николаевна")
        self.assertEqual(second.http_session.calls, [])
        self.assertEqual(
            ratings.teacher_identity(NAME), ratings.teacher_identity(cached["query_name"])
        )

    async def test_initials_and_compound_names_have_no_db_or_network_side_effect(self):
        service = self.service()
        for name in ("Чупреева А. Н.", NAME + "; " + NAME, "Иванов Иван", "https://evil.test"):
            self.assertEqual((await service.get(name))["status"], "unsupported")
        with Session(self.engine) as session:
            self.assertEqual(session.scalars(select(TeacherRatingCache)).all(), [])
        self.assertFalse(service.http_session.calls)

    async def test_valid_negative_result_is_cached_for_a_day(self):
        service = self.service(HtmlSession(HtmlResponse(catalogue([]))))
        result = await service.get(NAME)
        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(result["profile"])
        self.assertIsNotNone(result["checked_at"])
        second = self.service()
        self.assertEqual((await second.get(NAME))["status"], "not_found")
        self.assertFalse(second.http_session.calls)
        row = self.row()
        self.assertAlmostEqual(
            (row["next_check_at"] - row["checked_at"]).total_seconds(), 24 * 3600, delta=1
        )

    async def test_zero_votes_and_absent_statistics_remain_null(self):
        service = self.service(self.matching_http(aggregateRating=None))
        result = await service.get(NAME)
        for field in ("rating_percent", "vote_count", "review_count"):
            self.assertIsNone(result["profile"][field])
        self.expire()
        entity = teacher()
        entity["aggregateRating"]["ratingCount"] = 0
        service.http_session = HtmlSession(
            HtmlResponse(catalogue()), HtmlResponse(structured(entity))
        )
        await service.get(NAME)
        await asyncio.gather(*list(service._tasks.values()))
        result = await service.get(NAME)
        self.assertEqual(result["profile"]["vote_count"], 0)
        self.assertIsNone(result["profile"]["rating_percent"])

    async def test_stale_response_returns_before_failed_refresh_preserves_snapshot(self):
        service = self.service(self.matching_http())
        original = await service.get(NAME)
        self.expire()
        checked = self.row()["checked_at"]
        started, release = asyncio.Event(), asyncio.Event()

        async def failed(_name):
            started.set()
            await release.wait()
            raise ratings.TeacherSourceUnavailable("offline")

        service._lookup_live = AsyncMock(side_effect=failed)
        stale = await service.get(NAME)
        self.assertTrue(stale["stale"])
        self.assertEqual(stale["profile"], original["profile"])
        await started.wait()
        self.assertFalse(release.is_set())
        release.set()
        await asyncio.gather(*list(service._tasks.values()))
        row = self.row()
        self.assertEqual(row["checked_at"], checked)
        self.assertEqual(row["status"], "matched")
        second = self.service()
        self.assertTrue((await second.get(NAME))["stale"])
        self.assertFalse(second.http_session.calls)

    async def test_initial_failure_has_durable_backoff_and_no_fabricated_check_time(self):
        service = self.service(HtmlSession(HtmlResponse(status=503), HtmlResponse(status=503)))
        result = await service.get(NAME)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["checked_at"])
        self.assertIsNone(result["profile"])
        self.assertEqual(len(service.http_session.calls), 2)
        second = self.service()
        self.assertEqual((await second.get(NAME))["status"], "unavailable")
        self.assertFalse(second.http_session.calls)
        self.assertGreater(self.row()["next_check_at"], datetime.now(UTC).replace(tzinfo=None))

    async def test_local_concurrent_first_requests_share_one_refresh(self):
        service = self.service()
        started, release = asyncio.Event(), asyncio.Event()

        async def lookup(_name):
            started.set()
            await release.wait()
            return "not_found", None, {"university_key": "fa"}

        service._lookup_live = AsyncMock(side_effect=lookup)
        requests = [asyncio.create_task(service.get(NAME)) for _ in range(8)]
        await started.wait()
        release.set()
        results = await asyncio.gather(*requests)
        self.assertTrue(all(result["status"] == "not_found" for result in results))
        self.assertEqual(service._lookup_live.await_count, 1)

    async def test_db_lease_coalesces_instances_and_expired_writer_cannot_overwrite(self):
        first, second = self.service(), self.service()
        key, canonical = ratings.teacher_identity(NAME)
        token1 = await first._claim(key, canonical)
        self.assertIsNone(await second._claim(key, canonical))
        with Session(self.engine) as session:
            session.execute(
                update(TeacherRatingCache).values(
                    refresh_started_at=datetime.now(UTC)
                    - ratings.REFRESH_LEASE
                    - timedelta(seconds=1)
                )
            )
            session.commit()
        token2 = await second._claim(key, canonical)
        self.assertNotEqual(token1, token2)
        self.assertFalse(await first._publish(key, token1, "not_found", None, {}))
        self.assertTrue(
            await second._publish(key, token2, "ambiguous", None, {"source": "myprepod"})
        )
        self.assertEqual(self.row()["status"], "ambiguous")

    async def test_request_cancellation_does_not_cancel_shared_cache_refresh(self):
        service = self.service()
        started, release = asyncio.Event(), asyncio.Event()

        async def lookup(_name):
            started.set()
            await release.wait()
            return "not_found", None, {}

        service._lookup_live = lookup
        request = asyncio.create_task(service.get(NAME))
        await started.wait()
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)
        tasks = list(service._tasks.values())
        self.assertEqual(len(tasks), 1)
        self.assertFalse(tasks[0].cancelled())
        release.set()
        await asyncio.gather(*tasks)
        self.assertEqual((await service.get(NAME))["status"], "not_found")

    async def test_refresh_capacity_bounds_tasks_and_new_cache_rows(self):
        service = self.service()
        release = asyncio.Event()
        started = asyncio.Event()
        count = 0

        async def lookup(_name):
            nonlocal count
            count += 1
            if count == 2:
                started.set()
            await release.wait()
            return "not_found", None, {}

        service._lookup_live = lookup
        with patch.object(ratings, "MAX_REFRESH_TASKS", 2):
            requests = [
                asyncio.create_task(service.get(name)) for name in (NAME, "Иванов Иван Иванович")
            ]
            await started.wait()
            self.assertEqual((await service.get("Петров Петр Петрович"))["status"], "unavailable")
            self.assertEqual(len(service._tasks), 2)
            with Session(self.engine) as session:
                self.assertEqual(len(session.scalars(select(TeacherRatingCache)).all()), 2)
            release.set()
            await asyncio.gather(*requests)

    async def test_slow_source_timeout_releases_lease_and_sets_backoff(self):
        service = self.service()

        async def slow(_name):
            await asyncio.Event().wait()

        service._lookup_live = slow
        with patch.object(ratings, "LOOKUP_TIMEOUT_SECONDS", 0.01):
            self.assertEqual((await service.get(NAME))["status"], "unavailable")
        self.assertIsNone(self.row()["refresh_token"])
        self.assertEqual(self.row()["last_error"], "source_unavailable")

    async def test_shutdown_cancels_refresh_and_releases_database_lease(self):
        service = self.service()
        started = asyncio.Event()

        async def slow(_name):
            started.set()
            await asyncio.Event().wait()

        service._lookup_live = slow
        request = asyncio.create_task(service.get(NAME))
        await started.wait()
        await service.close()
        await asyncio.gather(request, return_exceptions=True)
        self.assertFalse(service._tasks)
        self.assertIsNone(self.row()["refresh_token"])

    async def test_pagination_checks_second_exact_person_before_profile_fetch(self):
        service = self.service(
            HtmlSession(
                HtmlResponse(catalogue(found=2, next_url=source.build_catalogue_url(NAME, 2))),
                HtmlResponse(catalogue([card(url=OTHER_PROFILE)], found=2)),
            )
        )
        self.assertEqual((await service.get(NAME))["status"], "ambiguous")
        self.assertEqual(len(service.http_session.calls), 2)
        self.assertIsNone(self.row()["profile"])

    async def test_incomplete_paginated_search_cannot_publish_unique_match(self):
        service = self.service(
            HtmlSession(
                HtmlResponse(catalogue(found=2, next_url=source.build_catalogue_url(NAME, 2)))
            )
        )
        with patch.object(ratings, "MAX_CATALOGUE_PAGES", 1):
            self.assertEqual((await service.get(NAME))["status"], "unavailable")
        self.assertEqual(len(service.http_session.calls), 1)
        self.assertIsNone(self.row()["profile"])

    async def test_complete_paginated_search_counts_nonmatching_people_before_unique_match(self):
        service = self.service(
            HtmlSession(
                HtmlResponse(catalogue(found=2, next_url=source.build_catalogue_url(NAME, 2))),
                HtmlResponse(
                    catalogue([card(name="Иванов Иван Иванович", url=OTHER_PROFILE)], found=2)
                ),
                HtmlResponse(structured(teacher())),
            )
        )
        self.assertEqual((await service.get(NAME))["status"], "matched")
        self.assertEqual(len(service.http_session.calls), 3)
        self.assertEqual(self.row()["provenance"]["catalogue_results_observed"], 2)

    async def test_skipped_page_cannot_publish_false_unique_match_or_negative(self):
        for first_name in (NAME, "Петров Петр Петрович"):
            with self.subTest(first_name=first_name):
                service = self.service(
                    HtmlSession(
                        HtmlResponse(
                            catalogue(
                                [card(name=first_name)],
                                found=3,
                                next_url=source.build_catalogue_url(NAME, 3),
                            )
                        ),
                        HtmlResponse(
                            catalogue(
                                [card(name="Иванов Иван Иванович", url=OTHER_PROFILE)], found=3
                            )
                        ),
                    )
                )
                with self.assertRaises(ratings.TeacherSourceUnavailable):
                    await service._lookup_live(NAME)
                self.assertEqual(len(service.http_session.calls), 2)

    async def test_repeated_cards_or_changed_total_cannot_establish_unique_match(self):
        cases = (
            ([card()], 2),
            ([card(name="Иванов Иван Иванович", url=OTHER_PROFILE)], 3),
            ([card(), card(name="Иванов Иван Иванович", url=OTHER_PROFILE)], 2),
        )
        for cards, total in cases:
            with self.subTest(cards=cards, total=total):
                service = self.service(
                    HtmlSession(
                        HtmlResponse(
                            catalogue(found=2, next_url=source.build_catalogue_url(NAME, 2))
                        ),
                        HtmlResponse(catalogue(cards, found=total)),
                    )
                )
                with self.assertRaises(ratings.TeacherSourceUnavailable):
                    await service._lookup_live(NAME)
                self.assertEqual(len(service.http_session.calls), 2)


class HttpBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_redirects_cannot_escape_source_query_page_or_profile_identity(self):
        cases = (
            (source.build_catalogue_url(NAME), "https://evil.test/", False),
            (
                source.build_catalogue_url(NAME),
                source.build_catalogue_url("Иванов Иван Иванович"),
                False,
            ),
            (source.build_catalogue_url(NAME), source.build_catalogue_url(NAME, 2), False),
            (PROFILE, OTHER_PROFILE, True),
            (PROFILE, "https://myprepod.ru/api/search/x", True),
        )
        for initial, target, profile in cases:
            session = HtmlSession(HtmlResponse(status=302, headers={"Location": target}))
            service = ratings.TeacherRatingsService(session)
            with (
                self.subTest(target=target),
                self.assertRaises((source.UnsafeSourceUrl, ratings.TeacherSourceUnavailable)),
            ):
                await service._fetch_html(initial, NAME, [0], profile=profile)
            self.assertEqual(len(session.calls), 1)
            await service.close()

    async def test_size_mime_and_compression_bounds_apply_before_parsing(self):
        responses = (
            HtmlResponse(b"x" * (source.MAX_HTML_BYTES + 1)),
            HtmlResponse("{}", headers={"Content-Type": "application/json"}),
            HtmlResponse("compressed", headers={"Content-Encoding": "gzip"}),
        )
        for response in responses:
            session = HtmlSession(response)
            service = ratings.TeacherRatingsService(session)
            with self.assertRaises(ratings.TeacherSourceUnavailable):
                await service._fetch_html(source.build_catalogue_url(NAME), NAME, [0])
            self.assertEqual(len(session.calls), 1)
            await service.close()
        response = HtmlResponse(b"x" * (source.MAX_HTML_BYTES + 1))
        response.content_length = None
        service = ratings.TeacherRatingsService(HtmlSession(response))
        with self.assertRaises(ratings.TeacherSourceUnavailable):
            await service._fetch_html(source.build_catalogue_url(NAME), NAME, [0])
        await service.close()

    async def test_transient_http_retries_once_and_total_request_budget_is_hard(self):
        session = HtmlSession(HtmlResponse(status=502), HtmlResponse("ok"))
        service = ratings.TeacherRatingsService(session)
        with patch.object(ratings, "HTTP_START_INTERVAL_SECONDS", 0):
            result = await service._fetch_html(source.build_catalogue_url(NAME), NAME, [0])
        self.assertEqual(result[0], "ok")
        self.assertEqual(len(session.calls), 2)
        with self.assertRaises(ratings.TeacherSourceUnavailable):
            await service._fetch_html(
                source.build_catalogue_url(NAME), NAME, [ratings.MAX_HTTP_REQUESTS]
            )
        self.assertEqual(len(session.calls), 2)
        await service.close()

    async def test_http_concurrency_and_start_rate_are_bounded(self):
        session = HtmlSession(*(HtmlResponse("ok", delay=0.06) for _ in range(4)))
        service = ratings.TeacherRatingsService(session)
        with patch.object(ratings, "HTTP_START_INTERVAL_SECONDS", 0.02):
            await asyncio.gather(
                *(
                    service._fetch_html(source.build_catalogue_url(NAME), NAME, [0])
                    for _ in range(4)
                )
            )
        self.assertEqual(session.max_active, 2)
        self.assertTrue(all(b - a >= 0.015 for a, b in zip(session.starts, session.starts[1:])))
        await service.close()


class TeacherRatingApiTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router.router, prefix="/api")
        self.app.state.teacher_ratings_service = AsyncMock()
        self.app.state.teacher_ratings_service.get.return_value = {
            "query_name": NAME,
            "status": "matched",
            "profile": {"name": NAME, "url": PROFILE, "department": None, "vote_count": None},
            "checked_at": datetime(2026, 10, 10, tzinfo=UTC),
            "stale": False,
        }
        self.client = TestClient(self.app)

    def test_public_response_keeps_nulls_and_utc_time_and_uses_client_limiter(self):
        limiter = AsyncMock()
        with patch.object(router, "enforce_rate_limit", limiter):
            response = self.client.get("/api/schedule/teacher-ratings", params={"name": NAME})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["profile"]["rating_percent"])
        self.assertIsNone(payload["profile"]["review_count"])
        self.assertTrue(payload["checked_at"].endswith("Z"))
        self.assertEqual(limiter.await_args.kwargs["scope"], "teacher_ratings")

    def test_rate_limit_rejects_before_lookup(self):
        with patch.object(router, "enforce_rate_limit", AsyncMock(side_effect=HTTPException(429))):
            response = self.client.get("/api/schedule/teacher-ratings", params={"name": NAME})
        self.assertEqual(response.status_code, 429)
        self.app.state.teacher_ratings_service.get.assert_not_awaited()

    def test_blank_or_oversize_query_is_rejected(self):
        for value in ("", "я" * 201):
            response = self.client.get("/api/schedule/teacher-ratings", params={"name": value})
            self.assertEqual(response.status_code, 422)


class TeacherRatingMigrationTests(unittest.TestCase):
    def test_upgrade_creates_real_constraints_and_downgrade_preserves_other_tables(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "alembic/versions/ff5f60718293_teacher_rating_cache.py"
        )
        spec = importlib.util.spec_from_file_location("teacher_rating_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        self.assertEqual(migration.down_revision, "fe4e5f607182")
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE keep_existing_data (id INTEGER PRIMARY KEY)"))
            connection.execute(text("INSERT INTO keep_existing_data VALUES (1)"))
            with patch.object(migration, "op", Operations(MigrationContext.configure(connection))):
                migration.upgrade()
                columns = {
                    column["name"]
                    for column in inspect(connection).get_columns("teacher_rating_cache")
                }
                self.assertEqual(columns, set(TeacherRatingCache.__table__.columns.keys()))
                values = {
                    "identity_key": "1" * 64,
                    "university_key": "fa",
                    "canonical_name": "иванов иван иванович",
                    "next_check_at": datetime.now(UTC),
                    "status": "not_found",
                }
                connection.execute(TeacherRatingCache.__table__.insert().values(**values))
                with self.assertRaises(IntegrityError):
                    connection.execute(
                        TeacherRatingCache.__table__.insert().values(
                            **{**values, "identity_key": "2" * 64}
                        )
                    )
                with self.assertRaises(IntegrityError):
                    connection.execute(
                        TeacherRatingCache.__table__.insert().values(
                            **{
                                **values,
                                "identity_key": "3" * 64,
                                "canonical_name": "other",
                                "status": "bad",
                            }
                        )
                    )
                migration.downgrade()
                self.assertNotIn("teacher_rating_cache", inspect(connection).get_table_names())
                self.assertEqual(
                    connection.execute(text("SELECT id FROM keep_existing_data")).scalar(), 1
                )
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
