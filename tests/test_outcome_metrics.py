import os
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests")

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event

from fastapi_stats_app.routers import insights_router
from shared_lib import operational_metrics, product_metrics
from shared_lib.models import ProductEvent


class TestProductAggregates(unittest.IsolatedAsyncioTestCase):
    async def test_real_sql_aggregates_completed_outcomes_and_distinct_return_days(self):
        engine = create_engine("sqlite://")

        @event.listens_for(engine, "connect")
        def timezone_function(connection, record):
            connection.create_function("timezone", 2, lambda zone, value: value)

        with engine.connect() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE web_accounts (id INTEGER PRIMARY KEY, telegram_id INTEGER)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE product_events (id INTEGER PRIMARY KEY, event_name TEXT, web_account_id INTEGER, telegram_user_id INTEGER, dedupe_key TEXT, created_at DATETIME)"
            )
            now = datetime.now(UTC)
            rows = [
                ("search_started", 1, 0),
                ("search_succeeded", 1, 0),
                ("search_empty", 2, 0),
                ("search_failed", 2, 0),
                ("studio_succeeded", 1, 2),
                ("subscription_created", 3, 40),
            ]
            connection.execute(
                ProductEvent.__table__.insert(),
                [
                    {
                        "id": i + 1,
                        "event_name": name,
                        "web_account_id": user,
                        "created_at": now - timedelta(days=age),
                    }
                    for i, (name, user, age) in enumerate(rows)
                ],
            )

            class AsyncConnection:
                async def execute(self, query):
                    return connection.execute(query)

            result = await product_metrics.get_product_snapshot(AsyncConnection(), 30)
            self.assertEqual(result["active_users"], 2)
            self.assertEqual(result["returning_users"], 1)
            self.assertEqual(result["counts"]["subscription_created"], 0)
            self.assertAlmostEqual(result["search_success_rate"], 1 / 3, places=4)
            self.assertEqual(len(result["daily"]), 2)
            self.assertNotIn("web_account_id", str(result))
        engine.dispose()

    async def test_historical_web_events_and_linked_telegram_events_share_one_actor(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)

        @event.listens_for(engine, "connect")
        def timezone_function(connection, record):
            connection.create_function("timezone", 2, lambda zone, value: value)

        with engine.connect() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE web_accounts (id INTEGER PRIMARY KEY, telegram_id INTEGER)"
            )
            connection.exec_driver_sql("INSERT INTO web_accounts VALUES (7, 99), (8, NULL)")
            connection.exec_driver_sql(
                "CREATE TABLE product_events (id INTEGER PRIMARY KEY, event_name TEXT, web_account_id INTEGER, telegram_user_id INTEGER, dedupe_key TEXT, created_at DATETIME)"
            )
            now = datetime.now(UTC)
            records = [
                ("search_succeeded", 7, None, 2),
                ("subscription_created", 7, None, 2),
                ("search_succeeded", None, 99, 0),
                ("subscription_created", None, 99, 0),
                ("search_empty", 8, None, 0),
            ]
            connection.execute(
                ProductEvent.__table__.insert(),
                [
                    {
                        "id": index + 1,
                        "event_name": name,
                        "web_account_id": web_id,
                        "telegram_user_id": telegram_id,
                        "created_at": now - timedelta(days=age),
                    }
                    for index, (name, web_id, telegram_id, age) in enumerate(records)
                ],
            )

            class AsyncConnection:
                async def execute(self, query):
                    return connection.execute(query)

            result = await product_metrics.get_product_snapshot(AsyncConnection(), 30)
            self.assertEqual(result["active_users"], 2)
            self.assertEqual(result["returning_users"], 1)
            self.assertEqual(result["counts"]["subscription_created"], 1)
            self.assertEqual([row["active_users"] for row in result["daily"]], [1, 2])

    async def test_invalid_names_and_identity_combinations_are_rejected(self):
        for name, kwargs in [
            ("arbitrary_query_text", {"telegram_user_id": 1}),
            ("search_started", {}),
            ("search_started", {"web_account_id": 1, "telegram_user_id": 1}),
        ]:
            with self.assertRaises(ValueError):
                await product_metrics.record_product_event(name, **kwargs)

    async def test_telemetry_failure_does_not_fail_user_action(self):
        with patch.object(product_metrics, "get_session", side_effect=ConnectionError("test")):
            await product_metrics.record_product_event("search_succeeded", telegram_user_id=1)


class TestOperationalMetrics(unittest.IsolatedAsyncioTestCase):
    async def test_stale_success_is_distinct_from_healthy_process(self):
        rows = [
            {
                "last_success": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
                "last_status": "success",
            }
        ]
        rows += [{} for _ in range(len(operational_metrics.OPERATIONS) - 1)]
        pipe = Mock()
        pipe.execute = AsyncMock(return_value=rows)
        pipe.__aenter__ = AsyncMock(return_value=pipe)
        pipe.__aexit__ = AsyncMock(return_value=False)
        client = SimpleNamespace(client=SimpleNamespace(pipeline=Mock(return_value=pipe)))
        with patch.object(operational_metrics, "redis_client", client):
            result = await operational_metrics.get_operational_snapshot()
        self.assertTrue(result["available"])
        self.assertEqual(result["operations"][0]["status"], "stale")
        self.assertEqual(result["operations"][1]["status"], "unknown")

    async def test_unavailable_storage_is_not_an_empty_healthy_report(self):
        client = SimpleNamespace(client=SimpleNamespace(pipeline=Mock(side_effect=ConnectionError)))
        with patch.object(operational_metrics, "redis_client", client):
            self.assertFalse((await operational_metrics.get_operational_snapshot())["available"])


class TestInsightsAuthorization(unittest.TestCase):
    def test_non_admin_cannot_read_either_aggregate(self):
        app = FastAPI()
        app.include_router(insights_router.router, prefix="/api")

        async def forbidden():
            raise HTTPException(403, "Admin required")

        app.dependency_overrides[insights_router.require_admin] = forbidden
        app.dependency_overrides[insights_router.get_db_session_dependency] = lambda: AsyncMock()
        with TestClient(app) as client:
            for endpoint in ["operations", "product"]:
                self.assertEqual(client.get("/api/insights/" + endpoint).status_code, 403)


if __name__ == "__main__":
    unittest.main()
