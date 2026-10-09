import base64
import io
import json
import os
import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_stats_app.routers import ux_router
from shared_lib.database import get_db_session_dependency


class TestJourneyAPI(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(ux_router.router, prefix="/api")
        self.app.dependency_overrides[get_db_session_dependency] = lambda: None
        self.client = TestClient(self.app)

    def test_requires_auth_and_does_not_accept_content_or_unknown_events(self):
        payload = {"journey": "studio_first", "duration_ms": 800}
        self.assertEqual(self.client.post("/api/ux/events", json=payload).status_code, 401)
        self.app.dependency_overrides[ux_router.get_current_user] = lambda: {"id": 42}
        for extra in [
            {"document": "private"},
            {"journey": "query text"},
            {"duration_ms": -1},
            {"duration_ms": 3600001},
        ]:
            self.assertEqual(
                self.client.post("/api/ux/events", json={**payload, **extra}).status_code, 422
            )

    def test_records_only_bounded_duration_and_authenticated_owner(self):
        self.app.dependency_overrides[ux_router.get_current_user] = lambda: {"id": 42}
        with (
            patch.object(ux_router, "record_product_event", AsyncMock()) as record,
            patch.object(ux_router, "enforce_rate_limit", AsyncMock()) as limit,
        ):
            response = self.client.post(
                "/api/ux/events", json={"journey": "studio_first", "duration_ms": 800}
            )
        self.assertEqual(response.status_code, 202)
        record.assert_awaited_once_with("ux_studio_first", web_account_id=42, duration_ms=800)
        limit.assert_awaited_once()


class TestArchive(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node required for browser ZIP regression")
    def test_archive_preserves_unicode_binary_crc_and_rejects_duplicate_paths(self):
        source = Path(__file__).parents[1] / "main_site_frontend/js/archive_download.js"
        script = """
global.window=globalThis;
require(process.argv[1]);
(async()=>{
 const blob=MpbArchive.zip([{name:'проект/main.tex',text:'Текст'},{name:'проект/image.png',bytes:new Uint8Array([0,255,1])}]);
 let duplicate=false;try{MpbArchive.zip([{name:'a'},{name:'../a'}]);}catch{duplicate=true;}
 console.log(JSON.stringify({data:Buffer.from(await blob.arrayBuffer()).toString('base64'),duplicate,safe:MpbArchive.safePath('../../bad/name')}));
})();
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", script, str(source)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(data["data"]))) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read("проект/main.tex").decode(), "Текст")
            self.assertEqual(archive.read("проект/image.png"), b"\x00\xff\x01")
        self.assertTrue(data["duplicate"])
        self.assertEqual(data["safe"], "bad/name")
