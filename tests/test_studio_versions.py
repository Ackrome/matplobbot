"""Test named snapshots with real relational writes and the normal project build endpoint."""

import base64
import os
import runpy
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, inspect, null, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from alembic.migration import MigrationContext
from alembic.operations import Operations

os.environ.setdefault("JWT_SECRET_KEY", "studio-versions-test-secret-at-least-32-bytes")

from fastapi_stats_app.routers import studio_jobs_router, studio_router, studio_versions_router
from shared_lib.models import (
    Project,
    ProjectFile,
    ProjectVersion,
    ProjectVersionFile,
    User,
    WebAccount,
)
from tests.test_curriculum_service import _AsyncSession


class AsyncTestSession(_AsyncSession):
    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()

    async def delete(self, value):
        self.session.delete(value)


class TestStudioVersions(unittest.TestCase):
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
                lambda value: (
                    None
                    if value is None
                    else len(value.encode("utf-8") if isinstance(value, str) else value)
                ),
            )

        for model in User, WebAccount, Project, ProjectFile, ProjectVersion, ProjectVersionFile:
            model.__table__.create(self.engine)
        with Session(self.engine) as db:
            db.add_all([WebAccount(id=1, username="owner"), WebAccount(id=2, username="other")])
            db.flush()
            db.add_all(
                [
                    Project(
                        id=9,
                        owner_id=1,
                        name="Старый проект",
                        project_type="latex",
                        build_cache=b"compile-cache",
                    ),
                    Project(id=10, owner_id=1, name="Another owned project", project_type="latex"),
                ]
            )
            db.flush()
            db.add_all(
                [
                    ProjectFile(
                        project_id=9,
                        file_path="document.tex",
                        content_text="Исходник",
                        is_main=True,
                    ),
                    ProjectFile(
                        project_id=9, file_path="includes/intro.tex", content_text="", is_main=False
                    ),
                    ProjectFile(
                        project_id=9,
                        file_path="images/logo.png",
                        content_binary=b"\x00\xffLogo",
                        is_main=null(),
                    ),
                ]
            )
            db.commit()

        async def database():
            with Session(self.engine, expire_on_commit=False) as db:
                yield AsyncTestSession(db)

        self.app = FastAPI()
        for module in studio_router, studio_versions_router, studio_jobs_router:
            self.app.include_router(module.router, prefix="/api")
        self.owner = 1
        self.app.dependency_overrides[studio_versions_router.get_db_session_dependency] = database
        self.app.dependency_overrides[studio_versions_router.get_current_user] = lambda: {
            "id": self.owner
        }
        self.enterContext(patch.object(studio_versions_router, "enforce_rate_limit", AsyncMock()))
        self.enterContext(patch.object(studio_jobs_router, "enforce_rate_limit", AsyncMock()))
        self.client = self.enterContext(TestClient(self.app, raise_server_exceptions=False))
        self.path = "/api/studio/projects/9/versions"

    def create_version(self):
        response = self.client.post(self.path, json={"name": "  Точка сохранения  "})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_version_and_copy_preserve_legacy_paths_main_and_bytes(self):
        self.assertEqual(self.client.get(self.path).json(), [])
        version = self.create_version()
        self.assertEqual(version["name"], "Точка сохранения")
        self.assertEqual(version["project_name"], "Старый проект")
        self.assertEqual(version["file_count"], 3)
        self.assertEqual(version["byte_count"], len("Исходник".encode()) + len(b"\x00\xffLogo"))
        route = f"{self.path}/{version['id']}"
        detail = self.client.get(route)
        self.assertEqual(detail.headers["cache-control"], "private, no-store")
        self.assertEqual(
            detail.json()["files"],
            [
                {"path": "document.tex", "is_main": True, "is_binary": False},
                {"path": "images/logo.png", "is_main": False, "is_binary": True},
                {"path": "includes/intro.tex", "is_main": False, "is_binary": False},
            ],
        )
        with Session(self.engine) as db:
            live_file = db.scalars(
                select(ProjectFile).where(ProjectFile.file_path == "document.tex")
            ).one()
            live_file.content_text = "Новый текст"
            db.get(Project, 9).name = "Переименованный оригинал"
            db.commit()
        response = self.client.post(route + "/restore", json={"name": "Восстановленная копия"})
        self.assertEqual(response.status_code, 201, response.text)
        copy_id = response.json()["id"]
        self.assertNotEqual(copy_id, 9)
        files = self.client.get(f"/api/studio/projects/{copy_id}")
        self.assertEqual(files.status_code, 200, files.text)
        self.assertFalse(next(item["is_main"] for item in files.json() if item["is_binary"]))
        with Session(self.engine) as db:
            self.assertEqual(db.get(Project, 9).name, "Переименованный оригинал")
            self.assertIsNone(db.get(Project, copy_id).build_cache)
            self.assertEqual(db.get(Project, copy_id).project_type, "latex")
        mock = AsyncMock(return_value={"job_id": "test", "status": "queued"})
        with patch.object(studio_jobs_router, "_enqueue", mock):
            job = self.client.post(f"/api/studio/projects/{copy_id}/jobs")
        self.assertEqual(job.status_code, 202, job.text)
        payload, main, cache = mock.await_args.args[1]
        self.assertEqual(main, "document.tex")
        self.assertIsNone(cache)
        self.assertEqual(
            payload,
            [
                {"path": "document.tex", "text": "Исходник"},
                {"path": "images/logo.png", "binary": base64.b64encode(b"\x00\xffLogo").decode()},
                {"path": "includes/intro.tex", "text": ""},
            ],
        )

    def test_private_routes_and_wrong_project_version_are_rejected(self):
        version = self.create_version()
        route = f"{self.path}/{version['id']}"
        self.assertEqual(
            self.client.get(f"/api/studio/projects/10/versions/{version['id']}").status_code, 404
        )
        self.owner = 2
        requests = [
            ("GET", self.path, None),
            ("GET", route, None),
            ("POST", self.path, {"name": "Foreign version"}),
            ("POST", route + "/restore", {"name": "Foreign copy"}),
            ("DELETE", route, None),
        ]
        for method, url, body in requests:
            self.assertEqual(self.client.request(method, url, json=body).status_code, 404)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count(ProjectVersion.id))), 1)
            self.assertEqual(db.scalar(select(func.count(Project.id))), 2)

    def test_duplicate_names_and_account_quotas_are_checked_atomically(self):
        version = self.create_version()
        duplicate = self.client.post(self.path, json={"name": version["name"]})
        self.assertEqual(duplicate.json()["detail"]["code"], "version_name_taken")
        with patch.object(studio_versions_router, "MAX_VERSIONS_PER_ACCOUNT", 1):
            exceeded = self.client.post(
                "/api/studio/projects/10/versions", json={"name": "Other project"}
            )
            self.assertEqual(exceeded.json()["detail"]["code"], "version_quota")
        route = f"{self.path}/{version['id']}"
        with patch.object(studio_versions_router, "MAX_RESTORE_BYTES_PER_ACCOUNT", 1):
            exceeded = self.client.post(route + "/restore", json={"name": "Another copy"})
        self.assertEqual(exceeded.json()["detail"]["code"], "version_restore_quota")
        self.assertEqual(self.client.delete(route).status_code, 204)
        self.assertEqual(self.client.get(self.path).json(), [])
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count(ProjectVersionFile.version_id))), 0)

    def test_failed_insert_leaves_no_partial_version_or_restore(self):
        for table in ("project_version_files", "project_files"):
            if table == "project_files":
                version = self.create_version()
            with self.engine.begin() as connection:
                connection.exec_driver_sql(
                    f"CREATE TRIGGER fail_copy BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'fixture failure'); END"
                )
            route = (
                self.path
                if table == "project_version_files"
                else f"{self.path}/{version['id']}/restore"
            )
            self.assertEqual(self.client.post(route, json={"name": "Fail"}).status_code, 500)
            with Session(self.engine) as db:
                self.assertEqual(
                    db.scalar(select(func.count(ProjectVersion.id))),
                    0 if table == "project_version_files" else 1,
                )
                self.assertEqual(db.scalar(select(func.count(Project.id))), 2)
            with self.engine.begin() as connection:
                connection.exec_driver_sql("DROP TRIGGER fail_copy")

    def test_migration_roundtrip_retains_old_projects(self):
        module = runpy.run_path(
            str(
                Path(__file__).parents[1]
                / "alembic/versions/ea1400010004_studio_project_versions.py"
            )
        )
        ProjectVersionFile.__table__.drop(self.engine)
        ProjectVersion.__table__.drop(self.engine)
        with (
            self.engine.begin() as connection,
            Operations.context(MigrationContext.configure(connection)),
        ):
            module["upgrade"]()
            self.assertTrue(inspect(connection).has_table("project_version_files"))
            module["downgrade"]()
            self.assertFalse(inspect(connection).has_table("project_versions"))
        with Session(self.engine) as db:
            self.assertEqual(db.get(Project, 9).name, "Старый проект")
