"""Persist reviewed curriculum data; refresh candidates without replacing published facts."""

import hashlib
import logging
import os
import re
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer

from shared_lib.database import get_session
from shared_lib.models import CurriculumDocument, CurriculumGroup
from shared_lib.services.curriculum_documents import (
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENT_PAGES,
    fetch_official_document,
)
from shared_lib.services.curriculum_processing import (
    CurriculumProcessingError,
    current_parser_version,
    parse_document_in_worker,
    validate_scan_layout,
)

logger = logging.getLogger(__name__)
MAX_PDF_BYTES = MAX_DOCUMENT_BYTES
ASSESSMENT_KINDS = {"exam", "pass", "graded_pass", "coursework", "course_project"}
REFRESH_LEASE = timedelta(minutes=5)
PROCESSING_LEASE = timedelta(minutes=15)  # Always longer than the worker's hard 600-second maximum.
_SCOPE_FIELDS = ("program", "profile", "campus", "admission_year", "study_form")


class CurriculumNotFoundError(ValueError):
    """The requested document no longer exists."""


class CurriculumConflictError(ValueError):
    """A newer candidate or another group binding requires review."""


def refresh_days() -> int:
    """Default to weekly; an operator may select a fortnightly refresh."""
    return 14 if os.getenv("CURRICULUM_REFRESH_DAYS", "7").strip() == "14" else 7


def _utc(value):
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


def _iso(value):
    return _utc(value).isoformat() if value else None


def _name(value: str) -> str:
    # Whitespace/case equivalence only: fuzzy title matches must never become facts.
    return re.sub(r"\s+", " ", value).strip().casefold()


def _document_dict(document, groups, *, include_records=True):
    return {
        **{
            key: getattr(document, key)
            for key in (
                "id",
                "parent_document_id",
                "title",
                "source_url",
                "program",
                "profile",
                "campus",
                "admission_year",
                "study_form",
                "scan_layout",
                "pending_hash",
                "published_hash",
                "last_error",
            )
        },
        "status": document.pending_status
        if document.pending_hash
        else ("published" if document.published_hash else "empty"),
        "candidates": (document.pending_assessments or []) if include_records else [],
        "warnings": document.pending_warnings or [],
        "published_assessments": (document.published_assessments or []) if include_records else [],
        "page_count": document.source_page_count,
        "checked_at": _iso(document.checked_at),
        "last_attempt_at": _iso(document.last_attempt_at),
        "next_check_at": _iso(document.next_check_at),
        "published_at": _iso(document.published_at),
        "processing_state": document.processing_state,
        "processing_error": document.processing_error,
        "processing_started_at": _iso(document.processing_started_at),
        "parser_version": document.parser_version,
        "parse_method": document.parse_method,
        "engine_version": document.engine_version,
        "refresh_interval_days": refresh_days(),
        "refreshing": bool(
            document.refresh_token
            and document.refresh_started_at
            and _utc(document.refresh_started_at) + REFRESH_LEASE > datetime.now(UTC)
        ),
        "groups": [
            {"group_id": group.group_id, "group_name": group.group_name, "terms": group.terms}
            for group in groups
        ],
        "document_url": f"/api/curricula/{document.id}/document"
        if (document.pending_hash or document.published_hash)
        else None,
    }


async def list_curricula(document_id: int | None = None) -> list[dict]:
    async with get_session() as db:
        query = (
            select(CurriculumDocument)
            .options(defer(CurriculumDocument.source_pdf), defer(CurriculumDocument.published_pdf))
            .order_by(CurriculumDocument.id.desc())
        )
        if document_id is not None:
            query = query.where(CurriculumDocument.id == document_id)
        else:
            query = query.options(
                defer(CurriculumDocument.pending_assessments),
                defer(CurriculumDocument.published_assessments),
            )
        documents = list((await db.scalars(query)).all())
        groups = list((await db.scalars(select(CurriculumGroup))).all())
        return [
            _document_dict(
                doc,
                [group for group in groups if group.document_id == doc.id],
                include_records=document_id is not None,
            )
            for doc in documents
        ]


