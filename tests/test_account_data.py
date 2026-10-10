"""Exercise ownership/cascades against an isolated in-memory relational database."""

import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests-at-least-32-bytes")
os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from fastapi_stats_app.auth import create_access_token, decode_access_token, get_current_user
from fastapi_stats_app.routers import ws_router
from shared_lib import models
from shared_lib.services import account_data


class _AsyncSessionAdapter:
    """Run ordinary SQLAlchemy statements unchanged, without an extra async DB dependency."""

    def __init__(self, session):
        self.session = session

    async def execute(self, stmt):
        return self.session.execute(stmt)

    async def commit(self):
        self.session.commit()


class TestAccountData(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        tables = [
            table
            for table in models.Base.metadata.sorted_tables
            if table.name not in {"cached_schedules", "search_documents"}
        ]
        models.Base.metadata.create_all(self.engine, tables=tables)
        self.sync = Session(self.engine, expire_on_commit=False)
        self.db = _AsyncSessionAdapter(self.sync)
        self.sync.add_all(
            [
                models.User(user_id=100, full_name="Owner", calendar_secret="secret"),
                models.User(user_id=200, full_name="Other"),
            ]
        )
        self.sync.flush()
        self.sync.add_all(
            [
                models.WebAccount(
                    id=1,
                    telegram_id=100,
                    role="user",
                    preferences={"theme": "dark"},
                    password_hash="private-hash",
                ),
                models.WebAccount(id=2, telegram_id=200, role="user", preferences={}),
            ]
        )
        self.sync.flush()
        self.sync.add_all(
            [
                models.Project(id=10, owner_id=1, name="Owner project", build_cache=b"cache"),
                models.Project(id=20, owner_id=2, name="Other project"),
            ]
        )
        self.sync.flush()
        self.sync.add_all(
            [
                models.ProjectFile(
                    id=11, project_id=10, file_path="main.tex", content_text="My work"
                ),
                models.ProjectFile(
                    id=12, project_id=10, file_path="image.png", content_binary=b"image"
                ),
                models.ProjectFile(
                    id=21, project_id=20, file_path="main.tex", content_text="Other work"
                ),
                models.UserAction(id=1, user_id=100, action_type="test"),
                models.UserFavorite(id=1, user_id=100, code_path="my/example"),
                models.MailAccount(
                    id=1,
                    user_id=100,
                    address="me@example.test",
                    host="mail.example.test",
                    protocol="imap",
                    credential=b"encrypted-secret",
                    checkpoint=b"mail-checkpoint",
                ),
                models.ProductEvent(id=1, telegram_user_id=100, event_name="search_started"),
                models.ProductEvent(id=2, web_account_id=1, event_name="studio_started"),
            ]
        )
        self.sync.commit()
        self.cache_patch = patch.object(account_data, "_clear_owner_cache", AsyncMock())
        self.cache_patch.start()
        self.jobs_patch = patch.object(account_data, "_clear_studio_jobs", AsyncMock())
        self.jobs_patch.start()

    def tearDown(self):
        self.cache_patch.stop()
        self.jobs_patch.stop()
        self.sync.close()
        self.engine.dispose()

    async def test_export_includes_only_owned_projects_and_no_credentials(self):
        payload = await account_data.export_account_data(self.db, account_id=1)
        self.assertEqual([item["id"] for item in payload["projects"]], [10])
        self.assertEqual({item["id"] for item in payload["project_files"]}, {11, 12})
        asset = next(item for item in payload["project_files"] if item["id"] == 12)
        self.assertEqual(asset["content_binary"]["encoding"], "base64")
        self.assertNotIn("password_hash", payload["account"])
        self.assertNotIn("calendar_secret", payload["telegram_user"])
        self.assertNotIn("credential", payload["mail_accounts"][0])
        self.assertNotIn("build_cache", payload["projects"][0])

    async def test_full_delete_cascades_and_rejects_previous_jwt(self):
        token = create_access_token({"sub": "1"})
        self.assertTrue(await account_data.delete_account_data(self.db, 1))
        self.sync.expire_all()
        for model in (
            models.ProjectFile,
            models.UserAction,
            models.UserFavorite,
            models.MailAccount,
            models.ProductEvent,
        ):
            rows = self.sync.execute(select(model)).scalars().all()
            self.assertEqual(len(rows), 1 if model is models.ProjectFile else 0)
        self.assertIsNone(self.sync.get(models.WebAccount, 1))
        self.assertIsNone(self.sync.get(models.User, 100))
        self.assertIsNotNone(self.sync.get(models.WebAccount, 2))
        self.assertIsNotNone(self.sync.get(models.Project, 20))
        with self.assertRaises(HTTPException) as error:
            await get_current_user(token=token, db=self.db)
        self.assertEqual(error.exception.status_code, 401)
        context = AsyncMock()
        context.__aenter__.return_value = self.db
        with patch.object(ws_router, "get_session", return_value=context):
            self.assertFalse(await ws_router.websocket_account_is_active({"id": 1}))
            self.assertTrue(
                await ws_router.websocket_account_is_active(
                    {
                        "id": 2,
                        "token_claims": decode_access_token(create_access_token({"sub": "2"})),
                    }
                )
            )

    async def test_telegram_only_keeps_access_to_studio(self):
        self.assertTrue(await account_data.delete_telegram_data(self.db, 100))
        self.sync.expire_all()
        self.assertEqual(self.sync.get(models.WebAccount, 1).telegram_id, 100)
        self.assertIsNotNone(self.sync.get(models.Project, 10))
        self.assertIsNone(self.sync.get(models.User, 100).calendar_secret)
        self.assertEqual(self.sync.get(models.User, 100).settings, {})
        self.assertEqual(self.sync.execute(select(models.MailAccount)).scalars().all(), [])
        self.assertEqual(self.sync.execute(select(models.UserAction)).scalars().all(), [])
        user = await get_current_user(token=create_access_token({"sub": "1"}), db=self.db)
        self.assertEqual(user["id"], 1)
