"""Owner-scoped, resumable Studio compiles backed by existing Celery results."""

import asyncio
import base64
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared_lib.celery_app import app as celery_app
from shared_lib.celery_app import dispatch_traced_task
from shared_lib.database import get_db_session_dependency
from shared_lib.models import Project, ProjectFile
from shared_lib.product_metrics import record_product_event
from shared_lib.redis_client import redis_client
from shared_lib.studio_process import CANCEL_PREFIX
from shared_lib.tasks import (
    compile_full_latex_task,
    compile_project_task,
    render_mermaid,
    render_pdf_task,
)

from ..auth import get_current_user
from ..config import RATE_LIMIT_STUDIO_COMPILE
from ..rate_limit import enforce_rate_limit
from .studio_router import get_owned_project_or_404

router = APIRouter(prefix="/studio", tags=["studio"])
logger = logging.getLogger(__name__)
JOB_TTL_SECONDS = 86400
JOB_PREFIX = "mpb:studio-job:"


class StudioJobRequest(BaseModel):
    type: Literal["latex", "markdown", "mermaid"]
    content: str = Field(min_length=1, max_length=2_000_000)


async def _enqueue(
    task,
    args: tuple,
    current_user: dict,
    project_id: int | None = None,
    source_fingerprint: str | None = None,
):
    job_id = str(uuid4())
    now = datetime.now(UTC)
    metadata = {
        "job_id": job_id,
        "owner_id": current_user["id"],
        "project_id": project_id,
        "source_fingerprint": source_fingerprint,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=JOB_TTL_SECONDS)).isoformat(),
    }
    try:
        # Persist access control before sending work. Do not dispatch if storage is unavailable.
        async with asyncio.timeout(5):
            await redis_client.client.set(
                JOB_PREFIX + job_id, json.dumps(metadata), ex=JOB_TTL_SECONDS
            )
        await asyncio.to_thread(
            dispatch_traced_task, task, *args, _task_id=job_id, studio_job_id=job_id
        )
    except Exception as exc:
        logger.warning("Studio job publication failed (%s)", type(exc).__name__)
        raise HTTPException(503, "Compilation queue unavailable. Please retry.") from exc
    await record_product_event(
        "studio_started", web_account_id=current_user["id"], dedupe_key=f"studio-start:{job_id}"
    )
    return {
        "job_id": job_id,
        "status": "queued",
        "expires_at": metadata["expires_at"],
        "created_at": metadata["created_at"],
        "source_fingerprint": source_fingerprint,
    }


def _project_snapshot(files):
    payload, main_file = [], None
    for file in sorted(files, key=lambda item: item.file_path):
        if file.is_main:
            main_file = file.file_path
        payload.append(
            {
                "path": file.file_path,
                **(
                    {"binary": base64.b64encode(file.content_binary).decode("ascii")}
                    if file.content_binary is not None
                    else {"text": file.content_text or ""}
                ),
            }
        )
    fingerprint = hashlib.sha256(
        json.dumps([payload, main_file], sort_keys=True).encode("utf-8")
    ).hexdigest()
    return payload, main_file, fingerprint


