import hashlib
import hmac
import json
import os
import time
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlencode

FASTAPI_AVAILABLE = True
try:
    from fastapi import Depends, FastAPI, HTTPException
    from fastapi.testclient import TestClient

    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests")
    os.environ.setdefault("BOT_TOKEN", "123456:test-token")

    from fastapi_stats_app import auth as fastapi_auth  # noqa: E402
    from fastapi_stats_app.routers import auth_router  # noqa: E402
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class TestAuthFlow(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(auth_router.router, prefix="/api")
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def _mock_db(self, *, account=None):
        db = Mock()
        execute_result = Mock()
        execute_result.scalar_one_or_none.return_value = account
        db.execute = AsyncMock(return_value=execute_result)
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.add = Mock()
        return db

    def _build_webapp_init_data(self, user_data, *, auth_date=None):
        params = {
            "auth_date": str(auth_date if auth_date is not None else int(time.time())),
            "query_id": "test-query",
            "user": json.dumps(user_data, separators=(",", ":")),
        }
        data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
        secret_key = hmac.new(
            b"WebAppData",
            os.environ["BOT_TOKEN"].encode("utf-8"),
            hashlib.sha256,
        ).digest()
        params["hash"] = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return urlencode(params)

    def test_register_creates_non_admin_user(self):
        db = self._mock_db(account=None)
        self.app.dependency_overrides[auth_router.get_db_session_dependency] = lambda: db

        response = self.client.post(
            "/api/auth/register",
            json={"username": "newuser", "password": "StrongPass123"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"status": "success"})
        self.assertTrue(db.add.called)
        created_account = db.add.call_args.args[0]
        self.assertEqual(created_account.role, "user")

    def test_login_returns_bearer_token(self):
        account = SimpleNamespace(
            id=7,
            role="user",
            password_hash=fastapi_auth.get_password_hash("s3cret-pass"),
        )
        db = self._mock_db(account=account)
        self.app.dependency_overrides[auth_router.get_db_session_dependency] = lambda: db

        response = self.client.post(
            "/api/auth/login",
            data={"username": "john", "password": "s3cret-pass"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["token_type"], "bearer")
        decoded = fastapi_auth.decode_access_token(body["access_token"])
        self.assertEqual(decoded["sub"], "7")
        self.assertEqual(decoded["role"], "user")

    def test_login_rejects_invalid_password(self):
        account = SimpleNamespace(
            id=8,
            role="user",
            password_hash=fastapi_auth.get_password_hash("correct-pass"),
        )
        db = self._mock_db(account=account)
        self.app.dependency_overrides[auth_router.get_db_session_dependency] = lambda: db

        response = self.client.post(
            "/api/auth/login",
            data={"username": "john", "password": "wrong-pass"},
        )

        self.assertEqual(response.status_code, 401)

    def test_telegram_webapp_init_data_verifier_accepts_valid_payload(self):
        init_data = self._build_webapp_init_data(
            {
                "id": 12345,
                "first_name": "Ivan",
                "last_name": "Petrov",
                "username": "ivan",
            }
        )

        parsed = fastapi_auth.parse_verified_telegram_webapp_init_data(init_data)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["id"], 12345)
        self.assertEqual(parsed["first_name"], "Ivan")

    def test_telegram_webapp_init_data_verifier_rejects_tampering(self):
        init_data = self._build_webapp_init_data({"id": 12345, "first_name": "Ivan"})
        tampered = init_data.replace("Ivan", "Eve")

        parsed = fastapi_auth.parse_verified_telegram_webapp_init_data(tampered)

        self.assertIsNone(parsed)

    def test_telegram_webapp_init_data_verifier_rejects_stale_payload(self):
        init_data = self._build_webapp_init_data(
            {"id": 12345, "first_name": "Ivan"},
            auth_date=int((datetime.now(UTC) - timedelta(days=2)).timestamp()),
        )

        parsed = fastapi_auth.parse_verified_telegram_webapp_init_data(init_data)

        self.assertIsNone(parsed)

    def test_logout_returns_success_for_authenticated_user(self):
        self.app.dependency_overrides[auth_router.get_current_user] = lambda: {
            "id": 1,
            "role": "user",
        }

        response = self.client.post("/api/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success"})

    def test_update_preferences_merges_existing_namespaces(self):
        account = SimpleNamespace(
            preferences={
                "calendar_sync": {
                    "enabled": True,
                    "custom_profiles": [{"id": "custom-1", "name": "Group 1"}],
                },
                "useShortNames": False,
            }
        )
        db = self._mock_db(account=account)
        self.app.dependency_overrides[auth_router.get_db_session_dependency] = lambda: db
        self.app.dependency_overrides[auth_router.get_current_user] = lambda: {
            "id": 1,
            "username": "Test User",
            "role": "user",
            "preferences": account.preferences,
            "db_obj": account,
        }

        response = self.client.put(
            "/api/auth/preferences",
            json={
                "preferences": {
                    "entity": {"type": "group", "id": "group-1", "name": "Group 1"},
                    "modules": ["Core"],
                    "useShortNames": True,
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            account.preferences["calendar_sync"]["custom_profiles"][0]["id"],
            "custom-1",
        )
        self.assertEqual(account.preferences["entity"]["id"], "group-1")
        self.assertEqual(account.preferences["modules"], ["Core"])
        self.assertTrue(account.preferences["useShortNames"])
        self.assertEqual(response.json()["preferences"], account.preferences)

    def test_update_preferences_locks_latest_account_before_merging(self):
        stale_account = auth_router.WebAccount(
            id=1,
            username="Test User",
            role="user",
            preferences={"useShortNames": False},
        )
        locked_account = auth_router.WebAccount(
            id=1,
            username="Test User",
            role="user",
            preferences={
                "calendar_sync": {
                    "enabled": True,
                    "custom_profiles": [{"id": "custom-2", "name": "Group 2"}],
                },
                "useShortNames": False,
            },
        )
        db = self._mock_db(account=locked_account)

        self.app.dependency_overrides[auth_router.get_db_session_dependency] = lambda: db
        self.app.dependency_overrides[auth_router.get_current_user] = lambda: {
            "id": 1,
            "username": "Test User",
            "role": "user",
            "preferences": {"useShortNames": False},
            "db_obj": stale_account,
        }

        response = self.client.put(
            "/api/auth/preferences",
            json={
                "preferences": {
                    "entity": {"type": "group", "id": "group-2", "name": "Group 2"},
                    "modules": ["Core"],
                    "useShortNames": True,
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        db.execute.assert_awaited()
        self.assertEqual(
            locked_account.preferences["calendar_sync"]["custom_profiles"][0]["id"],
            "custom-2",
        )
        self.assertEqual(locked_account.preferences["entity"]["id"], "group-2")
        self.assertTrue(locked_account.preferences["useShortNames"])
        self.assertEqual(response.json()["preferences"], locked_account.preferences)

    async def test_expired_jwt_is_rejected_by_get_current_user(self):
        expired_token = fastapi_auth.create_access_token(
            {
                "sub": "1",
                "role": "user",
            },
            expires_delta=timedelta(seconds=-5),
        )
        account = SimpleNamespace(
            id=1,
            role="user",
            telegram_id=None,
            username="u1",
            preferences={},
        )
        db = self._mock_db(account=account)

        with self.assertRaises(HTTPException) as ctx:
            await fastapi_auth.get_current_user(token=expired_token, db=db)

        self.assertEqual(getattr(ctx.exception, "status_code", None), 401)

    def test_admin_non_admin_access_matrix(self):
        app = FastAPI()

        @app.get("/admin-only")
        def admin_only(_user: dict = Depends(fastapi_auth.require_admin)):
            return {"status": "ok"}

        app.dependency_overrides[fastapi_auth.get_current_user] = lambda: {
            "id": 2,
            "role": "user",
        }
        client = TestClient(app)
        user_response = client.get("/admin-only")
        self.assertEqual(user_response.status_code, 403)

        app.dependency_overrides[fastapi_auth.get_current_user] = lambda: {
            "id": 1,
            "role": "admin",
        }
        admin_response = client.get("/admin-only")
        self.assertEqual(admin_response.status_code, 200)
