"""Relational regression coverage for reviewed curriculum publication and cached lookups."""

import asyncio
import copy
import hashlib
import runpy
import unittest
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, delete, event, inspect
from sqlalchemy.orm import Session

from alembic.migration import MigrationContext
from alembic.operations import Operations
from shared_lib.models import CurriculumDocument, CurriculumGroup
from shared_lib.services import curriculum_service as service
from shared_lib.services.curriculum_documents import MAX_DOCUMENT_BYTES, MAX_DOCUMENT_PAGES


class _AsyncSession:
    """Execute unchanged SQLAlchemy statements on SQLite without a test-only async dependency."""

    def __init__(self, session):
        self.session = session

    @asynccontextmanager
    async def begin(self):
        with self.session.begin():
            yield

    async def scalar(self, statement):
        return self.session.scalar(statement)

    async def scalars(self, statement):
        return self.session.scalars(statement)

    async def get(self, model, key, **kwargs):
        return self.session.get(model, key, **kwargs)

    async def execute(self, statement):
        return self.session.execute(statement)

    async def flush(self):
        self.session.flush()

    def add(self, item):
        self.session.add(item)


class TestCurriculumPersistence(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        CurriculumDocument.__table__.create(self.engine)
        CurriculumGroup.__table__.create(self.engine)

        @asynccontextmanager
        async def sessions():
            with Session(self.engine, expire_on_commit=False) as db:
                yield _AsyncSession(db)

        self.patches = [
            patch.object(service, "get_session", sessions),
            patch.dict("os.environ", {"CURRICULUM_REFRESH_DAYS": "7"}),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(self.engine.dispose)
        self.metadata = {
            "title": "Учебный план 2023",
            "source_url": "https://www.fa.ru/upload/plan.pdf",
            "program": "01.03.02",
            "profile": "Прикладное машинное обучение",
            "campus": "Москва",
            "admission_year": 2023,
            "study_form": "Очная",
        }
        self.rows = [
            {
                "discipline_code": "Б1.В.01",
                "discipline_name": "Семантические технологии",
                "semester": 7,
                "kind": "pass",
                "page": 2,
                "evidence": "Зачёты: 7",
            },
            {
                "discipline_code": "Б1.В.01",
                "discipline_name": "Семантические технологии",
                "semester": 8,
                "kind": "exam",
                "page": 2,
                "evidence": "Экзамены: 8",
            },
            {
                "discipline_code": "Б1.В.01",
                "discipline_name": "Семантические технологии",
                "semester": 7,
                "kind": "coursework",
                "page": 2,
                "evidence": "Курсовые работы: 7",
            },
        ]
        self.groups = [
            {
                "group_id": "162426",
                "group_name": "ПМ23-1",
                "terms": [
                    {"semester": 7, "start_date": "2026-09-01", "end_date": "2027-01-31"},
                    {"semester": 8, "start_date": "2027-02-01", "end_date": "2027-08-31"},
                ],
            }
        ]
        self.pdf = b"%PDF-1.7 reviewed fixture"

    async def imported(self):
        doc = await service.create_curriculum(self.metadata)
        with patch.object(
            service,
            "parse_document_in_worker",
            AsyncMock(
                return_value={
                    "status": "parsed",
                    "assessments": self.rows,
                    "warnings": [],
                    "page_count": 3,
                }
            ),
        ):
            doc = await service.refresh_curriculum(doc["id"], uploaded_pdf=self.pdf)
            self.assertEqual(doc["processing_state"], "queued")
            await service.process_curriculum_queue()
        return await service.get_curriculum(doc["id"])

    async def published(self):
        doc = await self.imported()
        doc = await service.publish_curriculum(doc["id"], doc["pending_hash"], self.rows)
        return await service.bind_curriculum_groups(doc["id"], self.groups)

    async def supplement(self, parent, *, rows=None, publish=True):
        """Import a synthetic separately paginated document through the real service."""
        rows = (
            rows
            if rows is not None
            else [
                {
                    "discipline_code": "BRS.graph",
                    "discipline_name": "Машинное обучение на графах",
                    "semester": 7,
                    "kind": "pass",
                    "page": 35,
                    "evidence": "Semester 7: pass",
                }
            ]
        )
        doc = await service.create_curriculum(
            {
                **self.metadata,
                "parent_document_id": parent["id"],
                "title": "БРС 2023",
                "source_url": "https://www.fa.ru/upload/brs.pdf",
            }
        )
        with patch.object(
            service,
            "parse_document_in_worker",
            AsyncMock(
                return_value={
                    "status": "needs_review",
                    "assessments": rows,
                    "warnings": [],
                    "page_count": 40,
                }
            ),
        ):
            await service.refresh_curriculum(
                doc["id"], uploaded_pdf=b"%PDF-supplement " + str(doc["id"]).encode()
            )
            await service.process_curriculum_queue()
        doc = await service.get_curriculum(doc["id"])
        if publish:
            doc = await service.publish_curriculum(doc["id"], doc["pending_hash"], rows)
        return doc

    async def test_supplement_uses_own_pages_source_and_versioned_snapshot(self):
        parent = await self.published()
        child = await self.supplement(parent)
        self.assertEqual(child["parent_document_id"], parent["id"])
        self.assertEqual(child["groups"], [])
        registry = await service.list_curricula()
        self.assertEqual(
            next(d for d in registry if d["id"] == child["id"])["parent_document_id"], parent["id"]
        )
        result = await service.lookup_curriculum(
            "162426", "Машинное обучение на графах", date(2026, 10, 9)
        )
        self.assertEqual((result["status"], result["semester"]), ("confirmed", 7))
        self.assertEqual(result["source_url"], child["source_url"])
        self.assertFalse(result["stale"])
        row = result["assessments"][0]
        self.assertEqual(
            (row["page"], row["kind"], row["source_document_id"]), (35, "pass", child["id"])
        )
        self.assertEqual(row["source_title"], child["title"])
        self.assertEqual(row["source_sha256"], child["published_hash"])
        self.assertEqual(
            row["snapshot_url"],
            f"/api/schedule/curriculum/documents/{child['id']}/{child['published_hash']}.pdf",
        )
        self.assertEqual(
            await service.get_curriculum_pdf(child["id"], child["published_hash"]),
            b"%PDF-supplement " + str(child["id"]).encode(),
        )
        self.assertEqual(
            await service.get_curriculum_pdf(parent["id"], parent["published_hash"]), self.pdf
        )
        await service.refresh_curriculum(
            child["id"], uploaded_pdf=b"%PDF-pending supplement replacement"
        )
        retained = await service.lookup_curriculum(
            "162426", "Машинное обучение на графах", date(2026, 10, 9)
        )
        self.assertEqual(retained["status"], "confirmed")
        self.assertTrue(retained["stale"])
        self.assertTrue(retained["review_pending"])
        self.assertEqual(retained["assessments"][0]["snapshot_url"], row["snapshot_url"])
        self.assertEqual(
            (await service.get_curriculum(parent["id"]))["published_hash"], parent["published_hash"]
        )

    async def test_unpublished_supplement_is_not_confirmed(self):
        parent = await self.published()
        await self.supplement(parent, publish=False)
        result = await service.lookup_curriculum(
            "162426", "Машинное обучение на графах", date(2026, 10, 9)
        )
        self.assertEqual(result["status"], "needs_review")
        self.assertTrue(result["review_pending"])
        self.assertEqual(result["assessments"], [])
        self.assertEqual(
            (await service.lookup_curriculum("162426", "Unknown course", date(2026, 10, 9)))[
                "status"
            ],
            "not_found",
        )

    async def test_supplement_requires_root_and_exact_scope(self):
        parent = await service.create_curriculum(self.metadata)
        for field, wrong in (
            ("program", "09.03.01"),
            ("profile", "Other"),
            ("campus", "Курск"),
            ("admission_year", 2025),
            ("study_form", "Заочная"),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                await service.create_curriculum(
                    {**self.metadata, "parent_document_id": parent["id"], field: wrong}
                )
        with self.assertRaises(service.CurriculumNotFoundError):
            await service.create_curriculum({**self.metadata, "parent_document_id": 999})
        child = await service.create_curriculum(
            {**self.metadata, "parent_document_id": parent["id"]}
        )
        with self.assertRaises(ValueError):
            await service.create_curriculum({**self.metadata, "parent_document_id": child["id"]})
        for invalid in (0, -1, True, "1"):
            with self.subTest(parent=invalid), self.assertRaises(ValueError):
                await service.create_curriculum({**self.metadata, "parent_document_id": invalid})
        self.assertEqual(len(await service.list_curricula()), 2)

    async def test_supplement_cannot_bind_groups_and_other_roots_do_not_leak(self):
        parent = await self.published()
        child = await self.supplement(parent)
        for groups in (self.groups, []):
            with self.assertRaises(ValueError):
                await service.bind_curriculum_groups(child["id"], groups)
        other = await service.create_curriculum(self.metadata)
        # A published supplementary document under another root is not visible,
        # even when its scope metadata and course name otherwise match.
        unrelated = await self.supplement(
            other, rows=[{**self.rows[0], "discipline_name": "Other root course"}]
        )
        self.assertEqual(unrelated["parent_document_id"], other["id"])
        self.assertEqual(
            (await service.lookup_curriculum("162426", "Other root course", date(2026, 10, 9)))[
                "status"
            ],
            "not_found",
        )
        # Defense against a malformed link written outside the service.
        with Session(self.engine) as db:
            db.get(CurriculumDocument, child["id"]).admission_year = 2025
            db.commit()
        self.assertEqual(
            (
                await service.lookup_curriculum(
                    "162426", "Машинное обучение на графах", date(2026, 10, 9)
                )
            )["status"],
            "not_found",
        )

    async def test_same_course_in_different_published_sources_is_ambiguous(self):
        parent = await self.published()
        await self.supplement(parent, rows=[self.rows[0]])
        result = await service.lookup_curriculum(
            "162426", "Семантические технологии", date(2026, 10, 9)
        )
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["reason"], "ambiguous_discipline")
        self.assertEqual(result["assessments"], [])
        await self.supplement(parent)
        await self.supplement(parent)
        result = await service.lookup_curriculum(
            "162426", "Машинное обучение на графах", date(2026, 10, 9)
        )
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["assessments"], [])

    async def test_supplement_uses_parent_semester_mapping_and_requires_parent_publication(self):
        parent = await self.imported()
        await service.bind_curriculum_groups(parent["id"], self.groups)
        await self.supplement(parent)
        result = await service.lookup_curriculum(
            "162426", "Машинное обучение на графах", date(2026, 10, 9)
        )
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["assessments"], [])
        await service.publish_curriculum(parent["id"], parent["pending_hash"], self.rows)
        result = await service.lookup_curriculum(
            "162426", "Машинное обучение на графах", date(2027, 4, 1)
        )
        self.assertEqual((result["status"], result["semester"]), ("confirmed", 8))
        self.assertEqual(result["assessments"][0]["semester"], 7)
        result = await service.lookup_curriculum(
            "162426", "Машинное обучение на графах", date(2025, 4, 1)
        )
        self.assertEqual((result["status"], result["reason"]), ("unavailable", "semester_unmapped"))

    async def test_deleting_root_unlinks_and_preserves_supplement_without_sqlite_foreign_keys(self):
        parent = await self.published()
        child = await self.supplement(parent)
        await service.delete_curriculum(parent["id"])
        survivor = await service.get_curriculum(child["id"])
        self.assertIsNone(survivor["parent_document_id"])
        self.assertEqual(survivor["published_hash"], child["published_hash"])
        self.assertEqual(survivor["groups"], [])
        self.assertEqual(
            (
                await service.lookup_curriculum(
                    "162426", "Машинное обучение на графах", date(2026, 10, 9)
                )
            )["status"],
            "unmapped",
        )

    async def test_import_never_publishes_without_explicit_review(self):
        doc = await self.imported()
        await service.bind_curriculum_groups(doc["id"], self.groups)
        result = await service.lookup_curriculum(
            "162426", "Семантические технологии", date(2026, 10, 9)
        )
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["assessments"], [])
        self.assertEqual(doc["pending_hash"], hashlib.sha256(self.pdf).hexdigest())
        self.assertIsNone(doc["published_hash"])

    async def test_group_scope_exact_title_semester_and_multiple_assessment_forms(self):
        await self.published()
        result = await service.lookup_curriculum(
            "162426", "  СЕМАНТИЧЕСКИЕ   технологии ", date(2026, 10, 9)
        )
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(result["semester"], 7)
        self.assertEqual(
            {row["kind"] for row in result["assessments"]}, {"pass", "exam", "coursework"}
        )
        self.assertEqual({row["semester"] for row in result["assessments"]}, {7, 8})
        self.assertFalse(result["stale"])
        self.assertTrue(all("snapshot_url" in row for row in result["assessments"]))
        other = await service.lookup_curriculum(
            "branch-162426", "Семантические технологии", date(2026, 10, 9)
        )
        self.assertEqual(other["status"], "unmapped")
        abbreviated = await service.lookup_curriculum(
            "162426", "Семантические тех...", date(2026, 10, 9)
        )
        self.assertEqual(abbreviated["status"], "not_found")
        no_term = await service.lookup_curriculum(
            "162426", "Семантические технологии", date(2025, 10, 9)
        )
        self.assertEqual(no_term["status"], "unavailable")
        self.assertEqual(no_term["reason"], "semester_unmapped")
        self.assertEqual(no_term["assessments"], [])

    async def test_changed_source_stages_replacement_and_preserves_reviewed_snapshot(self):
        original = await self.published()
        changed_rows = [{**self.rows[0], "kind": "graded_pass"}]
        with (
            patch.object(
                service, "fetch_official_document", AsyncMock(return_value=b"%PDF-1.7 changed")
            ),
            patch.object(
                service,
                "parse_document_in_worker",
                AsyncMock(
                    return_value={
                        "status": "parsed",
                        "assessments": changed_rows,
                        "warnings": [],
                        "page_count": 2,
                    }
                ),
            ),
        ):
            doc = await service.refresh_curriculum(original["id"], object())
            await service.process_curriculum_queue()
            doc = await service.get_curriculum(doc["id"])
        self.assertNotEqual(doc["pending_hash"], original["published_hash"])
        result = await service.lookup_curriculum(
            "162426", "Семантические технологии", date(2026, 10, 9)
        )
        self.assertEqual(result["status"], "confirmed")
        self.assertTrue(result["stale"])
        self.assertTrue(result["review_pending"])
        self.assertEqual(len(result["assessments"]), 3)
        self.assertEqual(
            await service.get_curriculum_pdf(doc["id"], original["published_hash"]), self.pdf
        )
        with self.assertRaises(service.CurriculumConflictError):
            await service.publish_curriculum(doc["id"], original["published_hash"], changed_rows)
        await service.publish_curriculum(doc["id"], doc["pending_hash"], changed_rows)
        result = await service.lookup_curriculum(
            "162426", "Семантические технологии", date(2026, 10, 9)
        )
        self.assertEqual(result["assessments"][0]["kind"], "graded_pass")
        with self.assertRaises(service.CurriculumNotFoundError):
            await service.get_curriculum_pdf(doc["id"], original["published_hash"])

    async def test_failed_or_invalid_import_keeps_published_and_records_sanitized_error(self):
        doc = await self.published()
        with patch.object(
            service,
            "fetch_official_document",
            AsyncMock(side_effect=RuntimeError("secret proxy body")),
        ):
            failed = await service.refresh_curriculum(doc["id"], object())
        self.assertEqual(failed["last_error"], "import_failed")
        self.assertNotIn("secret", str(failed))
        self.assertEqual(failed["published_hash"], doc["published_hash"])
        self.assertEqual(failed["checked_at"], doc["checked_at"])
        self.assertIsNotNone(failed["next_check_at"])
        result = await service.lookup_curriculum(
            "162426", "Семантические технологии", date(2026, 10, 9)
        )
        self.assertTrue(result["stale"])
        self.assertEqual(result["status"], "confirmed")
        invalid = await service.refresh_curriculum(doc["id"], uploaded_pdf=b"not a PDF")
        self.assertEqual(invalid["published_hash"], doc["published_hash"])

    async def test_unchanged_source_preserves_reviewed_corrections(self):
        doc = await self.imported()
        reviewed = [{**self.rows[0], "kind": "graded_pass"}]
        await service.publish_curriculum(doc["id"], doc["pending_hash"], reviewed)
        with patch.object(
            service,
            "parse_document_in_worker",
            AsyncMock(
                return_value={
                    "status": "parsed",
                    "assessments": self.rows,
                    "warnings": [],
                    "page_count": 3,
                }
            ),
        ):
            checked = await service.refresh_curriculum(doc["id"], uploaded_pdf=self.pdf)
        self.assertIsNone(checked["pending_hash"])
        self.assertEqual(checked["published_assessments"], reviewed)

    async def test_hash_cache_prevents_parsing_and_model_upgrade_preserves_review(self):
        doc = await self.published()
        with patch.object(service, "parse_document_in_worker", AsyncMock()) as parse:
            unchanged = await service.refresh_curriculum(doc["id"], uploaded_pdf=self.pdf)
            self.assertEqual(unchanged["processing_state"], "ready")
            self.assertEqual(
                await service.process_curriculum_queue(), {"processed": 0, "failed": 0}
            )
            parse.assert_not_awaited()
        with (
            patch.dict("os.environ", {"CURRICULUM_OCR_MODEL_VERSION": "new-russian-model"}),
            patch.object(
                service,
                "parse_document_in_worker",
                AsyncMock(
                    return_value={
                        "status": "needs_review",
                        "assessments": [],
                        "warnings": ["No rows"],
                        "page_count": 3,
                        "method": "ocr",
                        "engine_version": "Tesseract 5",
                    }
                ),
            ) as parse,
        ):
            result = await service.process_curriculum_queue()
        self.assertEqual(result["processed"], 1)
        parse.assert_awaited_once()
        upgraded = await service.get_curriculum(doc["id"])
        self.assertNotEqual(upgraded["parser_version"], doc["parser_version"])
        self.assertEqual(upgraded["published_assessments"], doc["published_assessments"])
        self.assertIsNone(upgraded["pending_hash"])

    async def test_queued_publish_blocked_and_explicit_retry_uses_cached_bytes(self):
        doc = await service.create_curriculum(self.metadata)
        queued = await service.refresh_curriculum(doc["id"], uploaded_pdf=self.pdf)
        with self.assertRaises(service.CurriculumConflictError):
            await service.publish_curriculum(doc["id"], queued["pending_hash"], self.rows)
        with patch.object(
            service,
            "parse_document_in_worker",
            AsyncMock(side_effect=service.CurriculumProcessingError("parse_timeout")),
        ):
            await service.process_curriculum_queue()
        failed = await service.get_curriculum(doc["id"])
        self.assertEqual(failed["processing_error"], "parse_timeout")
        with patch.object(service, "fetch_official_document", AsyncMock()) as fetch:
            retried = await service.reprocess_curriculum(doc["id"])
            fetch.assert_not_awaited()
        self.assertEqual(retried["processing_state"], "queued")
        self.assertIsNone(retried["processing_error"])

    async def test_cancelled_worker_lease_recovers_and_serializes_different_documents(self):
        first = await service.create_curriculum(self.metadata)
        second = await service.create_curriculum(self.metadata)
        await service.refresh_curriculum(first["id"], uploaded_pdf=self.pdf)
        await service.refresh_curriculum(second["id"], uploaded_pdf=self.pdf)
        with patch.object(
            service, "parse_document_in_worker", AsyncMock(side_effect=asyncio.CancelledError)
        ):
            with self.assertRaises(asyncio.CancelledError):
                await service.process_curriculum_queue()
        with patch.object(service, "parse_document_in_worker", AsyncMock()) as parse:
            self.assertEqual(
                await service.process_curriculum_queue(), {"processed": 0, "failed": 0}
            )
            parse.assert_not_awaited()
        with Session(self.engine) as db:
            row = db.get(CurriculumDocument, first["id"])
            row.processing_started_at = datetime.now(UTC) - timedelta(minutes=16)
            db.commit()
        with patch.object(
            service,
            "parse_document_in_worker",
            AsyncMock(
                return_value={
                    "status": "parsed",
                    "assessments": self.rows,
                    "warnings": [],
                    "page_count": 3,
                }
            ),
        ):
            self.assertEqual(
                await service.process_curriculum_queue(), {"processed": 1, "failed": 0}
            )
        self.assertEqual((await service.get_curriculum(first["id"]))["processing_state"], "ready")
        self.assertEqual((await service.get_curriculum(second["id"]))["processing_state"], "queued")

    async def test_replaced_source_during_ocr_ignores_stale_worker_result(self):
        doc = await service.create_curriculum(self.metadata)
        await service.refresh_curriculum(doc["id"], uploaded_pdf=self.pdf)

        async def replacement(_content, **_kwargs):
            await service.refresh_curriculum(doc["id"], uploaded_pdf=b"%PDF-newer-source")
            self.assertEqual(
                await service.process_curriculum_queue(), {"processed": 0, "failed": 0}
            )
            return {"status": "parsed", "assessments": self.rows, "warnings": [], "page_count": 3}

        with patch.object(service, "parse_document_in_worker", replacement):
            self.assertEqual(
                await service.process_curriculum_queue(), {"processed": 0, "failed": 0}
            )
        latest = await service.get_curriculum(doc["id"])
        self.assertEqual(latest["processing_state"], "queued")
        self.assertEqual(latest["candidates"], [])
        self.assertEqual(latest["pending_hash"], hashlib.sha256(b"%PDF-newer-source").hexdigest())

    async def test_ocr_previews_never_escape_to_public_facts(self):
        doc = await self.imported()
        rows = [{**self.rows[0], "ocr": {"confidence": 84, "crop_png_base64": "private-image"}}]
        published = await service.publish_curriculum(doc["id"], doc["pending_hash"], rows)
        self.assertNotIn("ocr", published["published_assessments"][0])
        await service.bind_curriculum_groups(doc["id"], self.groups)
        result = await service.lookup_curriculum(
            "162426", "Семантические технологии", date(2026, 10, 9)
        )
        self.assertNotIn("private-image", str(result))

    async def test_unsupported_page_count_and_oversized_pdf_retain_previous_source(self):
        doc = await self.published()
        self.assertEqual(service.MAX_PDF_BYTES, MAX_DOCUMENT_BYTES)
        for page_count in (0, MAX_DOCUMENT_PAGES + 1, True):
            with (
                self.subTest(page_count=page_count),
                patch.object(
                    service,
                    "parse_document_in_worker",
                    AsyncMock(
                        return_value={
                            "status": "needs_review",
                            "assessments": [],
                            "warnings": ["Unsupported page count"],
                            "page_count": page_count,
                        }
                    ),
                ),
            ):
                failed = await service.refresh_curriculum(
                    doc["id"], uploaded_pdf=b"%PDF-replacement"
                )
                await service.process_curriculum_queue()
                failed = await service.get_curriculum(doc["id"])
            self.assertEqual(failed["processing_error"], "invalid_pdf")
            self.assertEqual(failed["published_hash"], doc["published_hash"])
            self.assertEqual(
                await service.get_curriculum_pdf(doc["id"], doc["published_hash"]), self.pdf
            )
        with patch.object(service, "parse_document_in_worker") as parse:
            failed = await service.refresh_curriculum(
                doc["id"], uploaded_pdf=b"%PDF-" + b"x" * MAX_DOCUMENT_BYTES
            )
        parse.assert_not_called()
        self.assertEqual(failed["last_error"], "import_failed")
        self.assertEqual(
            await service.get_curriculum_pdf(doc["id"], doc["published_hash"]), self.pdf
        )

    async def test_duplicate_title_different_course_codes_is_ambiguous(self):
        doc = await self.imported()
        await service.publish_curriculum(
            doc["id"],
            doc["pending_hash"],
            self.rows + [{**self.rows[0], "discipline_code": "Б1.В.ДВ.01", "kind": "exam"}],
        )
        await service.bind_curriculum_groups(doc["id"], self.groups)
        result = await service.lookup_curriculum(
            "162426", "Семантические технологии", date(2026, 10, 9)
        )
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["assessments"], [])

    async def test_group_collision_is_atomic_and_removal_does_not_delete_document(self):
        first = await self.published()
        other = await service.create_curriculum({**self.metadata, "campus": "Краснодар"})
        with self.assertRaises(service.CurriculumConflictError):
            await service.bind_curriculum_groups(other["id"], self.groups)
        self.assertEqual(len((await service.get_curriculum(first["id"]))["groups"]), 1)
        await service.bind_curriculum_groups(first["id"], [])
        self.assertEqual(
            (await service.lookup_curriculum("162426", "X", date(2026, 10, 9)))["status"],
            "unmapped",
        )
        self.assertTrue((await service.get_curriculum(first["id"]))["published_hash"])

    async def test_delete_removes_bindings_and_snapshot_without_affecting_other_sources(self):
        doc = await self.published()
        other = await service.create_curriculum(self.metadata)
        await service.delete_curriculum(doc["id"])
        self.assertEqual(
            (await service.lookup_curriculum("162426", "X", date(2026, 10, 9)))["status"],
            "unmapped",
        )
        with self.assertRaises(service.CurriculumNotFoundError):
            await service.get_curriculum_pdf(doc["id"], doc["published_hash"])
        with self.assertRaises(service.CurriculumNotFoundError):
            await service.delete_curriculum(doc["id"])
        self.assertEqual([row["id"] for row in await service.list_curricula()], [other["id"]])

    async def test_scheduler_due_dates_survive_repeated_ticks_and_support_fortnight(self):
        doc = await self.published()
        with patch.object(service, "fetch_official_document", AsyncMock()) as fetch:
            first = await service.refresh_due_curricula(object())
        self.assertEqual(first["checked"], 0)
        fetch.assert_not_called()
        with Session(self.engine) as db:
            stored = db.get(CurriculumDocument, doc["id"])
            stored.next_check_at = datetime.now(UTC) - timedelta(hours=1)
            db.commit()
        with (
            patch.dict("os.environ", {"CURRICULUM_REFRESH_DAYS": "14"}),
            patch.object(
                service, "fetch_official_document", AsyncMock(return_value=self.pdf)
            ) as fetch,
            patch.object(
                service,
                "parse_document_in_worker",
                AsyncMock(
                    return_value={
                        "status": "parsed",
                        "assessments": self.rows,
                        "warnings": [],
                        "page_count": 3,
                    }
                ),
            ),
        ):
            first = await service.refresh_due_curricula(object())
            second = await service.refresh_due_curricula(object())
        self.assertEqual(first["checked"], 1)
        self.assertEqual(second["checked"], 0)
        self.assertEqual(fetch.await_count, 1)
        refreshed = await service.get_curriculum(doc["id"])
        delta = datetime.fromisoformat(refreshed["next_check_at"]) - datetime.fromisoformat(
            refreshed["last_attempt_at"]
        )
        self.assertEqual(delta.days, 14)

    async def test_active_refresh_lease_and_invalid_source_page_cannot_publish(self):
        doc = await self.imported()
        with self.assertRaises(ValueError):
            await service.publish_curriculum(
                doc["id"], doc["pending_hash"], [{**self.rows[0], "page": 4}]
            )
        with Session(self.engine) as db:
            stored = db.get(CurriculumDocument, doc["id"])
            stored.refresh_token = "other-worker"
            stored.refresh_started_at = datetime.now(UTC)
            db.commit()
        with self.assertRaises(service.CurriculumConflictError):
            await service.refresh_curriculum(doc["id"], uploaded_pdf=self.pdf)

    async def test_interrupted_import_stays_due_and_recovers_after_lease_expiry(self):
        doc = await self.published()
        with patch.object(
            service, "fetch_official_document", AsyncMock(side_effect=asyncio.CancelledError)
        ):
            with self.assertRaises(asyncio.CancelledError):
                await service.refresh_curriculum(doc["id"], object())
        interrupted = await service.get_curriculum(doc["id"])
        self.assertLessEqual(
            datetime.fromisoformat(interrupted["next_check_at"]), datetime.now(UTC)
        )
        self.assertTrue(interrupted["refreshing"])
        with Session(self.engine) as db:
            stored = db.get(CurriculumDocument, doc["id"])
            stored.refresh_started_at = datetime.now(UTC) - timedelta(minutes=6)
            db.commit()
        with (
            patch.object(service, "fetch_official_document", AsyncMock(return_value=self.pdf)),
            patch.object(
                service,
                "parse_document_in_worker",
                AsyncMock(
                    return_value={
                        "status": "parsed",
                        "assessments": self.rows,
                        "warnings": [],
                        "page_count": 3,
                    }
                ),
            ),
        ):
            result = await service.refresh_due_curricula(object())
        self.assertEqual(result["checked"], 1)
        recovered = await service.get_curriculum(doc["id"])
        self.assertFalse(recovered["refreshing"])
        self.assertEqual(recovered["published_assessments"], doc["published_assessments"])

    def test_overlapping_terms_duplicate_and_conflicting_assessments_rejected(self):
        groups = copy.deepcopy(self.groups)
        groups[0]["terms"][1]["start_date"] = "2027-01-31"
        with self.assertRaises(ValueError):
            service.validate_groups(groups)
        with self.assertRaises(ValueError):
            service.validate_assessments(self.rows + [self.rows[0]], 3)
        with self.assertRaises(ValueError):
            service.validate_assessments(
                self.rows + [{**self.rows[0], "semester": 1, "discipline_name": "Other"}], 3
            )
        for bad in (0, True, 17):
            with self.assertRaises(ValueError):
                service.validate_assessments([{**self.rows[0], "semester": bad}], 3)

    async def test_layout_change_requeues_cached_pdf_and_preserves_publication(self):
        doc = await self.published()
        with patch.object(service, "fetch_official_document", AsyncMock()) as fetch:
            changed = await service.set_scan_layout(doc["id"], "fa_compact_v1")
        fetch.assert_not_awaited()
        self.assertEqual(changed["scan_layout"], "fa_compact_v1")
        self.assertEqual(changed["processing_state"], "queued")
        self.assertEqual(changed["published_assessments"], doc["published_assessments"])
        self.assertEqual(
            await service.get_curriculum_pdf(doc["id"], doc["published_hash"]), self.pdf
        )
        self.assertEqual(changed["candidates"], [])
        with patch.object(
            service,
            "parse_document_in_worker",
            AsyncMock(
                return_value={
                    "status": "needs_review",
                    "assessments": [],
                    "warnings": [],
                    "page_count": 3,
                }
            ),
        ) as parse:
            self.assertEqual(
                await service.process_curriculum_queue(), {"processed": 1, "failed": 0}
            )
        parse.assert_awaited_once_with(self.pdf, scan_layout="fa_compact_v1")
        unchanged = await service.set_scan_layout(doc["id"], "fa_compact_v1")
        self.assertEqual(unchanged["processing_state"], "ready")
        self.assertEqual(unchanged["published_assessments"], doc["published_assessments"])

    async def test_layout_change_and_reset_during_worker_discards_original_output(self):
        doc = await service.create_curriculum(self.metadata)
        await service.refresh_curriculum(doc["id"], uploaded_pdf=self.pdf)

        async def change_while_running(_content, *, scan_layout):
            self.assertIsNone(scan_layout)
            await service.set_scan_layout(doc["id"], "fa_legacy_v1")
            # Returning to the captured value still invalidates the active job.
            await service.set_scan_layout(doc["id"], None)
            self.assertEqual(
                await service.process_curriculum_queue(), {"processed": 0, "failed": 0}
            )
            return {"assessments": self.rows, "warnings": [], "page_count": 3}

        with patch.object(service, "parse_document_in_worker", change_while_running):
            self.assertEqual(
                await service.process_curriculum_queue(), {"processed": 0, "failed": 0}
            )
        changed = await service.get_curriculum(doc["id"])
        self.assertEqual(changed["processing_state"], "queued")
        self.assertEqual(changed["candidates"], [])
        self.assertIsNone(changed["parser_version"])

    async def test_failure_from_prior_layout_does_not_fail_replacement_job(self):
        doc = await service.create_curriculum(self.metadata)
        await service.refresh_curriculum(doc["id"], uploaded_pdf=self.pdf)

        async def change_then_fail(_content, **_kwargs):
            await service.set_scan_layout(doc["id"], "fa_compact_v1")
            raise service.CurriculumProcessingError("parse_timeout")

        with patch.object(service, "parse_document_in_worker", change_then_fail):
            await service.process_curriculum_queue()
        changed = await service.get_curriculum(doc["id"])
        self.assertEqual(changed["processing_state"], "queued")
        self.assertIsNone(changed["processing_error"])

    async def test_layout_validation_and_setting_before_first_import(self):
        doc = await service.create_curriculum({**self.metadata, "scan_layout": "fa_legacy_v1"})
        self.assertEqual(doc["scan_layout"], "fa_legacy_v1")
        self.assertEqual(
            (await service.set_scan_layout(doc["id"], None))["processing_state"], "ready"
        )
        with self.assertRaises(ValueError):
            await service.set_scan_layout(doc["id"], "guessed-layout")
        with self.assertRaises(ValueError):
            await service.create_curriculum({**self.metadata, "scan_layout": "guessed-layout"})
        with self.assertRaises(service.CurriculumNotFoundError):
            await service.set_scan_layout(99999, "fa_legacy_v1")


