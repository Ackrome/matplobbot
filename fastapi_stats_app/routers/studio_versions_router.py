"""Private named Studio project versions and safe restoration into a new project."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, insert, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared_lib.database import get_db_session_dependency
from shared_lib.models import Project, ProjectFile, ProjectVersion, ProjectVersionFile, WebAccount
from shared_lib.render_assets import MAX_PROJECT_BYTES, MAX_PROJECT_FILES
from shared_lib.schemas import StudioProjectSummary

from ..auth import get_current_user
from ..config import RATE_LIMIT_STUDIO_COMPILE
from ..rate_limit import enforce_rate_limit
from .studio_router import ProjectRename, get_owned_project_or_404

router = APIRouter(prefix="/studio", tags=["studio"])
MAX_VERSIONS_PER_ACCOUNT = 20
MAX_VERSION_BYTES_PER_ACCOUNT = 100 * 1024 * 1024
MAX_RESTORE_PROJECTS = 100
MAX_RESTORE_BYTES_PER_ACCOUNT = 200 * 1024 * 1024
_FILE_FIELDS = ("file_path", "content_text", "content_binary", "is_main")


class VersionName(ProjectRename):
    name: str = Field(min_length=1, max_length=120)


class VersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    project_name: str
    project_type: str
    file_count: int
    byte_count: int
    created_at: datetime


class VersionFileSummary(BaseModel):
    path: str
    is_binary: bool
    is_main: bool


class VersionDetails(VersionSummary):
    files: list[VersionFileSummary]


async def lock_studio_account(db, owner_id):
    # All changes to an account's versions share this PostgreSQL lock, including
    # creates in different projects that consume the same account quota.
    account = await db.scalar(
        select(WebAccount.id).where(WebAccount.id == owner_id).with_for_update()
    )
    if account is None:
        raise HTTPException(401, "Account not found")


async def _lock_mutation(request, db, user, project_id):
    await enforce_rate_limit(
        request, scope="studio_version_write", settings=RATE_LIMIT_STUDIO_COMPILE, current_user=user
    )
    await lock_studio_account(db, user["id"])
    return await get_owned_project_or_404(db, project_id, user["id"], lock=True)


async def _version(db, project_id, version_id):
    version = await db.scalar(
        select(ProjectVersion).where(
            ProjectVersion.project_id == project_id, ProjectVersion.id == version_id
        )
    )
    if version is None:
        raise HTTPException(404, "Version not found")
    return version


def _project_bytes():
    return func.coalesce(
        func.sum(
            func.coalesce(func.octet_length(ProjectFile.content_text), 0)
            + func.coalesce(func.octet_length(ProjectFile.content_binary), 0)
        ),
        0,
    )


async def enforce_studio_copy_quota(db, owner_id, byte_count, *, error_code):
    """Check project-copy limits while the caller holds the account lock."""
    count, used = (
        await db.execute(
            select(func.count(func.distinct(Project.id)), _project_bytes())
            .select_from(Project)
            .outerjoin(ProjectFile, ProjectFile.project_id == Project.id)
            .where(Project.owner_id == owner_id)
        )
    ).one()
    if count >= MAX_RESTORE_PROJECTS or used + byte_count > MAX_RESTORE_BYTES_PER_ACCOUNT:
        raise HTTPException(409, {"code": error_code})


@router.get("/projects/{project_id}/versions", response_model=list[VersionSummary])
async def list_versions(
    project_id: int,
    response: Response,
    db: AsyncSession = Depends(get_db_session_dependency),
    user: dict = Depends(get_current_user),
):
    await get_owned_project_or_404(db, project_id, user["id"], include_cache=False)
    response.headers["Cache-Control"] = "private, no-store"
    return (
        await db.scalars(
            select(ProjectVersion)
            .where(ProjectVersion.project_id == project_id)
            .order_by(ProjectVersion.created_at.desc(), ProjectVersion.id.desc())
        )
    ).all()


@router.get("/projects/{project_id}/versions/{version_id}", response_model=VersionDetails)
async def get_version(
    project_id: int,
    version_id: int,
    response: Response,
    db: AsyncSession = Depends(get_db_session_dependency),
    user: dict = Depends(get_current_user),
):
    await get_owned_project_or_404(db, project_id, user["id"], include_cache=False)
    version = await _version(db, project_id, version_id)
    files = (
        await db.execute(
            select(
                ProjectVersionFile.file_path,
                ProjectVersionFile.content_binary.is_not(None),
                ProjectVersionFile.is_main,
            )
            .where(ProjectVersionFile.version_id == version_id)
            .order_by(ProjectVersionFile.file_path)
        )
    ).all()
    response.headers["Cache-Control"] = "private, no-store"
    return {
        **VersionSummary.model_validate(version).model_dump(),
        "files": [
            {"path": path, "is_binary": binary, "is_main": bool(main)}
            for path, binary, main in files
        ],
    }


@router.post("/projects/{project_id}/versions", response_model=VersionSummary, status_code=201)
async def create_version(
    project_id: int,
    data: VersionName,
    request: Request,
    db: AsyncSession = Depends(get_db_session_dependency),
    user: dict = Depends(get_current_user),
):
    project = await _lock_mutation(request, db, user, project_id)
    if (
        await db.scalar(
            select(ProjectVersion.id).where(
                ProjectVersion.project_id == project_id, ProjectVersion.name == data.name
            )
        )
        is not None
    ):
        raise HTTPException(409, {"code": "version_name_taken"})
    file_count, byte_count = (
        await db.execute(
            select(func.count(ProjectFile.id), _project_bytes()).where(
                ProjectFile.project_id == project_id
            )
        )
    ).one()
    if file_count > MAX_PROJECT_FILES or byte_count > MAX_PROJECT_BYTES:
        raise HTTPException(413, {"code": "version_project_too_large"})
    count, used = (
        await db.execute(
            select(
                func.count(ProjectVersion.id), func.coalesce(func.sum(ProjectVersion.byte_count), 0)
            )
            .join(Project, Project.id == ProjectVersion.project_id)
            .where(Project.owner_id == user["id"])
        )
    ).one()
    if count >= MAX_VERSIONS_PER_ACCOUNT or used + byte_count > MAX_VERSION_BYTES_PER_ACCOUNT:
        raise HTTPException(409, {"code": "version_quota"})
    version = ProjectVersion(
        project_id=project_id,
        name=data.name,
        project_name=project.name,
        project_type=project.project_type,
        file_count=file_count,
        byte_count=byte_count,
    )
    db.add(version)
    await db.flush()
    await db.execute(
        insert(ProjectVersionFile).from_select(
            ("version_id", *_FILE_FIELDS),
            select(literal(version.id), *(getattr(ProjectFile, key) for key in _FILE_FIELDS)).where(
                ProjectFile.project_id == project_id
            ),
        )
    )
    await db.commit()
    return version


@router.post(
    "/projects/{project_id}/versions/{version_id}/restore",
    response_model=StudioProjectSummary,
    status_code=201,
)
async def restore_version(
    project_id: int,
    version_id: int,
    data: ProjectRename,
    request: Request,
    db: AsyncSession = Depends(get_db_session_dependency),
    user: dict = Depends(get_current_user),
):
    await _lock_mutation(request, db, user, project_id)
    version = await _version(db, project_id, version_id)
    await enforce_studio_copy_quota(
        db, user["id"], version.byte_count, error_code="version_restore_quota"
    )
    copy = Project(owner_id=user["id"], name=data.name, project_type=version.project_type)
    db.add(copy)
    await db.flush()
    await db.execute(
        insert(ProjectFile).from_select(
            ("project_id", *_FILE_FIELDS),
            select(
                literal(copy.id), *(getattr(ProjectVersionFile, key) for key in _FILE_FIELDS)
            ).where(ProjectVersionFile.version_id == version_id),
        )
    )
    result = {"id": copy.id, "name": copy.name, "type": copy.project_type}
    await db.commit()
    return result


@router.delete("/projects/{project_id}/versions/{version_id}", status_code=204)
async def delete_version(
    project_id: int,
    version_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session_dependency),
    user: dict = Depends(get_current_user),
):
    await _lock_mutation(request, db, user, project_id)
    version = await _version(db, project_id, version_id)
    await db.delete(version)
    await db.commit()
    return Response(status_code=204)
