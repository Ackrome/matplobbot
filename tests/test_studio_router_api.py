import base64
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

FASTAPI_AVAILABLE = True
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests")
    from fastapi_stats_app.routers import studio_router  # noqa: E402
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False


def _mock_scalar_result(value):
    result = Mock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalars_result(values):
    scalars = Mock()
    scalars.all.return_value = values
    result = Mock()
    result.scalars.return_value = scalars
    return result


class _FakeTelegramResponse:
    def __init__(self, status: int = 200, body: str = "ok"):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return self._body


class _FakeTelegramSession:
    def __init__(self, response: _FakeTelegramResponse):
        self.response = response
        self.post_calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url: str, **kwargs):
        self.post_calls.append((url, kwargs))
        return self.response


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class TestStudioRouterAPI(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(studio_router.router, prefix="/api")
        self.client = TestClient(self.app)
        self.db = AsyncMock()
        self.db.commit = AsyncMock()
        self.db.flush = AsyncMock()
        self.app.dependency_overrides[studio_router.get_db_session_dependency] = lambda: self.db
        self.current_user = {
            "id": 1,
            "username": "test-user",
            "role": "user",
            "db_obj": SimpleNamespace(telegram_id=777),
        }
        self.app.dependency_overrides[studio_router.get_current_user] = lambda: self.current_user

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_project_ownership_guard_returns_404(self):
        self.db.execute.return_value = _mock_scalar_result(None)

        response = self.client.get("/api/studio/projects/999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "Project not found")

    def test_rename_file_returns_400_on_conflict(self):
        project = SimpleNamespace(id=9, owner_id=1)
        self.db.execute.side_effect = [_mock_scalar_result(project), Exception("duplicate key")]

        response = self.client.put(
            "/api/studio/projects/9/files/10/rename",
            json={"new_name": "duplicate.tex"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json().get("detail"), "Filename might already exist or invalid")

    def test_send_telegram_rejects_unlinked_telegram_account(self):
        self.app.dependency_overrides[studio_router.get_current_user] = lambda: {
            "id": 1,
            "username": "test-user",
            "role": "user",
            "db_obj": SimpleNamespace(telegram_id=None),
        }

        response = self.client.post("/api/studio/projects/1/send_telegram")

        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json().get("detail"))

    def test_send_telegram_returns_400_when_compile_fails(self):
        project = SimpleNamespace(id=1, owner_id=1, name="My Project", build_cache=None)
        files = [
            SimpleNamespace(
                file_path="main.tex",
                content_text="\\documentclass{article}",
                content_binary=None,
                is_main=True,
            )
        ]
        self.db.execute.side_effect = [_mock_scalar_result(project), _mock_scalars_result(files)]

        with (
            patch.object(studio_router, "BOT_TOKEN", "test-token"),
            patch.object(studio_router, "dispatch_traced_task") as mocked_dispatch_task,
            patch.object(
                studio_router.asyncio,
                "to_thread",
                new=AsyncMock(return_value={"status": "error"}),
            ),
        ):
            mocked_dispatch_task.return_value = SimpleNamespace(get=Mock())
            response = self.client.post("/api/studio/projects/1/send_telegram")

        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json().get("detail"))

    def test_send_telegram_returns_500_when_telegram_api_fails(self):
        project = SimpleNamespace(id=1, owner_id=1, name="My Project", build_cache=None)
        files = [
            SimpleNamespace(
                file_path="main.tex",
                content_text="\\documentclass{article}",
                content_binary=None,
                is_main=True,
            )
        ]
        self.db.execute.side_effect = [_mock_scalar_result(project), _mock_scalars_result(files)]
        fake_session = _FakeTelegramSession(
            _FakeTelegramResponse(status=500, body="tg unavailable")
        )

        with (
            patch.object(studio_router, "BOT_TOKEN", "test-token"),
            patch.object(studio_router, "dispatch_traced_task") as mocked_dispatch_task,
            patch.object(
                studio_router.asyncio,
                "to_thread",
                new=AsyncMock(
                    return_value={"status": "ok", "pdf": base64.b64encode(b"%PDF-test").decode()}
                ),
            ),
            patch.object(studio_router.aiohttp, "ClientSession", return_value=fake_session),
        ):
            mocked_dispatch_task.return_value = SimpleNamespace(get=Mock())
            response = self.client.post("/api/studio/projects/1/send_telegram")

        self.assertEqual(response.status_code, 500)
        self.assertTrue(response.json().get("detail"))

    def test_send_telegram_escapes_project_name_in_html_caption(self):
        project = SimpleNamespace(
            id=1,
            owner_id=1,
            name="Report <draft> & \"quotes\" 'single'",
            build_cache=None,
        )
        files = [
            SimpleNamespace(
                file_path="main.tex",
                content_text="\\documentclass{article}",
                content_binary=None,
                is_main=True,
            )
        ]
        self.db.execute.side_effect = [_mock_scalar_result(project), _mock_scalars_result(files)]
        fake_session = _FakeTelegramSession(_FakeTelegramResponse(status=200, body="ok"))

        with (
            patch.object(studio_router, "BOT_TOKEN", "test-token"),
            patch.object(studio_router, "dispatch_traced_task") as mocked_dispatch_task,
            patch.object(
                studio_router.asyncio,
                "to_thread",
                new=AsyncMock(
                    return_value={"status": "ok", "pdf": base64.b64encode(b"%PDF-test").decode()}
                ),
            ),
            patch.object(studio_router.aiohttp, "ClientSession", return_value=fake_session),
        ):
            mocked_dispatch_task.return_value = SimpleNamespace(get=Mock())
            response = self.client.post("/api/studio/projects/1/send_telegram")

        self.assertEqual(response.status_code, 200)
        _, post_kwargs = fake_session.post_calls[0]
        fields = {
            field[0]["name"]: field[2]
            for field in post_kwargs["data"]._fields
            if "name" in field[0]
        }
        self.assertEqual(fields["parse_mode"], "HTML")
        self.assertEqual(
            fields["caption"],
            "📄 Ваш проект: <b>Report &lt;draft&gt; &amp; &quot;quotes&quot; &#x27;single&#x27;</b>",
        )
        self.assertNotIn("<draft>", fields["caption"])

    def test_studio_openapi_documents_typed_and_binary_responses(self):
        schema = self.app.openapi()

        compile_schema = schema["paths"]["/api/studio/compile"]["post"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        self.assertEqual(compile_schema["$ref"], "#/components/schemas/StudioCompileResponse")

        zip_content = schema["paths"]["/api/studio/projects/{project_id}/export/zip"]["get"][
            "responses"
        ]["200"]["content"]
        self.assertIn("application/zip", zip_content)

        asset_content = schema["paths"]["/api/studio/projects/{project_id}/assets/{file_path}"][
            "get"
        ]["responses"]["200"]["content"]
        self.assertIn("application/octet-stream", asset_content)
