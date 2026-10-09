"""Curriculum API authorization, upload bounds, source validation and public caching contract."""

import asyncio
import os
import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "curriculum-api-test-secret-at-least-32-bytes")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from fastapi_stats_app.auth import get_current_user
from fastapi_stats_app.routers import curriculum_router as api
from shared_lib.models import CurriculumDocument, CurriculumGroup
from tests.test_curriculum_documents import HEADERS, synthetic_pdf
from tests.test_curriculum_service import _AsyncSession


class TestCurriculumAPI(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(api.router, prefix="/api")
        self.app.dependency_overrides[get_current_user] = lambda: {"role": "admin", "id": 1}
        self.app.dependency_overrides[api.get_shared_http_session] = lambda: object()
        self.rate_limit = patch.object(api, "enforce_rate_limit", AsyncMock())
        self.rate = self.rate_limit.start()
        self.addCleanup(self.rate_limit.stop)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.metadata = {
            "title": "Plan 2023",
            "source_url": "https://www.fa.ru/upload/plan.pdf",
            "program": "01.03.02",
            "profile": "Applied ML",
            "campus": "Moscow",
            "admission_year": 2023,
            "study_form": "Full time",
        }

    def test_every_admin_endpoint_rejects_non_admin_without_work(self):
        self.app.dependency_overrides[get_current_user] = lambda: {"role": "user", "id": 2}
        routes = [
            ("get", "/curricula"),
            ("post", "/curricula"),
            ("get", "/curricula/1"),
            ("post", "/curricula/1/refresh"),
            ("put", "/curricula/1/document"),
            ("get", "/curricula/1/document"),
            ("post", "/curricula/1/publish"),
            ("put", "/curricula/1/groups"),
            ("delete", "/curricula/1"),
            ("post", "/curricula/1/reprocess"),
            ("put", "/curricula/1/scan-layout"),
        ]
        for method, path in routes:
            with self.subTest(path=path, method=method):
                response = getattr(self.client, method)("/api" + path)
                self.assertEqual(response.status_code, 403)

    def test_official_source_validation_blocks_unrelated_and_internal_urls(self):
        with patch.object(
            api.service, "create_curriculum", AsyncMock(return_value={"id": 1})
        ) as create:
            good = self.client.post("/api/curricula", json=self.metadata)
            self.assertEqual(good.status_code, 201)
            for url in (
                "http://www.fa.ru/a.pdf",
                "https://fa.ru.evil.test/a.pdf",
                "https://127.0.0.1/a.pdf",
                "file:///a.pdf",
            ):
                response = self.client.post(
                    "/api/curricula", json={**self.metadata, "source_url": url}
                )
                self.assertEqual(response.status_code, 422, url)
            self.assertEqual(create.await_count, 1)

    def test_explicit_scan_layout_schema_and_reset(self):
        with patch.object(
            api.service, "create_curriculum", AsyncMock(return_value={"id": 1})
        ) as create:
            response = self.client.post(
                "/api/curricula", json={**self.metadata, "scan_layout": "fa_legacy_v1"}
            )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(create.await_args.args[0]["scan_layout"], "fa_legacy_v1")
            self.assertEqual(
                self.client.post(
                    "/api/curricula", json={**self.metadata, "scan_layout": "guess"}
                ).status_code,
                422,
            )
        with patch.object(
            api.service, "set_scan_layout", AsyncMock(return_value={"scan_layout": None})
        ) as change:
            for value in ("fa_legacy_v1", "fa_compact_v1", None):
                response = self.client.put(
                    "/api/curricula/1/scan-layout", json={"scan_layout": value}
                )
                self.assertEqual(response.status_code, 200)
                change.assert_awaited_with(1, value)
            for body in ({}, {"scan_layout": "guess"}, {"scan_layout": None, "extra": True}):
                self.assertEqual(
                    self.client.put("/api/curricula/1/scan-layout", json=body).status_code, 422
                )
            self.assertEqual(change.await_count, 3)

    def test_supplement_parent_id_is_optional_strict_and_positive(self):
        with patch.object(
            api.service,
            "create_curriculum",
            AsyncMock(return_value={"id": 2, "parent_document_id": 1}),
        ) as create:
            response = self.client.post(
                "/api/curricula", json={**self.metadata, "parent_document_id": 1}
            )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(create.await_args.args[0]["parent_document_id"], 1)
            for invalid in (0, -1, True, "1", 1.5):
                with self.subTest(parent=invalid):
                    self.assertEqual(
                        self.client.post(
                            "/api/curricula", json={**self.metadata, "parent_document_id": invalid}
                        ).status_code,
                        422,
                    )
            self.assertEqual(create.await_count, 1)

    def test_supplement_http_scope_provenance_binding_and_deletion(self):
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        self.addCleanup(engine.dispose)
        CurriculumDocument.__table__.create(engine)
        CurriculumGroup.__table__.create(engine)

        @asynccontextmanager
        async def sessions():
            with Session(engine, expire_on_commit=False) as db:
                yield _AsyncSession(db)

        base_row = {
            "discipline_code": "base.1",
            "discipline_name": "Base course",
            "semester": 7,
            "kind": "exam",
            "page": 1,
            "evidence": "Exam in semester 7",
        }
        child_row = {
            "discipline_code": "brs.1",
            "discipline_name": "Graph learning",
            "semester": 7,
            "kind": "pass",
            "page": 35,
            "evidence": "Pass in semester 7",
        }
        with patch.object(api.service, "get_session", sessions):
            parent = self.client.post("/api/curricula", json=self.metadata).json()
            child_meta = {
                **self.metadata,
                "parent_document_id": parent["id"],
                "title": "BRS",
                "source_url": "https://www.fa.ru/upload/brs.pdf",
            }
            self.assertEqual(
                self.client.post(
                    "/api/curricula", json={**child_meta, "admission_year": 2025}
                ).status_code,
                422,
            )
            self.assertEqual(
                self.client.post(
                    "/api/curricula", json={**child_meta, "parent_document_id": 999}
                ).status_code,
                404,
            )
            response = self.client.post("/api/curricula", json=child_meta)
            self.assertEqual(response.status_code, 201, response.text)
            child = response.json()
            self.assertEqual(child["parent_document_id"], parent["id"])
            self.assertEqual(
                self.client.post(
                    "/api/curricula", json={**child_meta, "parent_document_id": child["id"]}
                ).status_code,
                422,
            )
            self.assertEqual(
                self.client.put(
                    f"/api/curricula/{child['id']}/groups", json={"groups": []}
                ).status_code,
                422,
            )
            for document, row, pages, pdf in (
                (parent, base_row, 2, b"%PDF-base"),
                (child, child_row, 40, b"%PDF-brs"),
            ):
                prefix = f"/api/curricula/{document['id']}"
                self.assertEqual(
                    self.client.put(
                        prefix + "/document",
                        content=pdf,
                        headers={"Content-Type": "application/pdf"},
                    ).status_code,
                    200,
                )
                with patch.object(
                    api.service,
                    "parse_document_in_worker",
                    AsyncMock(
                        return_value={
                            "status": "needs_review",
                            "assessments": [row],
                            "warnings": [],
                            "page_count": pages,
                        }
                    ),
                ):
                    asyncio.run(api.service.process_curriculum_queue())
                candidate = self.client.get(prefix).json()
                self.assertEqual(
                    self.client.post(
                        prefix + "/publish",
                        json={"expected_hash": candidate["pending_hash"], "assessments": [row]},
                    ).status_code,
                    200,
                )
            mapping = {
                "groups": [
                    {
                        "group_id": "group",
                        "group_name": "Group",
                        "terms": [
                            {"semester": 7, "start_date": "2026-09-01", "end_date": "2027-01-31"},
                        ],
                    }
                ]
            }
            self.assertEqual(
                self.client.put(f"/api/curricula/{parent['id']}/groups", json=mapping).status_code,
                200,
            )
            result = self.client.get(
                "/api/schedule/curriculum",
                params={
                    "group_id": "group",
                    "discipline": "Graph learning",
                    "lesson_date": "2026-10-09",
                },
            ).json()
            self.assertEqual(result["status"], "confirmed")
            row = result["assessments"][0]
            self.assertEqual(
                (row["page"], row["source_url"], row["source_title"]),
                (35, child_meta["source_url"], "BRS"),
            )
            self.assertEqual(self.client.get(row["snapshot_url"]).content, b"%PDF-brs")
            registry = self.client.get("/api/curricula").json()
            self.assertEqual(
                next(d for d in registry if d["id"] == child["id"])["parent_document_id"],
                parent["id"],
            )
            self.assertEqual(self.client.delete(f"/api/curricula/{parent['id']}").status_code, 204)
            self.assertIsNone(
                self.client.get(f"/api/curricula/{child['id']}").json()["parent_document_id"]
            )
            self.assertEqual(self.client.get(row["snapshot_url"]).content, b"%PDF-brs")

    def test_real_pdf_import_review_mapping_and_snapshot_through_http(self):
        """Exercise API schemas, actual PDF parser and SQL persistence together."""
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        self.addCleanup(engine.dispose)
        CurriculumDocument.__table__.create(engine)
        CurriculumGroup.__table__.create(engine)

        @asynccontextmanager
        async def sessions():
            with Session(engine, expire_on_commit=False) as db:
                yield _AsyncSession(db)

        original = synthetic_pdf([HEADERS, ["B1.01", "Machine learning", "7", "", "", "7", ""]])
        replacement = synthetic_pdf([HEADERS, ["B1.01", "Machine learning", "", "7", "", "", ""]])
        with patch.object(api.service, "get_session", sessions):
            created = self.client.post("/api/curricula", json=self.metadata)
            self.assertEqual(created.status_code, 201, created.text)
            prefix = f"/api/curricula/{created.json()['id']}"
            imported = self.client.put(
                prefix + "/document", content=original, headers={"Content-Type": "application/pdf"}
            )
            self.assertEqual(imported.status_code, 200, imported.text)
            self.assertEqual(imported.json()["processing_state"], "queued")
            # The HTTP request only persisted a job. Exercise the actual bounded
            # child process separately, like the scheduler's minute tick.
            completed = asyncio.run(api.service.process_curriculum_queue())
            self.assertEqual(completed, {"processed": 1, "failed": 0})
            candidate = self.client.get(prefix).json()
            self.assertEqual(candidate["status"], "parsed")
            self.assertEqual(len(candidate["candidates"]), 2)
            published = self.client.post(
                prefix + "/publish",
                json={
                    "expected_hash": candidate["pending_hash"],
                    "assessments": candidate["candidates"],
                },
            )
            self.assertEqual(published.status_code, 200, published.text)
            self.assertEqual(published.json()["status"], "published")
            bound = self.client.put(
                prefix + "/groups",
                json={
                    "groups": [
                        {
                            "group_id": "test-group",
                            "group_name": "Test group",
                            "terms": [
                                {
                                    "semester": 7,
                                    "start_date": "2026-09-01",
                                    "end_date": "2027-01-31",
                                }
                            ],
                        }
                    ]
                },
            )
            self.assertEqual(bound.status_code, 200, bound.text)
            query = {
                "group_id": "test-group",
                "discipline": "Machine learning",
                "lesson_date": "2026-10-09",
            }
            lookup = self.client.get("/api/schedule/curriculum", params=query).json()
            self.assertEqual(lookup["status"], "confirmed")
            self.assertEqual({row["kind"] for row in lookup["assessments"]}, {"exam", "coursework"})
            snapshot = lookup["assessments"][0]["snapshot_url"]
            self.assertEqual(self.client.get(snapshot).content, original)
            updated = self.client.put(
                prefix + "/document",
                content=replacement,
                headers={"Content-Type": "application/pdf"},
            )
            self.assertEqual(updated.status_code, 200)
            lookup = self.client.get("/api/schedule/curriculum", params=query).json()
            self.assertTrue(lookup["stale"])
            self.assertEqual({row["kind"] for row in lookup["assessments"]}, {"exam", "coursework"})
            self.assertEqual(self.client.get(snapshot).content, original)
            obsolete = self.client.post(
                prefix + "/publish",
                json={
                    "expected_hash": candidate["pending_hash"],
                    "assessments": candidate["candidates"],
                },
            )
            self.assertEqual(obsolete.status_code, 409)
            self.assertEqual(self.client.delete(prefix).status_code, 204)
            self.assertEqual(
                self.client.get("/api/schedule/curriculum", params=query).json()["status"],
                "unmapped",
            )
            self.assertEqual(self.client.get(snapshot).status_code, 404)

    def test_raw_upload_size_type_and_signature_are_checked_before_import(self):
        with patch.object(
            api.service, "refresh_curriculum", AsyncMock(return_value={"id": 1})
        ) as refresh:
            self.assertEqual(
                self.client.put("/api/curricula/1/document", content=b"%PDF-test").status_code, 415
            )
            self.assertEqual(
                self.client.put(
                    "/api/curricula/1/document",
                    content=b"html",
                    headers={"content-type": "application/pdf"},
                ).status_code,
                422,
            )
            with patch.object(api.service, "MAX_PDF_BYTES", 5):
                response = self.client.put(
                    "/api/curricula/1/document",
                    content=b"%PDF-large",
                    headers={"content-type": "application/pdf"},
                )
            self.assertEqual(response.status_code, 413)
            refresh.assert_not_awaited()
            response = self.client.put(
                "/api/curricula/1/document",
                content=b"%PDF-valid",
                headers={"content-type": "application/pdf"},
            )
            self.assertEqual(response.status_code, 200)
            refresh.assert_awaited_once_with(1, uploaded_pdf=b"%PDF-valid")

    def test_public_lookup_is_rate_limited_and_does_not_require_auth_or_fetch(self):
        self.app.dependency_overrides.pop(get_current_user)
        result = {"status": "unmapped", "group_id": "162426", "assessments": []}
        with (
            patch.object(
                api.service, "lookup_curriculum", AsyncMock(return_value=result)
            ) as lookup,
            patch.object(api.service, "fetch_official_document", AsyncMock()) as fetch,
        ):
            response = self.client.get(
                "/api/schedule/curriculum",
                params={
                    "group_id": "162426",
                    "discipline": "Семантические технологии",
                    "lesson_date": "2026-10-09",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), result)
        self.assertEqual(lookup.await_args.args[2].isoformat(), "2026-10-09")
        self.rate.assert_awaited_once()
        fetch.assert_not_awaited()

    def test_malformed_date_and_empty_group_never_hit_lookup(self):
        with patch.object(api.service, "lookup_curriculum", AsyncMock()) as lookup:
            for params in (
                {"group_id": "1", "discipline": "Math", "lesson_date": "invalid"},
                {"group_id": "", "discipline": "Math", "lesson_date": "2026-10-09"},
            ):
                self.assertEqual(
                    self.client.get("/api/schedule/curriculum", params=params).status_code, 422
                )
        lookup.assert_not_awaited()

    def test_conflict_and_not_found_status_are_preserved(self):
        with patch.object(
            api.service,
            "get_curriculum",
            AsyncMock(side_effect=api.service.CurriculumNotFoundError("Curriculum not found")),
        ):
            self.assertEqual(self.client.get("/api/curricula/1").status_code, 404)
        with patch.object(
            api.service,
            "refresh_curriculum",
            AsyncMock(side_effect=api.service.CurriculumConflictError("Refresh running")),
        ):
            self.assertEqual(self.client.post("/api/curricula/1/refresh").status_code, 409)

    def test_published_snapshot_has_pdf_type_and_only_accepts_matching_version_in_service(self):
        digest = "a" * 64
        with patch.object(
            api.service, "get_curriculum_pdf", AsyncMock(return_value=b"%PDF-snapshot")
        ) as pdf:
            response = self.client.get(f"/api/schedule/curriculum/documents/1/{digest}.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        pdf.assert_awaited_once_with(1, digest)
        with patch.object(
            api.service,
            "get_curriculum_pdf",
            AsyncMock(side_effect=api.service.CurriculumNotFoundError("Version not found")),
        ):
            self.assertEqual(
                self.client.get(f"/api/schedule/curriculum/documents/1/{digest}.pdf").status_code,
                404,
            )

    def test_publish_validates_required_evidence_and_hash_before_mutating(self):
        with patch.object(api.service, "publish_curriculum", AsyncMock()) as publish:
            response = self.client.post(
                "/api/curricula/1/publish", json={"expected_hash": "old", "assessments": []}
            )
        self.assertEqual(response.status_code, 422)
        publish.assert_not_awaited()

    def test_admin_delete_returns_empty_response(self):
        with patch.object(api.service, "delete_curriculum", AsyncMock()) as remove:
            response = self.client.delete("/api/curricula/1")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        remove.assert_awaited_once_with(1)


if __name__ == "__main__":
    unittest.main()