async def get_curriculum(document_id: int) -> dict:
    rows = await list_curricula(document_id)
    if not rows:
        raise CurriculumNotFoundError("Curriculum not found")
    return rows[0]


async def create_curriculum(metadata: dict) -> dict:
    validate_scan_layout(metadata.get("scan_layout"))
    parent_id = metadata.get("parent_document_id")
    if parent_id is not None and (type(parent_id) is not int or parent_id < 1):
        raise ValueError("Invalid parent curriculum identifier")
    async with get_session() as db, db.begin():
        if parent_id is not None:
            parent = await db.scalar(
                select(CurriculumDocument)
                .where(CurriculumDocument.id == parent_id)
                .options(
                    defer(CurriculumDocument.source_pdf), defer(CurriculumDocument.published_pdf)
                )
                .with_for_update()
            )
            if parent is None:
                raise CurriculumNotFoundError("Parent curriculum not found")
            if parent.parent_document_id is not None:
                raise ValueError("A supplement must belong directly to a root curriculum")
            if any(metadata.get(field) != getattr(parent, field) for field in _SCOPE_FIELDS):
                raise ValueError(
                    "Supplement programme, profile, campus, cohort and study form must match its parent"
                )
        document = CurriculumDocument(
            **metadata,
            pending_assessments=[],
            pending_warnings=[],
            published_assessments=[],
            next_check_at=datetime.now(UTC),
        )
        db.add(document)
        await db.flush()
        document_id = document.id
    return await get_curriculum(document_id)


async def delete_curriculum(document_id: int) -> None:
    """Remove the source and bindings, retaining supplements as unbound standalone sources."""
    async with get_session() as db, db.begin():
        document = await db.scalar(
            select(CurriculumDocument.id)
            .where(CurriculumDocument.id == document_id)
            .with_for_update()
        )
        if document is None:
            raise CurriculumNotFoundError("Curriculum not found")
        # Explicitly unlink as well as using ON DELETE SET NULL, including SQLite
        # callers that have not enabled foreign-key enforcement.
        await db.execute(
            update(CurriculumDocument)
            .where(CurriculumDocument.parent_document_id == document_id)
            .values(parent_document_id=None)
        )
        await db.execute(delete(CurriculumGroup).where(CurriculumGroup.document_id == document_id))
        await db.execute(delete(CurriculumDocument).where(CurriculumDocument.id == document_id))


async def refresh_curriculum(
    document_id: int,
    http_session=None,
    *,
    uploaded_pdf: bytes | None = None,
    only_if_due: bool = False,
) -> dict:
    """Fetch/store bytes and durably queue parsing; never execute OCR in an API request."""
    now = datetime.now(UTC)
    token = str(uuid.uuid4())
    async with get_session() as db, db.begin():
        document = await db.scalar(
            select(CurriculumDocument).where(CurriculumDocument.id == document_id).with_for_update()
        )
        if document is None:
            raise CurriculumNotFoundError("Curriculum not found")
        if only_if_due and document.next_check_at and _utc(document.next_check_at) > now:
            return {"skipped": True}
        if (
            document.refresh_token
            and document.refresh_started_at
            and _utc(document.refresh_started_at) + REFRESH_LEASE > now
        ):
            raise CurriculumConflictError("Document refresh is already running")
        document.refresh_token = token
        document.refresh_started_at = now
        document.last_attempt_at = now
        # Keep the claimed document due until a result is persisted. A killed
        # process must be retried after its lease expires, not one week later.
        document.next_check_at = now
        source_url = document.source_url

    try:
        data = (
            uploaded_pdf
            if uploaded_pdf is not None
            else await fetch_official_document(http_session, source_url)
        )
        if not data or len(data) > MAX_PDF_BYTES or not data.lstrip().startswith(b"%PDF-"):
            raise ValueError("Unsupported or oversized PDF")
        digest = hashlib.sha256(data).hexdigest()
    except Exception:
        # Upstream URLs, proxy credentials and response bodies never reach API errors.
        logger.warning("Curriculum import failed for document %s", document_id)
        async with get_session() as db, db.begin():
            document = await db.scalar(
                select(CurriculumDocument)
                .where(CurriculumDocument.id == document_id)
                .with_for_update()
            )
            if document and document.refresh_token == token:
                document.last_error = "import_failed"
                document.next_check_at = datetime.now(UTC) + timedelta(days=refresh_days())
                document.refresh_token = None
                document.refresh_started_at = None
        return await get_curriculum(document_id)

    async with get_session() as db, db.begin():
        document = await db.scalar(
            select(CurriculumDocument).where(CurriculumDocument.id == document_id).with_for_update()
        )
        if not document:
            raise CurriculumNotFoundError("Curriculum not found")
        if document.refresh_token != token:
            raise CurriculumConflictError("A newer import has replaced this refresh")
        document.checked_at = datetime.now(UTC)
        document.next_check_at = document.checked_at + timedelta(days=refresh_days())
        document.last_error = None
        document.refresh_token = None
        document.refresh_started_at = None
        document.source_pdf = data
        _queue_document(document, digest)
    return await get_curriculum(document_id)


