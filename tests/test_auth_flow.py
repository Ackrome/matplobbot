import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

FASTAPI_AVAILABLE = True
try:
    from fastapi import Depends, FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from jose import jwt

    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests")

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
        db.add = Mock()
        return db

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
        decoded = jwt.decode(
            body["access_token"],
            fastapi_auth.SECRET_KEY,
            algorithms=[fastapi_auth.ALGORITHM],
        )
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

    def test_logout_returns_success_for_authenticated_user(self):
        self.app.dependency_overrides[auth_router.get_current_user] = lambda: {
            "id": 1,
            "role": "user",
        }

        response = self.client.post("/api/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success"})

    async def test_expired_jwt_is_rejected_by_get_current_user(self):
        expired_token = jwt.encode(
            {
                "sub": "1",
                "role": "user",
                "exp": datetime.utcnow() - timedelta(seconds=5),
            },
            fastapi_auth.SECRET_KEY,
            algorithm=fastapi_auth.ALGORITHM,
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