async def _save_build_cache(db, metadata, encoded_cache):
    """Reuse artifacts only when the completed job still matches the saved source."""
    if not metadata.get("project_id") or not metadata.get("source_fingerprint"):
        return
    try:
        files = (
            (
                await db.execute(
                    select(ProjectFile).where(ProjectFile.project_id == metadata["project_id"])
                )
            )
            .scalars()
            .all()
        )
        if _project_snapshot(files)[2] != metadata["source_fingerprint"]:
            return
        cache = base64.b64decode(encoded_cache, validate=True)
        await db.execute(
            update(Project)
            .where(Project.id == metadata["project_id"], Project.owner_id == metadata["owner_id"])
            .values(build_cache=cache)
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("Studio build cache persistence failed (%s)", type(exc).__name__)


@router.post("/jobs", status_code=202, summary="Queue a resumable snippet compile")
async def create_snippet_job(
    data: StudioJobRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    await enforce_rate_limit(
        request,
        scope="studio_compile",
        settings=RATE_LIMIT_STUDIO_COMPILE,
        current_user=current_user,
    )
    args: tuple
    if data.type == "latex":
        task, args = compile_full_latex_task, (data.content,)
    elif data.type == "markdown":
        task, args = (
            render_pdf_task,
            (
                data.content,
                "Document",
                current_user.get("username") or "",
                "Today",
            ),
        )
    else:
        task, args = render_mermaid, (data.content,)
    return await _enqueue(task, args, current_user)


@router.post(
    "/projects/{project_id}/jobs", status_code=202, summary="Queue a saved project snapshot"
)
async def create_project_job(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    await enforce_rate_limit(
        request,
        scope="studio_compile",
        settings=RATE_LIMIT_STUDIO_COMPILE,
        current_user=current_user,
    )
    project = await get_owned_project_or_404(db, project_id, current_user["id"])
    files = (
        (await db.execute(select(ProjectFile).where(ProjectFile.project_id == project_id)))
        .scalars()
        .all()
    )
    if not files:
        raise HTTPException(400, "Project is empty")
    payload, main_file, fingerprint = _project_snapshot(files)
    if not main_file:
        raise HTTPException(400, "Project has no main file")
    if project.project_type in {"markdown", "mermaid"}:
        content = next(item.get("text") for item in payload if item["path"] == main_file)
        if not content:
            raise HTTPException(400, "Main file must contain text")
        task, args = (
            (render_pdf_task, (content, project.name, current_user.get("username") or "", "Today"))
            if project.project_type == "markdown"
            else (render_mermaid, (content,))
        )
        return await _enqueue(task, args, current_user, project_id, fingerprint)
    cache = base64.b64encode(project.build_cache).decode("ascii") if project.build_cache else None
    return await _enqueue(
        compile_project_task, (payload, main_file, cache), current_user, project_id, fingerprint
    )


def _task_status(job_id: str) -> tuple[str, dict | None]:
    result = celery_app.AsyncResult(job_id)
    state = result.state
    if state in {"PENDING", "RECEIVED", "RETRY"}:
        return "queued", None
    if state == "STARTED":
        return "running", None
    if state == "SUCCESS":
        payload = result.result
        if isinstance(payload, dict):
            if payload.get("status") == "cancelled":
                return "cancelled", None
            return "error" if payload.get("status") == "error" else "success", payload
        return "error", {"error": "Compilation returned an invalid result"}
    if state == "REVOKED":
        return "cancelled", None
    if state == "FAILURE":
        # Exception values can contain internal paths or credentials: do not expose them.
        return "error", {"error": "Compilation failed. Please retry or check the source."}
    return "running", None


@router.post("/jobs/{job_id}/cancel", status_code=202)
async def cancel_studio_job(
    job_id: UUID,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    """Request cooperative cancellation of this job's compiler process group."""
    response.headers["Cache-Control"] = "no-store"
    try:
        async with asyncio.timeout(5):
            raw = await redis_client.client.get(JOB_PREFIX + str(job_id))
        metadata = json.loads(raw) if raw else None
    except Exception as exc:
        raise HTTPException(503, "Job storage unavailable") from exc
    if not metadata or metadata.get("owner_id") != current_user["id"]:
        raise HTTPException(404, "Job not found or expired")
    try:
        status, _ = await asyncio.to_thread(_task_status, str(job_id))
        if status in {"success", "error", "cancelled"}:
            return {"job_id": str(job_id), "status": status}
        async with asyncio.timeout(5):
            await redis_client.client.set(CANCEL_PREFIX + str(job_id), "1", ex=JOB_TTL_SECONDS)
            metadata["cancel_requested"] = True
            await redis_client.client.set(
                JOB_PREFIX + str(job_id), json.dumps(metadata), xx=True, keepttl=True
            )
    except Exception as exc:
        raise HTTPException(
            503, "Cancellation could not be confirmed. Check the job again."
        ) from exc
    return {"job_id": str(job_id), "status": "cancelling"}


@router.get("/jobs/{job_id}", summary="Resume or retrieve an owned compile result")
async def get_studio_job(
    job_id: UUID,
    response: Response,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        async with asyncio.timeout(5):
            raw = await redis_client.client.get(JOB_PREFIX + str(job_id))
        metadata = json.loads(raw) if raw else None
    except Exception as exc:
        raise HTTPException(503, "Job storage unavailable. Please retry.") from exc
    if not metadata or metadata.get("owner_id") != current_user["id"]:
        raise HTTPException(404, "Job not found or expired")
    try:
        status, result = await asyncio.to_thread(_task_status, str(job_id))
    except Exception as exc:
        raise HTTPException(503, "Job status unavailable. Please retry.") from exc
    body = {"job_id": str(job_id), "status": status, "expires_at": metadata["expires_at"]}
    body["source_fingerprint"] = metadata.get("source_fingerprint")
    body["created_at"] = metadata.get("created_at")
    if metadata.get("cancel_requested") and status in {"queued", "running"}:
        body["status"] = "cancelling"
    if result is not None:
        if result.get("build_cache"):
            await _save_build_cache(db, metadata, result["build_cache"])
        # Cache remains internal; never return it in the public job representation.
        result = {key: value for key, value in result.items() if key != "build_cache"}
        body["result"] = result
        if status == "error":
            body["error"] = result.get("error", "Compilation failed")
        # A DB uniqueness key makes repeated polls/reloads exactly one analytics event.
        await record_product_event(
            "studio_succeeded" if status == "success" else "studio_failed",
            web_account_id=current_user["id"],
            dedupe_key=f"studio-result:{job_id}",
        )
    return body