class TestCurriculumMigration(unittest.TestCase):
    def test_upgrade_matches_models_and_downgrade_is_reversible(self):
        engine = create_engine("sqlite:///:memory:")
        self.addCleanup(engine.dispose)
        migration = runpy.run_path(
            str(
                Path(__file__).parents[1]
                / "alembic/versions/f9f0a1b2c3d4_add_curriculum_documents.py"
            )
        )
        processing = runpy.run_path(
            str(
                Path(__file__).parents[1] / "alembic/versions/fa0a1b2c3d4e_curriculum_processing.py"
            )
        )
        layout = runpy.run_path(
            str(
                Path(__file__).parents[1]
                / "alembic/versions/fb1b2c3d4e5f_curriculum_scan_layout.py"
            )
        )
        supplements = runpy.run_path(
            str(
                Path(__file__).parents[1]
                / "alembic/versions/fc2c3d4e5f60_curriculum_supplements.py"
            )
        )
        self.assertEqual(supplements["down_revision"], layout["revision"])
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration["upgrade"]()
                processing["upgrade"]()
                layout["upgrade"]()
                connection.exec_driver_sql(
                    "INSERT INTO curriculum_documents (id, title, source_url, program, profile, campus, "
                    "admission_year, study_form, pending_assessments, pending_warnings, "
                    "published_assessments, published_hash, published_pdf) "
                    "VALUES (1, 'Existing reviewed plan', 'https://www.fa.ru/upload/old.pdf', "
                    "'01.03.02', 'ML', 'Moscow', 2023, 'Full time', '[]', '[]', '[]', ?, ?)",
                    ("a" * 64, b"%PDF-existing reviewed snapshot"),
                )
                connection.exec_driver_sql(
                    "INSERT INTO curriculum_groups (group_id, document_id, group_name, terms) "
                    "VALUES ('existing-group', 1, 'Existing group', '[]')"
                )
                supplements["upgrade"]()
                inspector = inspect(connection)
                self.assertEqual(
                    set(inspector.get_table_names()), {"curriculum_documents", "curriculum_groups"}
                )
                for model in (CurriculumDocument, CurriculumGroup):
                    actual = {item["name"] for item in inspector.get_columns(model.__tablename__)}
                    self.assertEqual(actual, set(model.__table__.columns.keys()))
                foreign_key = next(
                    f
                    for f in inspector.get_foreign_keys("curriculum_documents")
                    if f["constrained_columns"] == ["parent_document_id"]
                )
                self.assertEqual(foreign_key["referred_table"], "curriculum_documents")
                self.assertEqual(foreign_key["options"]["ondelete"], "SET NULL")
                self.assertIn(
                    "ix_curriculum_documents_parent_document_id",
                    {i["name"] for i in inspector.get_indexes("curriculum_documents")},
                )
                stored = connection.exec_driver_sql(
                    "SELECT parent_document_id, published_hash, published_pdf FROM curriculum_documents WHERE id=1"
                ).one()
                self.assertEqual(
                    tuple(stored), (None, "a" * 64, b"%PDF-existing reviewed snapshot")
                )
                self.assertEqual(
                    connection.exec_driver_sql(
                        "SELECT document_id FROM curriculum_groups WHERE group_id='existing-group'"
                    ).scalar_one(),
                    1,
                )
                supplements["downgrade"]()
                self.assertEqual(
                    connection.exec_driver_sql(
                        "SELECT published_pdf FROM curriculum_documents WHERE id=1"
                    ).scalar_one(),
                    b"%PDF-existing reviewed snapshot",
                )
                layout["downgrade"]()
                processing["downgrade"]()
                migration["downgrade"]()
                self.assertEqual(inspect(connection).get_table_names(), [])
                migration["upgrade"]()
                self.assertEqual(len(inspect(connection).get_table_names()), 2)

    def test_sqlite_foreign_key_set_null_preserves_supplement_on_direct_delete(self):
        engine = create_engine("sqlite:///:memory:")
        self.addCleanup(engine.dispose)

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        CurriculumDocument.__table__.create(engine)
        metadata = dict(
            title="Plan",
            source_url="https://www.fa.ru/upload/example.pdf",
            program="01.03.02",
            profile="ML",
            campus="Moscow",
            admission_year=2023,
            study_form="Full time",
        )
        with Session(engine) as db, db.begin():
            root = CurriculumDocument(**metadata)
            db.add(root)
            db.flush()
            child = CurriculumDocument(**metadata, parent_document_id=root.id)
            db.add(child)
            db.flush()
            child_id = child.id
            db.execute(delete(CurriculumDocument).where(CurriculumDocument.id == root.id))
        with Session(engine) as db:
            self.assertIsNone(db.get(CurriculumDocument, child_id).parent_document_id)


if __name__ == "__main__":
    unittest.main()