def _queue_document(document, digest, *, force=False):
    unchanged = document.source_hash == digest
    document.source_hash = digest
    if not force and unchanged and document.processing_state in {"queued", "processing"}:
        return
    if (
        not force
        and digest == document.parsed_hash
        and document.parser_version == current_parser_version(document.scan_layout)
        and document.processing_state == "ready"
    ):
        return
    document.processing_state = "queued"
    document.processing_error = None
    # A replacement can queue while its prior bytes are still being processed.
    # Keep that active lease until the child exits, so another scheduler cannot
    # start a second CPU worker while the first still owns this slot.
    if not (
        document.processing_token
        and document.processing_started_at
        and _utc(document.processing_started_at) + PROCESSING_LEASE > datetime.now(UTC)
    ):
        document.processing_token = None
        document.processing_started_at = None
    if not unchanged:
        document.source_page_count = None
        document.parse_method = None
        document.engine_version = None
        document.pending_hash = None if digest == document.published_hash else digest
        document.pending_assessments = []
        document.pending_warnings = []
        document.pending_status = "needs_review" if document.pending_hash else None


async def reprocess_curriculum(document_id: int) -> dict:
    """Retry a cached PDF after a failure or parser/model upgrade, without downloading."""
    async with get_session() as db, db.begin():
        document = await db.scalar(
            select(CurriculumDocument).where(CurriculumDocument.id == document_id).with_for_update()
        )
        if not document:
            raise CurriculumNotFoundError("Curriculum not found")
        if not document.source_pdf:
            raise ValueError("Import a PDF before processing it")
        _queue_document(document, hashlib.sha256(document.source_pdf).hexdigest(), force=True)
    return await get_curriculum(document_id)


async def set_scan_layout(document_id: int, scan_layout: str | None) -> dict:
    """Choose control-column semantics explicitly and requeue cached bytes without replacing publication."""
    validate_scan_layout(scan_layout)
    async with get_session() as db, db.begin():
        document = await db.scalar(
            select(CurriculumDocument).where(CurriculumDocument.id == document_id).with_for_update()
        )
        if document is None:
            raise CurriculumNotFoundError("Curriculum not found")
        if document.scan_layout != scan_layout:
            document.scan_layout = scan_layout
            document.parser_version = None
            document.parsed_hash = None
            document.pending_assessments = []
            document.pending_warnings = []
            if document.source_pdf:
                digest = hashlib.sha256(document.source_pdf).hexdigest()
                _queue_document(document, digest, force=True)
                document.pending_hash = None if digest == document.published_hash else digest
                document.pending_status = "needs_review" if document.pending_hash else None
    return await get_curriculum(document_id)


