import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

FASTAPI_AVAILABLE = True
try:
    from fastapi import FastAPI, HTTPException, WebSocketException
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    # Ensure module import works with mandatory secret check.
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests")

    from fastapi_stats_app.auth import (
        _get_jwt_secret_key,
        get_ws_user,
        require_admin,
        require_ws_admin,
    )
    from fastapi_stats_app.main import read_root_html, read_user_details_html
    from fastapi_stats_app.routers import ws_router
    from fastapi_stats_app.routers.studio_router import get_owned_project_or_404
    from fastapi_stats_app.routers.ws_router import can_subscribe_user_updates
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _RunningTask:
    def done(self):
        return False


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

    def test_require_ws_admin_allows_admin(self):
        user = {"role": "admin", "id": 1}
        self.assertEqual(require_ws_admin(user), user)

    def test_require_ws_admin_rejects_non_admin_with_policy_violation(self):
        with self.assertRaises(WebSocketException) as ctx:
            require_ws_admin({"role": "user", "id": 2})

        self.assertEqual(ctx.exception.code, 1008)

    def test_stats_websocket_rejects_non_admin_before_accept(self):
        app = FastAPI()
        app.include_router(ws_router.router)
        app.dependency_overrides[get_ws_user] = lambda: {"role": "user", "id": 2}

        with TestClient(app) as client:
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with client.websocket_connect("/ws/stats/total_actions"):
                    self.fail("non-admin stats WebSocket connection was accepted")

        self.assertEqual(ctx.exception.code, 1008)
        self.assertFalse(ws_router.stats_manager.active_connections)

    def test_stats_websocket_accepts_admin_and_sends_initial_payload(self):
        app = FastAPI()
        app.include_router(ws_router.router)
        app.dependency_overrides[get_ws_user] = lambda: {"role": "admin", "id": 1}
        initial_payload = {"total_actions": 7, "leaderboard": []}

        ws_router.stats_manager.active_connections.clear()
        with (
            patch.object(ws_router, "stats_update_task", _RunningTask()),
            patch.object(
                ws_router,
                "last_sent_stats_data_str",
                '{"total_actions": 7, "leaderboard": []}',
            ),
            TestClient(app) as client,
        ):
            with client.websocket_connect("/ws/stats/total_actions") as websocket:
                self.assertEqual(websocket.receive_json(), initial_payload)

        self.assertFalse(ws_router.stats_manager.active_connections)

    def test_ws_guard_allows_admin(self):
        self.assertTrue(can_subscribe_user_updates({"role": "admin", "telegram_id": None}, 999))

    def test_ws_guard_allows_same_telegram_user(self):
        self.assertTrue(can_subscribe_user_updates({"role": "user", "telegram_id": 777}, 777))

    def test_ws_guard_rejects_other_user(self):
        self.assertFalse(can_subscribe_user_updates({"role": "user", "telegram_id": 1}, 2))

    def test_get_jwt_secret_key_raises_if_missing_in_production(self):
        with (
            patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True),
            self.assertRaises(RuntimeError),
        ):
            _get_jwt_secret_key()

    def test_get_jwt_secret_key_raises_for_prod_alias(self):
        with (
            patch.dict(os.environ, {"ENVIRONMENT": "prod"}, clear=True),
            self.assertRaises(RuntimeError),
        ):
            _get_jwt_secret_key()

    def test_get_jwt_secret_key_rejects_short_production_secret(self):
        with (
            patch.dict(
                os.environ,
                {"ENVIRONMENT": "production", "JWT_SECRET_KEY": "too-short"},
                clear=True,
            ),
            self.assertRaises(RuntimeError),
        ):
            _get_jwt_secret_key()

    def test_get_jwt_secret_key_fallback_in_development(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=True):
            key = _get_jwt_secret_key()
            self.assertTrue(bool(key))

    def test_get_jwt_secret_key_returns_value(self):
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "abc"}, clear=True):
            self.assertEqual(_get_jwt_secret_key(), "abc")

    async def test_legacy_dashboard_route_redirects_to_static_frontend(self):
        response = await read_root_html()

        self.assertEqual(response.status_code, 307)
        self.assertTrue(response.headers["location"].endswith("/stats"))

    async def test_legacy_user_route_preserves_user_id_in_static_redirect(self):
        response = await read_user_details_html(user_id=12345)

        self.assertEqual(response.status_code, 307)
        self.assertTrue(response.headers["location"].endswith("/admin-user.html?user_id=12345"))

    def test_studio_loads_pinned_sanitizer_before_markdown_parser(self):
        html = (PROJECT_ROOT / "main_site_frontend" / "studio.html").read_text(encoding="utf-8")

        sanitizer = "dompurify@3.4.16/dist/purify.min.js"
        self.assertIn(sanitizer, html)
        self.assertLess(html.index(sanitizer), html.index("marked@15.0.12/marked.min.js"))
        self.assertIn("/js/studio.js?v=12", html)

        cdn_tags = re.findall(
            r"<(?:script|link)\b[^>]+(?:cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com)[^>]*>",
            html,
            flags=re.IGNORECASE,
        )
        self.assertTrue(cdn_tags)
        for tag in cdn_tags:
            with self.subTest(tag=tag[:100]):
                self.assertIn("integrity=", tag)
                self.assertIn('crossorigin="anonymous"', tag)

    def test_studio_preview_sanitizes_html_and_renders_errors_as_text(self):
        script = (PROJECT_ROOT / "main_site_frontend" / "js" / "studio.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("window.DOMPurify", script)
        self.assertIn(".sanitize(renderedHtml, STUDIO_MARKDOWN_SANITIZE_CONFIG)", script)
        self.assertIn("errorElement.textContent", script)
        self.assertIn("container.replaceChildren(errorElement)", script)
        self.assertIn("typeof renderedDiagram === 'string'", script)
        self.assertIn("contentDiv.replaceChildren(diagramContainer)", script)
        self.assertIn("typeof tokenOrHref === 'object'", script)
        self.assertNotIn("contentDiv.innerHTML = marked.parse", script)
        self.assertNotIn('contentDiv.innerHTML = `<pre class="text-red-500', script)

    def test_studio_security_assets_are_versioned_in_offline_cache(self):
        service_worker = (PROJECT_ROOT / "main_site_frontend" / "service-worker.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('const CACHE_VERSION = "mpb-site-v34"', service_worker)
        self.assertIn('"/css/studio.css?v=1"', service_worker)
        self.assertIn('"/js/studio.js?v=12"', service_worker)

    def test_studio_csp_rejects_inline_scripts_and_event_attributes(self):
        html = (PROJECT_ROOT / "main_site_frontend" / "studio.html").read_text(encoding="utf-8")
        nginx = (PROJECT_ROOT / "main_site_frontend" / "default.conf").read_text(
            encoding="utf-8"
        )

        self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html, re.IGNORECASE))
        self.assertNotIn("<style", html.lower())
        self.assertIsNone(re.search(r"\son[a-z]+\s*=", html, re.IGNORECASE))
        self.assertIn('location = /studio {', nginx)
        self.assertIn('location = /studio.html {', nginx)
        self.assertIn("Content-Security-Policy", nginx)
        self.assertIn("script-src-attr 'none'", nginx)
        script_directive = nginx.split("script-src ", 1)[1].split(";", 1)[0]
        self.assertNotIn("'unsafe-inline'", script_directive)
        self.assertIn("'unsafe-eval'", script_directive)
        self.assertIn("worker-src 'self' blob: https://cdnjs.cloudflare.com", nginx)
        self.assertIn("frame-src 'self' blob: data:", nginx)

    @unittest.skipUnless(shutil.which("node"), "node is required for frontend date tests")
    def test_single_lesson_ics_converts_moscow_time_to_utc(self):
        script_path = PROJECT_ROOT / "main_site_frontend" / "js" / "schedule_render.js"
        node_script = """
            const fs = require('fs');
            const vm = require('vm');
            const context = { window: {}, console, setTimeout, clearTimeout };
            vm.createContext(context);
            vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
            const convert = context.window.ScheduleRender.formatMoscowIcsUtc;
            process.stdout.write(JSON.stringify([
                convert('2026.09.24', '09:00'),
                convert('2026-09-24', '02:15')
            ]));
        """
        completed = subprocess.run(
            ["node", "-e", node_script, str(script_path)],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(
            completed.stdout,
            '["20260924T060000Z","20260923T231500Z"]',
        )
        source = script_path.read_text(encoding="utf-8")
        self.assertIn("`DTSTART:${formatMoscowIcsUtc", source)
        self.assertIn("`DTEND:${formatMoscowIcsUtc", source)
        self.assertNotIn("DTSTART;TZID=Europe/Moscow", source)
