"""Exercise Studio ZIP export, guarded preview and copy import with real archive bytes."""

import io
import os
import struct
import unittest
import warnings
import zipfile
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET_KEY", "studio-archive-test-secret-at-least-32-bytes")

from fastapi_stats_app.routers import studio_import_router, studio_router
from shared_lib import studio_archive as archives
from shared_lib.models import Project, ProjectFile, User, WebAccount
from tests.test_studio_versions import AsyncTestSession

PREVIEW = "/api/studio/projects/import/preview"
IMPORT = "/api/studio/projects/import"


class ArchiveTestSession(AsyncTestSession):
    def add_all(self, values):
        self.session.add_all(values)


def legacy_zip(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.comment = b"An ordinary legacy comment"
        for name, data in entries:
            archive.writestr(name, data)
    return output.getvalue()


class TestStudioArchive(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        self.addCleanup(self.engine.dispose)

        @event.listens_for(self.engine, "connect")
        def configure(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.create_function(
                "octet_length",
                1,
                lambda value: None
                if value is None
                else len(value.encode("utf-8") if isinstance(value, str) else value),
            )

        for model in User, WebAccount, Project, ProjectFile:
            model.__table__.create(self.engine)
        with Session(self.engine) as db:
            db.add_all([WebAccount(id=1, username="owner"), WebAccount(id=2, username="other")])
            db.flush()
            db.add(
                Project(
                    id=9,
                    owner_id=1,
                    name="Архив исследования",
                    project_type="latex",
                    build_cache=b"private cache",
                )
            )
            db.flush()
            db.add_all(
                [
                    ProjectFile(
                        project_id=9,
                        file_path="report/chapter.tex",
                        content_text="Данные\n\ufeff",
                        is_main=True,
                    ),
                    ProjectFile(
                        project_id=9,
                        file_path="report/data.txt",
                        content_binary=b"\x00\xff",
                        is_main=False,
                    ),
                    ProjectFile(
                        project_id=9,
                        file_path="report/empty.eps",
                        content_binary=b"",
                        is_main=False,
                    ),
                ]
            )
            db.commit()

        async def database():
            with Session(self.engine, expire_on_commit=False) as db:
                yield ArchiveTestSession(db)

        self.owner = 1
        self.app = FastAPI()
        self.app.include_router(studio_router.router, prefix="/api")
        self.app.include_router(studio_import_router.router, prefix="/api")
        self.app.dependency_overrides[studio_import_router.get_db_session_dependency] = database
        self.app.dependency_overrides[studio_import_router.get_current_user] = lambda: {
            "id": self.owner
        }
        self.rate_limit = self.enterContext(
            patch.object(studio_import_router, "enforce_rate_limit", AsyncMock())
        )
        self.client = self.enterContext(TestClient(self.app, raise_server_exceptions=False))

    def project_count(self):
        with Session(self.engine) as db:
            return db.scalar(select(func.count(Project.id)))

    def preview(self, payload):
        return self.client.post(
            PREVIEW, files={"file": ("previous.zip", payload, "application/zip")}
        )

    def confirm(self, payload, token, *, main="report/chapter.tex", project_type="latex"):
        return self.client.post(
            IMPORT,
            files={"file": ("previous.zip", payload, "application/zip")},
            data={
                "preview_token": token,
                "name": "Отдельная копия",
                "project_type": project_type,
                "main": main,
            },
        )

    def test_versioned_export_preserves_ordinary_zip_and_exact_project_inputs(self):
        exported = self.client.get("/api/studio/projects/9/export/zip")
        self.assertEqual(exported.status_code, 200, exported.text)
        self.assertEqual(exported.headers["cache-control"], "private, no-store")
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            self.assertEqual(
                archive.namelist(), ["report/chapter.tex", "report/data.txt", "report/empty.eps"]
            )
            self.assertEqual(archive.read("report/data.txt"), b"\x00\xff")
            self.assertEqual(archive.read("report/empty.eps"), b"")
        response = self.preview(exported.content)
        self.assertEqual(response.status_code, 200, response.text)
        preview = response.json()
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertTrue(preview["manifest"])
        self.assertEqual(
            (preview["name"], preview["type"], preview["main"]),
            ("Архив исследования", "latex", "report/chapter.tex"),
        )
        self.assertEqual(self.project_count(), 1)
        altered_metadata = self.confirm(
            exported.content, preview["preview_token"], project_type="markdown"
        )
        self.assertEqual(altered_metadata.status_code, 400)
        saved = self.confirm(exported.content, preview["preview_token"])
        self.assertEqual(saved.status_code, 201, saved.text)
        copy_id = saved.json()["id"]
        self.assertNotEqual(copy_id, 9)
        with Session(self.engine) as db:
            self.assertEqual(db.get(Project, 9).name, "Архив исследования")
            self.assertIsNone(db.get(Project, copy_id).build_cache)
            copy = db.scalars(
                select(ProjectFile)
                .where(ProjectFile.project_id == copy_id)
                .order_by(ProjectFile.file_path)
            ).all()
            original = db.scalars(
                select(ProjectFile)
                .where(ProjectFile.project_id == 9)
                .order_by(ProjectFile.file_path)
            ).all()

            def signature(files):
                return [(f.file_path, f.content_text, f.content_binary, f.is_main) for f in files]

            self.assertEqual(signature(copy), signature(original))

    def test_owner_bytes_and_expiry_bind_preview(self):
        payload = legacy_zip([("notes.md", "# File")])
        token = self.preview(payload).json()["preview_token"]
        altered = legacy_zip([("notes.md", "# Changed")])
        self.assertEqual(
            self.confirm(altered, token).json()["detail"]["code"], "archive_preview_required"
        )
        self.owner = 2
        self.assertEqual(self.confirm(payload, token).status_code, 409)
        self.owner = 1
        with patch.object(
            studio_import_router.time, "time", return_value=int(token.split(".")[0]) + 1
        ):
            self.assertEqual(self.confirm(payload, token).status_code, 409)
        self.assertEqual(self.project_count(), 1)

    def test_legacy_picks_one_main_or_requires_explicit_selection(self):
        payload = legacy_zip(
            [
                ("notes.md", "# File"),
                ("report.tex", "source"),
                ("assets/", b""),
                ("assets/figure.png", b"picture"),
            ]
        )
        preview = self.preview(payload).json()
        self.assertFalse(preview["manifest"])
        self.assertIsNone(preview["main"])
        self.assertIsNone(preview["type"])
        bad_main = self.confirm(payload, preview["preview_token"], main="assets/figure.png")
        self.assertEqual(bad_main.json()["detail"]["code"], "archive_no_main")
        self.assertEqual(
            self.confirm(
                payload, preview["preview_token"], main="notes.md", project_type="markdown"
            ).status_code,
            201,
        )

    def test_reject_bad_archives_and_large_legacy_export_remains_downloadable(self):
        binary = legacy_zip([("conference.pdf", b"data")])
        self.assertEqual(self.preview(binary).json()["detail"]["code"], "archive_no_main")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            duplicate = legacy_zip([("main.tex", "first"), ("main.tex", "second")])
        for invalid in (
            duplicate,
            legacy_zip([("../main.tex", "data")]),
            legacy_zip([("main.tex", ""), ("unknown.bin", "data")]),
        ):
            self.assertEqual(self.preview(invalid).json()["detail"]["code"], "archive_bad_files")
        self.assertEqual(self.preview(b"not a ZIP").json()["detail"]["code"], "archive_invalid")
        with patch.object(archives, "MAX_PROJECT_BYTES", 3):
            exported = self.client.get("/api/studio/projects/9/export/zip")
            self.assertEqual(exported.status_code, 200)
            declined = self.preview(exported.content)
            self.assertEqual(declined.status_code, 413)
            self.assertEqual(declined.json()["detail"]["code"], "archive_too_large")
        self.assertEqual(self.project_count(), 1)

    def test_stream_is_bounded_and_auth_runs_before_multipart(self):
        visited = []
        content_type = "multipart/form-data; boundary=test"

        def chunks():
            visited.append(True)
            yield b"--test\r\n"
            yield b"x" * 1000

        with patch.object(studio_import_router, "MAX_REQUEST_BYTES", 100):
            rejected = self.client.post(
                PREVIEW, content=chunks(), headers={"Content-Type": content_type}
            )
            self.assertEqual(rejected.status_code, 413, rejected.text)
        self.assertTrue(visited)
        visited.clear()

        def no_auth():
            raise HTTPException(401)

        self.app.dependency_overrides[studio_import_router.get_current_user] = no_auth
        self.assertEqual(
            self.client.post(
                PREVIEW, content=chunks(), headers={"Content-Type": content_type}
            ).status_code,
            401,
        )
        self.assertEqual(visited, [])

    def test_rejects_unbounded_index_variants_and_invalid_manifest_unicode(self):
        mismatched = bytearray(legacy_zip([("main.tex", "source")]))
        footer = mismatched.rfind(b"PK\x05\x06")
        struct.pack_into("<HH", mismatched, footer + 8, 0, 0)
        with patch.object(zipfile, "ZIP64_LIMIT", 1):
            zip64 = legacy_zip([("main.tex", "source")])
        for archive in (mismatched, zip64):
            response = self.preview(bytes(archive))
            self.assertIn(response.status_code, (400, 413))
            self.assertIn(
                response.json()["detail"]["code"], {"archive_invalid", "archive_too_large"}
            )
        invalid = io.BytesIO()
        with zipfile.ZipFile(invalid, "w") as archive:
            archive.writestr("main.tex", "source")
            archive.comment = b'Matplobbot-Studio-Project\n{"version":1,"name":"\\ud800","type":"latex","main":"main.tex","binary":"0"}'
        response = self.preview(invalid.getvalue())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["code"], "archive_manifest_invalid")

    def test_db_failure_rolls_back_new_project(self):
        payload = legacy_zip([("main.tex", "source")])
        token = self.preview(payload).json()["preview_token"]
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TRIGGER fail_import BEFORE INSERT ON project_files BEGIN SELECT RAISE(ABORT,'fixture failure'); END"
            )
        self.assertEqual(self.confirm(payload, token, main="main.tex").status_code, 500)
        self.assertEqual(self.project_count(), 1)