async def process_curriculum_queue() -> dict:
    """Process at most one durable job per tick; reclaim abandoned leases on restart."""
    now, token = datetime.now(UTC), str(uuid.uuid4())
    async with get_session() as db, db.begin():
        # Lock the registry in a consistent order, serializing claimers even across
        # scheduler replicas. Re-query after the lock in READ COMMITTED isolation.
        await db.execute(
            select(CurriculumDocument.id).order_by(CurriculumDocument.id).with_for_update()
        )
        documents = list(
            (
                await db.scalars(
                    select(CurriculumDocument)
                    .options(
                        defer(CurriculumDocument.source_pdf),
                        defer(CurriculumDocument.published_pdf),
                        defer(CurriculumDocument.pending_assessments),
                        defer(CurriculumDocument.published_assessments),
                    )
                    .order_by(CurriculumDocument.id)
                )
            ).all()
        )
        if any(
            doc.processing_token
            and doc.processing_started_at
            and _utc(doc.processing_started_at) + PROCESSING_LEASE > now
            for doc in documents
        ):
            return {"processed": 0, "failed": 0}
        document = next(
            (
                doc
                for doc in documents
                if doc.source_hash
                and (
                    doc.processing_state in {"queued", "processing"}
                    or (
                        doc.processing_state == "ready"
                        and doc.parser_version != current_parser_version(doc.scan_layout)
                    )
                )
            ),
            None,
        )
        if document is None:
            return {"processed": 0, "failed": 0}
        document.processing_state = "processing"
        document.processing_token = token
        document.processing_started_at = now
        document.processing_error = None
        document_id = document.id
        data = await db.scalar(
            select(CurriculumDocument.source_pdf).where(CurriculumDocument.id == document_id)
        )
        if not data:
            document.processing_state = "error"
            document.processing_error = "invalid_pdf"
            document.processing_token = None
            document.processing_started_at = None
            return {"processed": 0, "failed": 1}
        digest = hashlib.sha256(data).hexdigest()
        document.source_hash = digest
        scan_layout = document.scan_layout
        version = current_parser_version(scan_layout)
    try:
        parsed = await parse_document_in_worker(data, scan_layout=scan_layout)
        page_count = parsed.get("page_count")
        if type(page_count) is not int or not 1 <= page_count <= MAX_DOCUMENT_PAGES:
            raise CurriculumProcessingError("invalid_pdf")
        if (
            not isinstance(parsed.get("assessments"), list)
            or len(parsed["assessments"]) > 5000
            or not isinstance(parsed.get("warnings"), list)
        ):
            raise CurriculumProcessingError("parse_failed")
    except Exception as exc:
        code = str(exc) if isinstance(exc, CurriculumProcessingError) else "parse_failed"
        if code not in {"parse_timeout", "parse_failed", "result_limit", "invalid_pdf"}:
            code = "parse_failed"
        async with get_session() as db, db.begin():
            document = await db.scalar(
                select(CurriculumDocument)
                .where(CurriculumDocument.id == document_id)
                .with_for_update()
            )
            if document and document.processing_token == token:
                replaced = (
                    document.source_hash != digest
                    or document.scan_layout != scan_layout
                    or document.processing_state != "processing"
                )
                document.processing_state = "queued" if replaced else "error"
                document.processing_error = None if replaced else code
                document.processing_token = None
                document.processing_started_at = None
        logger.warning("Curriculum processing failed for document %s: %s", document_id, code)
        return {"processed": 0, "failed": 1}
    async with get_session() as db, db.begin():
        document = await db.scalar(
            select(CurriculumDocument).where(CurriculumDocument.id == document_id).with_for_update()
        )
        if not document or document.processing_token != token:
            return {"processed": 0, "failed": 0}
        if (
            document.source_hash != digest
            or document.scan_layout != scan_layout
            or document.processing_state != "processing"
        ):
            document.processing_state = "queued"
            document.processing_token = None
            document.processing_started_at = None
            return {"processed": 0, "failed": 0}
        document.processing_state = "ready"
        document.processing_error = None
        document.processing_token = None
        document.processing_started_at = None
        document.parsed_hash = digest
        document.parser_version = version
        document.source_page_count = page_count
        document.parse_method = parsed.get("method", "text")
        document.engine_version = str(parsed.get("engine_version", ""))[:200]
        if digest == document.published_hash:
            # New engines must not silently undo a human correction of identical bytes.
            document.pending_hash = None
            document.pending_assessments = []
            document.pending_warnings = []
            document.pending_status = None
        else:
            document.pending_hash = digest
            document.pending_assessments = parsed["assessments"]
            document.pending_warnings = parsed["warnings"][:100]
            document.pending_status = parsed.get("status", "needs_review")
    return {"processed": 1, "failed": 0}


