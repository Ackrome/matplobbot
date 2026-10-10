"""Public minimal teacher-rating aggregates with the existing client limiter."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from shared_lib.services.teacher_ratings import TeacherRatingsService

from ..config import RATE_LIMIT_SCHEDULE_SEARCH
from ..rate_limit import enforce_rate_limit

router = APIRouter(prefix="/schedule", tags=["teacher ratings"])


class TeacherRatingProfileResponse(BaseModel):
    name: str
    url: str
    department: str | None = None
    rating_percent: float | None = Field(default=None, ge=0, le=100)
    vote_count: int | None = Field(default=None, ge=0, le=2_147_483_647)
    review_count: int | None = Field(default=None, ge=0, le=2_147_483_647)


class TeacherRatingResponse(BaseModel):
    query_name: str
    status: Literal["matched", "not_found", "ambiguous", "unsupported", "unavailable"]
    profile: TeacherRatingProfileResponse | None = None
    checked_at: datetime | None = None
    stale: bool


def get_teacher_ratings_service(request: Request) -> TeacherRatingsService:
    service = getattr(request.app.state, "teacher_ratings_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Teacher rating service is unavailable")
    return service


@router.get("/teacher-ratings", response_model=TeacherRatingResponse)
async def get_teacher_rating(
    request: Request,
    name: str = Query(min_length=1, max_length=200),
    service: TeacherRatingsService = Depends(get_teacher_ratings_service),
):
    await enforce_rate_limit(request, scope="teacher_ratings", settings=RATE_LIMIT_SCHEDULE_SEARCH)
    return await service.get(name)
