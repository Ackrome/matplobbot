import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

FASTAPI_AVAILABLE = True
try:
    from fastapi import HTTPException

    # Ensure module import works with mandatory secret check.
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests")

    from fastapi_stats_app.auth import _get_jwt_secret_key, require_admin  # noqa: E402
    from fastapi_stats_app.routers.studio_router import get_owned_project_or_404  # noqa: E402
    from fastapi_stats_app.routers.ws_router import can_subscribe_user_updates  # noqa: E402
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class TestAuthorizationGuards(unittest.IsolatedAsyncioTestCase):
    async def test_owned_project_helper_returns_project(self):
        project = object()
        execute_result = Mock()
        execute_result.scalar_one_or_none.return_value = project
        db = AsyncMock()
        db.execute.return_value = execute_result

        result = await get_owned_project_or_404(db, project_id=1, owner_id=123)

        self.assertIs(result, project)
        db.execute.assert_awaited_once()

    async def test_owned_project_helper_raises_404_for_missing_project(self):
        execute_result = Mock()
        execute_result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute.return_value = execute_result

        with self.assertRaises(HTTPException) as ctx:
            await get_owned_project_or_404(db, project_id=1, owner_id=123)

        self.assertEqual(ctx.exception.status_code, 404)

    def test_require_admin_allows_admin(self):
        user = {"role": "admin", "id": 1}
        self.assertEqual(require_admin(user), user)

    def test_require_admin_rejects_non_admin(self):
        with self.assertRaises(HTTPException) as ctx:
            require_admin({"role": "user", "id": 2})

        self.assertEqual(ctx.exception.status_code, 403)

    def test_ws_guard_allows_admin(self):
        self.assertTrue(
            can_subscribe_user_updates({"role": "admin", "telegram_id": None}, 999)
        )

    def test_ws_guard_allows_same_telegram_user(self):
        self.assertTrue(
            can_subscribe_user_updates({"role": "user", "telegram_id": 777}, 777)
        )

    def test_ws_guard_rejects_other_user(self):
        self.assertFalse(
            can_subscribe_user_updates({"role": "user", "telegram_id": 1}, 2)
        )

    def test_get_jwt_secret_key_raises_if_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                _get_jwt_secret_key()

    def test_get_jwt_secret_key_returns_value(self):
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "abc"}, clear=True):
            self.assertEqual(_get_jwt_secret_key(), "abc")
