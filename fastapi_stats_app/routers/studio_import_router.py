"""Preview an authenticated Studio ZIP and save it as a new project."""

import asyncio
import hashlib
import hmac
import time
from pathlib import PurePosixPath
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError
from python_multipart.exceptions import MultipartParseError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import ClientDisconnect

from shared_lib.database import get_db_session_dependency
from shared_lib.models import Project, ProjectFile
from shared_lib.schemas import StudioProjectSummary
from shared_lib.studio_archive import MAX_ARCHIVE_BYTES, ArchiveError, read_studio_zip

from ..auth import SECRET_KEY, get_current_user
from ..config import RATE_LIMIT_STUDIO_COMPILE
from ..rate_limit import enforce_rate_limit
from .studio_versions_router import enforce_studio_copy_quota, lock_studio_account

router = APIRouter(prefix="/studio", tags=["studio"])
PREVIEW_TTL = 600
MAX_REQUEST_BYTES = MAX_ARCHIVE_BYTES + 64 * 1024
_PREVIEW_KEY = hmac.digest(SECRET_KEY.encode("utf-8"), b"studio-zip-preview-v1", "sha256")


class ImportFields(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    project_type: Literal["latex", "markdown", "mermaid"]
    main: str = Field(min_length=1, max_length=255)
    preview_token: str = Field(min_length=1, max_length=120)


class _BodyTooLarge(MultiPartException):
    pass


async def _bounded_body(request):
    count = 0
    try:
        async for chunk in request.stream():
            count += len(chunk)
            if count > MAX_REQUEST_BYTES:
                raise _BodyTooLarge("Archive request size limit")
            yield chunk
    except ClientDisconnect as exc:
        raise MultiPartException("Incomplete archive request") from exc


async def _upload_parts(request, fields):
    """Parse multipart only after auth/rate limits and bound pre-spool request bytes."""
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "multipart/form-data"
    ):
        raise HTTPException(400, {"code": "archive_invalid"})
    try:
        if int(request.headers.get("content-length", "0")) > MAX_REQUEST_BYTES:
            raise _BodyTooLarge("Archive request size limit")
        parser = MultiPartParser(
            request.headers,
            _bounded_body(request),
            max_files=1,
            max_fields=len(fields),
            max_part_size=4096,
        )
        form = await parser.parse()
    except _BodyTooLarge:
        raise HTTPException(413, {"code": "archive_too_large"}) from None
    except (ValueError, MultiPartException, MultipartParseError):
        raise HTTPException(400, {"code": "archive_invalid"}) from None
    try:
        file = form.get("file")
        if (
            not isinstance(file, UploadFile)
            or set(form) != {*fields, "file"}
            or any(len(form.getlist(key)) != 1 for key in form)
        ):
            raise HTTPException(400, {"code": "archive_invalid"})
        data = await file.read(MAX_ARCHIVE_BYTES + 1)
        if len(data) > MAX_ARCHIVE_BYTES:
            raise HTTPException(413, {"code": "archive_too_large"})
        return data, file.filename, {key: form[key] for key in fields}
    finally:
        await form.close()


def _issue_preview(data, owner_id, expires):
    digest = hashlib.sha256(data).hexdigest()
    message = f"{owner_id}:{expires}:{digest}".encode("ascii")
    return f"{expires}.{hmac.digest(_PREVIEW_KEY, message, 'sha256').hex()}"


def _verify_preview(data, owner_id, token):
    now = int(time.time())
    expires, _, _ = token.partition(".")
    if (
        not expires.isascii()
        or not expires.isdecimal()
        or len(expires) > 12
        or not now <= int(expires) <= now + PREVIEW_TTL
        or not hmac.compare_digest(
            token.encode("utf-8"), _issue_preview(data, owner_id, int(expires)).encode("ascii")
        )
    ):
        raise HTTPException(409, {"code": "archive_preview_required"})


async def _parse(data):
    try:
        return await asyncio.to_thread(read_studio_zip, data)
    except ArchiveError as exc:
        code = str(exc)
        raise HTTPException(413 if code == "archive_too_large" else 400, {"code": code}) from None


@router.post("/projects/import/preview")
async def preview_archive(
    request: Request,
    response: Response,
    user: dict = Depends(get_current_user),
):
    await enforce_rate_limit(
        request,
        scope="studio_archive_preview",
        settings=RATE_LIMIT_STUDIO_COMPILE,
        current_user=user,
    )
    data, filename, _ = await _upload_parts(request, ())
    archive = await _parse(data)
    fallback = PurePosixPath((filename or "").replace("\\", "/")).stem.strip()
    fallback = "".join(char for char in fallback if ord(char) >= 32)[:160]
    response.headers["Cache-Control"] = "private, no-store"
    return {
        "name": archive.name or fallback,
        "type": archive.project_type,
        "main": archive.main,
        "manifest": archive.manifest,
        "byte_count": archive.byte_count,
        "files": [
            {"path": entry.path, "is_binary": isinstance(entry.data, bytes)}
            for entry in archive.files
        ],
        "preview_token": _issue_preview(data, user["id"], int(time.time()) + PREVIEW_TTL),
    }


@router.post("/projects/import", response_model=StudioProjectSummary, status_code=201)
async def import_archive(
    request: Request,
    db: AsyncSession = Depends(get_db_session_dependency),
    user: dict = Depends(get_current_user),
):
    await enforce_rate_limit(
        request,
        scope="studio_archive_import",
        settings=RATE_LIMIT_STUDIO_COMPILE,
        current_user=user,
    )
    data, _, fields = await _upload_parts(request, ImportFields.model_fields)
    try:
        inputs = ImportFields.model_validate(fields)
    except ValidationError:
        raise HTTPException(422, {"code": "archive_invalid"}) from None
    _verify_preview(data, user["id"], inputs.preview_token)
    archive = await _parse(data)
    name, project_type, main = inputs.name, inputs.project_type, inputs.main
    if not name.strip() or "\x00" in name:
        raise HTTPException(422, {"code": "archive_bad_name"})
    if main not in archive.main_candidates() or (
        archive.manifest
        and (project_type != archive.project_type or (archive.main and main != archive.main))
    ):
        raise HTTPException(400, {"code": "archive_no_main"})
    await lock_studio_account(db, user["id"])
    await enforce_studio_copy_quota(db, user["id"], archive.byte_count, error_code="archive_quota")
    project = Project(owner_id=user["id"], name=name.strip(), project_type=project_type)
    db.add(project)
    await db.flush()
    db.add_all(
        [
            ProjectFile(
                project_id=project.id,
                file_path=entry.path,
                is_main=entry.path == main,
                content_text=entry.data if isinstance(entry.data, str) else None,
                content_binary=entry.data if isinstance(entry.data, bytes) else None,
            )
            for entry in archive.files
        ]
    )
    await db.commit()
    return {"id": project.id, "name": project.name, "type": project.project_type}