def validate_assessments(rows: list[dict], page_count: int) -> list[dict]:
    if not rows or len(rows) > 5000:
        raise ValueError("Publish between 1 and 5000 reviewed assessment records")
    cleaned, identities = [], set()
    for row in rows:
        item = {
            key: row.get(key)
            for key in (
                "discipline_code",
                "discipline_name",
                "semester",
                "kind",
                "page",
                "evidence",
            )
        }
        for key, maximum in (
            ("discipline_code", 100),
            ("discipline_name", 500),
            ("evidence", 2000),
        ):
            item[key] = str(item[key] or "").strip()
            if not item[key] or len(item[key]) > maximum:
                raise ValueError(f"Invalid {key}")
        if (
            type(item["semester"]) is not int
            or not 1 <= item["semester"] <= 16
            or item["kind"] not in ASSESSMENT_KINDS
        ):
            raise ValueError("Invalid assessment semester or kind")
        if type(item["page"]) is not int or not 1 <= item["page"] <= page_count:
            raise ValueError("Assessment page is outside the source PDF")
        identity = (item["discipline_code"], item["semester"], item["kind"])
        if identity in identities:
            raise ValueError("Duplicate discipline/semester/assessment record")
        identities.add(identity)
        cleaned.append(item)
    # One course code cannot silently change its title in different terms.
    names_by_code = {}
    for item in cleaned:
        previous = names_by_code.setdefault(item["discipline_code"], _name(item["discipline_name"]))
        if previous != _name(item["discipline_name"]):
            raise ValueError("One discipline code has conflicting titles")
    return sorted(cleaned, key=lambda row: (row["discipline_name"], row["semester"], row["kind"]))


async def publish_curriculum(document_id: int, expected_hash: str, assessments: list[dict]) -> dict:
    async with get_session() as db, db.begin():
        document = await db.scalar(
            select(CurriculumDocument).where(CurriculumDocument.id == document_id).with_for_update()
        )
        if not document:
            raise CurriculumNotFoundError("Curriculum not found")
        if document.processing_state in {"queued", "processing"}:
            raise CurriculumConflictError("Wait for document processing to finish")
        current_hash = document.pending_hash or document.published_hash
        if not current_hash or current_hash != expected_hash or not document.source_pdf:
            raise CurriculumConflictError("The document changed; reload and review the current PDF")
        rows = validate_assessments(assessments, document.source_page_count or 0)
        document.published_assessments = rows
        document.published_hash = current_hash
        document.published_pdf = document.source_pdf
        document.published_at = datetime.now(UTC)
        document.pending_hash = None
        document.pending_assessments = []
        document.pending_warnings = []
        document.pending_status = None
    return await get_curriculum(document_id)


