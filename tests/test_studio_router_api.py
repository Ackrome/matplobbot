import base64
import io
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import unquote

from PIL import Image

FASTAPI_AVAILABLE = True
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests")
    from fastapi_stats_app.routers import studio_router
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

    def test_import_draft_is_atomic_and_invalid_templates_do_not_write(self):
        self.db.add = Mock()

        async def assign_id():
            self.db.add.call_args_list[0].args[0].id = 50

        self.db.flush.side_effect = assign_id
        response = self.client.post(
            "/api/studio/projects",
            json={
                "name": "Мой проект",
                "project_type": "markdown",
                "initial_content": "# Мой черновик",
            },
        )
        self.assertEqual(response.status_code, 200)
        file = self.db.add.call_args_list[1].args[0]
        self.assertEqual(
            (file.project_id, file.file_path, file.content_text), (50, "main.md", "# Мой черновик")
        )
        self.db.commit.assert_awaited_once()
        self.db.add.reset_mock()
        response = self.client.post(
            "/api/studio/projects",
            json={"name": "Invalid", "project_type": "latex", "template_id": "markdown"},
        )
        self.assertEqual(response.status_code, 400)
        self.db.add.assert_not_called()

    def test_project_crud_rejects_foreign_owner(self):
        self.db.execute.return_value = _mock_scalar_result(None)
        for method, path in [
            ("patch", "/api/studio/projects/9"),
            ("post", "/api/studio/projects/9/duplicate"),
            ("delete", "/api/studio/projects/9"),
        ]:
            kwargs = {} if method == "delete" else {"json": {"name": "Copy"}}
            self.assertEqual(getattr(self.client, method)(path, **kwargs).status_code, 404)
        self.db.commit.assert_not_awaited()

    def test_duplicate_preserves_sources_and_binary_files_without_build_cache(self):
        project = SimpleNamespace(
            id=9, owner_id=1, project_type="latex", build_cache=b"private cache"
        )
        files = [
            SimpleNamespace(
                file_path="main.tex", content_text="source", content_binary=None, is_main=True
            ),
            SimpleNamespace(
                file_path="image.png", content_text=None, content_binary=b"\x00\xff", is_main=False
            ),
        ]
        self.db.execute.side_effect = [_mock_scalar_result(project), _mock_scalars_result(files)]
        self.db.add = Mock()

        async def assign_id():
            self.db.add.call_args_list[0].args[0].id = 60

        self.db.flush.side_effect = assign_id
        response = self.client.post("/api/studio/projects/9/duplicate", json={"name": "Copy"})
        self.assertEqual(response.status_code, 200)
        copy, text, binary = [call.args[0] for call in self.db.add.call_args_list]
        self.assertIsNone(copy.build_cache)
        self.assertEqual((text.content_text, binary.content_binary), ("source", b"\x00\xff"))
        self.assertTrue(text.is_main)
        self.assertEqual(binary.project_id, 60)

    def test_project_filename_rejects_paths_and_control_characters(self):
        self.assertEqual(studio_router._sanitize_project_filename("diagram.png"), "diagram.png")
        for filename in (
            "../secret.txt",
            "nested/image.png",
            r"nested\image.png",
            "bad\x00.txt",
            ".latexmkrc",
            "latexmkrc",
            "texmf.cnf",
            "attack.html",
            "attack.svg",
        ):
            with self.subTest(filename=filename), self.assertRaises(HTTPException) as raised:
                studio_router._sanitize_project_filename(filename)
            self.assertEqual(raised.exception.status_code, 400)

    def test_asset_query_token_does_not_authenticate(self):
        self.app.dependency_overrides.pop(studio_router.get_current_user)
        response = self.client.get("/api/studio/projects/9/assets/image.png?token=not-a-session")
        self.assertEqual(response.status_code, 401)

    def test_legacy_html_or_disguised_image_is_sandboxed_download(self):
        for name in ("attack.html", "fake.png", "attack.svg"):
            self.db.execute.side_effect = [
                _mock_scalar_result(SimpleNamespace(id=9, owner_id=1)),
                _mock_scalar_result(
                    SimpleNamespace(
                        content_binary=b'<script>window.marker="executed"</script>',
                        content_text=None,
                    )
                ),
            ]
            response = self.client.get(f"/api/studio/projects/9/assets/{name}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "application/octet-stream")
            self.assertEqual(response.headers["content-disposition"], "attachment")
            self.assertIn("sandbox", response.headers["content-security-policy"])
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")
            self.assertEqual(response.headers["cache-control"], "no-store")

    def test_valid_raster_keeps_inline_preview(self):
        buffer = io.BytesIO()
        Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
        content = buffer.getvalue()
        self.db.execute.side_effect = [
            _mock_scalar_result(SimpleNamespace(id=9, owner_id=1)),
            _mock_scalar_result(SimpleNamespace(content_binary=content, content_text=None)),
        ]
        response = self.client.get("/api/studio/projects/9/assets/picture.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.content, content)

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

    def test_zip_export_uses_ascii_fallback_and_utf8_filename(self):
        project = SimpleNamespace(id=7, owner_id=1, name='Курсовая "работа" финал')
        files = [
            SimpleNamespace(
                file_path="main.tex",
                content_text="Привет",
                content_binary=None,
            )
        ]
        self.db.execute.side_effect = [
            _mock_scalar_result(project),
            _mock_scalars_result(files),
        ]

        response = self.client.get("/api/studio/projects/7/export/zip")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")
        disposition = response.headers["content-disposition"]
        self.assertIn('filename="project_export.zip"', disposition)
        encoded_name = disposition.split("filename*=UTF-8''", 1)[1]
        self.assertEqual(unquote(encoded_name), 'Курсовая "работа" финал_export.zip')

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
