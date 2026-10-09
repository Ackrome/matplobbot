"""Public cached assessment lookup and administrator-reviewed official PDF imports."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared_lib.services import curriculum_service as service
from shared_lib.services.curriculum_documents import validate_official_document_url

from ..auth import require_admin
from ..config import RATE_LIMIT_SCHEDULE_DATA
from ..rate_limit import enforce_rate_limit
from .schedule_router import get_shared_http_session

router = APIRouter(tags=["curriculum"])


class CurriculumCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=500)
    source_url: str = Field(min_length=1, max_length=2048)
    program: str = Field(min_length=1, max_length=500)
    profile: str = Field(min_length=1, max_length=500)
    campus: str = Field(min_length=1, max_length=255)
    admission_year: int = Field(ge=2000, le=2100)
    study_form: str = Field(min_length=1, max_length=100)
    scan_layout: Literal["fa_legacy_v1", "fa_compact_v1"] | None = None
    parent_document_id: int | None = Field(default=None, ge=1, strict=True)

    @field_validator("source_url")
    @classmethod
    def official_source(cls, value):
        return validate_official_document_url(value)


class ReviewedAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    discipline_code: str = Field(min_length=1, max_length=100)
    discipline_name: str = Field(min_length=1, max_length=500)
    semester: int = Field(ge=1, le=16, strict=True)
    kind: str = Field(pattern=r"^(exam|pass|graded_pass|coursework|course_project)$")
    page: int = Field(ge=1, strict=True)
    evidence: str = Field(min_length=1, max_length=2000)


class CurriculumPublish(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessments: list[ReviewedAssessment] = Field(min_length=1, max_length=5000)


class CurriculumTerm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semester: int = Field(ge=1, le=16, strict=True)
    start_date: date
    end_date: date


class CurriculumGroupInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    group_id: str = Field(min_length=1, max_length=128)
    group_name: str = Field(min_length=1, max_length=255)
    terms: list[CurriculumTerm] = Field(min_length=1, max_length=16)


class CurriculumGroups(BaseModel):
    model_config = ConfigDict(extra="forbid")

    groups: list[CurriculumGroupInput] = Field(max_length=100)


class CurriculumScanLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_layout: Literal["fa_legacy_v1", "fa_compact_v1"] | None


async def _result(awaitable):
    try:
        return await awaitable
    except service.CurriculumNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except service.CurriculumConflictError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@router.get("/schedule/curriculum")
async def get_course_assessments(
    request: Request,
    group_id: str = Query(min_length=1, max_length=128),
    discipline: str = Query(min_length=1, max_length=500),
    lesson_date: date = Query(),
):
    await enforce_rate_limit(request, scope="curriculum_lookup", settings=RATE_LIMIT_SCHEDULE_DATA)
    return await service.lookup_curriculum(group_id.strip(), discipline.strip(), lesson_date)


@router.get("/schedule/curriculum/documents/{document_id}/{published_hash}.pdf")
async def reviewed_document(request: Request, document_id: int, published_hash: str):
    await enforce_rate_limit(
        request, scope="curriculum_document", settings=RATE_LIMIT_SCHEDULE_DATA
    )
    data = await _result(service.get_curriculum_pdf(document_id, published_hash))
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="curriculum-{document_id}.pdf"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=3600, immutable",
        },
    )


@router.get("/curricula", dependencies=[Depends(require_admin)])
async def curricula_list():
    return await service.list_curricula()


@router.post("/curricula", dependencies=[Depends(require_admin)], status_code=201)
async def curricula_create(body: CurriculumCreate):
    return await _result(service.create_curriculum(body.model_dump()))


@router.get("/curricula/{document_id}", dependencies=[Depends(require_admin)])
async def curricula_detail(document_id: int):
    return await _result(service.get_curriculum(document_id))


@router.delete("/curricula/{document_id}", dependencies=[Depends(require_admin)], status_code=204)
async def curricula_delete(document_id: int):
    await _result(service.delete_curriculum(document_id))
    return Response(status_code=204)


@router.post("/curricula/{document_id}/refresh", dependencies=[Depends(require_admin)])
async def curricula_refresh(document_id: int, http_session=Depends(get_shared_http_session)):
    return await _result(service.refresh_curriculum(document_id, http_session))


@router.post("/curricula/{document_id}/reprocess", dependencies=[Depends(require_admin)])
async def curricula_reprocess(document_id: int):
    return await _result(service.reprocess_curriculum(document_id))


@router.put("/curricula/{document_id}/scan-layout", dependencies=[Depends(require_admin)])
async def curricula_scan_layout(document_id: int, body: CurriculumScanLayout):
    return await _result(service.set_scan_layout(document_id, body.scan_layout))


@router.put("/curricula/{document_id}/document", dependencies=[Depends(require_admin)])
async def curricula_upload(document_id: int, request: Request):
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/pdf":
        raise HTTPException(415, detail="Upload a PDF with application/pdf content type")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > service.MAX_PDF_BYTES:
            raise HTTPException(413, detail="PDF exceeds the 20 MiB limit")
    if not data.lstrip().startswith(b"%PDF-"):
        raise HTTPException(422, detail="A valid PDF is required")
    return await _result(service.refresh_curriculum(document_id, uploaded_pdf=bytes(data)))


@router.get("/curricula/{document_id}/document", dependencies=[Depends(require_admin)])
async def curricula_document(document_id: int):
    data = await _result(service.get_curriculum_pdf(document_id))
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="curriculum-review-{document_id}.pdf"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.post("/curricula/{document_id}/publish", dependencies=[Depends(require_admin)])
async def curricula_publish(document_id: int, body: CurriculumPublish):
    return await _result(
        service.publish_curriculum(
            document_id, body.expected_hash, [row.model_dump() for row in body.assessments]
        )
    )


@router.put("/curricula/{document_id}/groups", dependencies=[Depends(require_admin)])
async def curricula_groups(document_id: int, body: CurriculumGroups):
    return await _result(
        service.bind_curriculum_groups(
            document_id, [group.model_dump(mode="json") for group in body.groups]
        )
    )