def validate_groups(groups: list[dict]) -> list[dict]:
    if len(groups) > 100:
        raise ValueError("At most 100 groups per curriculum")
    result, seen = [], set()
    for group in groups:
        group_id = str(group.get("group_id", "")).strip()
        group_name = str(group.get("group_name", "")).strip()
        if not group_id or len(group_id) > 128 or re.search(r"[/\\?#\x00]", group_id):
            raise ValueError("Invalid group identifier")
        if not group_name or len(group_name) > 255 or group_id in seen:
            raise ValueError("Invalid or duplicate group")
        seen.add(group_id)
        terms, semesters = [], set()
        for term in group.get("terms", []):
            semester = term.get("semester")
            start, end = (
                date.fromisoformat(term["start_date"]),
                date.fromisoformat(term["end_date"]),
            )
            if type(semester) is not int or not 1 <= semester <= 16 or semester in semesters:
                raise ValueError("Invalid or duplicate semester")
            if end < start or (end - start).days > 400:
                raise ValueError("Invalid semester date range")
            semesters.add(semester)
            terms.append(
                {"semester": semester, "start_date": start.isoformat(), "end_date": end.isoformat()}
            )
        terms.sort(key=lambda term: term["start_date"])
        if not terms:
            raise ValueError("Specify at least one reviewed semester date range")
        for earlier, later in zip(terms, terms[1:]):
            if earlier["end_date"] >= later["start_date"]:
                raise ValueError("Semester date ranges overlap")
        result.append({"group_id": group_id, "group_name": group_name, "terms": terms})
    return result


async def bind_curriculum_groups(document_id: int, groups: list[dict]) -> dict:
    cleaned = validate_groups(groups)
    try:
        async with get_session() as db, db.begin():
            document = await db.scalar(
                select(CurriculumDocument)
                .where(CurriculumDocument.id == document_id)
                .with_for_update()
            )
            if not document:
                raise CurriculumNotFoundError("Curriculum not found")
            if document.parent_document_id is not None:
                raise ValueError(
                    "Bind groups to the root curriculum, not to a supplementary document"
                )
            ids = [row["group_id"] for row in cleaned]
            conflicting = (
                await db.scalar(
                    select(CurriculumGroup).where(
                        CurriculumGroup.group_id.in_(ids),
                        CurriculumGroup.document_id != document_id,
                    )
                )
                if ids
                else None
            )
            if conflicting:
                raise CurriculumConflictError("Group is already bound to another curriculum")
            await db.execute(
                delete(CurriculumGroup).where(CurriculumGroup.document_id == document_id)
            )
            for row in cleaned:
                db.add(CurriculumGroup(document_id=document_id, **row))
    except IntegrityError as exc:
        raise CurriculumConflictError("Group is already bound to another curriculum") from exc
    return await get_curriculum(document_id)


async def get_curriculum_pdf(document_id: int, published_hash: str | None = None) -> bytes:
    async with get_session() as db:
        document = await db.get(CurriculumDocument, document_id)
        if not document:
            raise CurriculumNotFoundError("Curriculum not found")
        if published_hash is not None:
            if published_hash != document.published_hash or not document.published_pdf:
                raise CurriculumNotFoundError("Reviewed document version not found")
            return document.published_pdf
        if not document.source_pdf:
            raise CurriculumNotFoundError("Document has not been imported")
        return document.source_pdf


async def lookup_curriculum(group_id: str, discipline: str, lesson_date: date) -> dict:
    result = {
        "status": "unmapped",
        "group_id": group_id,
        "program": None,
        "admission_year": None,
        "semester": None,
        "assessments": [],
        "checked_at": None,
        "stale": False,
    }
    async with get_session() as db:
        group = await db.get(CurriculumGroup, group_id)
        if not group:
            return result
        document = await db.get(
            CurriculumDocument,
            group.document_id,
            options=[defer(CurriculumDocument.source_pdf), defer(CurriculumDocument.published_pdf)],
        )
        if not document:
            return result
        if document.parent_document_id is not None:
            result.update(status="needs_review", reason="invalid_group_binding")
            return result
        result.update(
            {
                "program": document.program,
                "profile": document.profile,
                "campus": document.campus,
                "admission_year": document.admission_year,
                "study_form": document.study_form,
                "checked_at": _iso(document.checked_at),
                "source_title": document.title,
                "source_url": document.source_url,
                "review_pending": bool(document.pending_hash),
            }
        )
        result["stale"] = _source_stale(document)
        terms = [
            term
            for term in group.terms
            if term["start_date"] <= lesson_date.isoformat() <= term["end_date"]
        ]
        if len(terms) != 1:
            result["status"] = "unavailable"
            result["reason"] = "semester_unmapped"
            return result
        result["semester"] = terms[0]["semester"]
        if not document.published_hash:
            result["status"] = "needs_review" if document.pending_hash else "unavailable"
            return result
        supplements = list(
            (
                await db.scalars(
                    select(CurriculumDocument)
                    .where(
                        CurriculumDocument.parent_document_id == document.id,
                        *(
                            getattr(CurriculumDocument, field) == getattr(document, field)
                            for field in _SCOPE_FIELDS
                        ),
                    )
                    .options(
                        defer(CurriculumDocument.source_pdf),
                        defer(CurriculumDocument.published_pdf),
                    )
                    .order_by(CurriculumDocument.id)
                )
            ).all()
        )
        sources = [document, *supplements]
        course_name = _name(discipline)
        matched = [
            (source, row)
            for source in sources
            if source.published_hash
            for row in (source.published_assessments or [])
            if _name(row["discipline_name"]) == course_name
        ]
        identities = {(source.id, row["discipline_code"]) for source, row in matched}
        if len(identities) > 1:
            result["status"] = "needs_review"
            result["reason"] = "ambiguous_discipline"
            result["review_pending"] = True
            return result
        if not matched:
            awaiting_review = any(
                not source.published_hash
                and any(
                    _name(row.get("discipline_name", "")) == course_name
                    for row in (source.pending_assessments or [])
                )
                for source in supplements
            )
            result["status"] = "needs_review" if awaiting_review else "not_found"
            result["review_pending"] = result["review_pending"] or awaiting_review
            return result
        source = matched[0][0]
        result.update(
            source_title=source.title,
            source_url=source.source_url,
            checked_at=_iso(source.checked_at),
            stale=result["stale"] or _source_stale(source),
            review_pending=result["review_pending"] or bool(source.pending_hash),
        )
        result["status"] = "confirmed"
        result["assessments"] = [
            {
                **row,
                "source_url": source.source_url,
                "source_title": source.title,
                "source_document_id": source.id,
                "source_sha256": source.published_hash,
                "snapshot_url": f"/api/schedule/curriculum/documents/{source.id}/{source.published_hash}.pdf",
            }
            for source, row in matched
        ]
        return result


def _source_stale(document) -> bool:
    checked = _utc(document.checked_at)
    return bool(
        document.last_error
        or document.processing_error
        or document.pending_hash
        or not checked
        or checked + timedelta(days=refresh_days()) < datetime.now(UTC)
    )


async def refresh_due_curricula(http_session) -> dict:
    """Hourly scheduler tick; each registered document is fetched only when its persisted week is due."""
    now = datetime.now(UTC)
    async with get_session() as db:
        ids = list(
            (
                await db.scalars(
                    select(CurriculumDocument.id)
                    .where(
                        or_(
                            CurriculumDocument.next_check_at.is_(None),
                            CurriculumDocument.next_check_at <= now,
                        )
                    )
                    .order_by(CurriculumDocument.id)
                )
            ).all()
        )
    counts = {"checked": 0, "failed": 0, "skipped": 0}
    for document_id in ids:
        try:
            result = await refresh_curriculum(document_id, http_session, only_if_due=True)
            key = (
                "skipped"
                if result.get("skipped")
                else ("failed" if result.get("last_error") else "checked")
            )
            counts[key] += 1
        except (CurriculumConflictError, CurriculumNotFoundError):
            counts["skipped"] += 1
        except Exception:
            logger.exception("Curriculum refresh failed for document %s", document_id)
            counts["failed"] += 1
    logger.info("Curriculum refresh completed: %s", counts)
    return counts
