"""Public bounded schedule comparison API, sharing normal schedule refresh limits."""

from datetime import date, time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from shared_lib.services.calendar_sync_state import normalize_timezone
from shared_lib.services.schedule_planning import load_schedule_plan, validate_window
from shared_lib.services.university_api import create_ruz_api_client

from ..config import RATE_LIMIT_SCHEDULE_DATA, SCHEDULE_INTERACTIVE_UPSTREAM_TIMEOUT_SECONDS
from ..rate_limit import enforce_rate_limit
from .schedule_router import get_shared_http_session

router = APIRouter(prefix="/schedule", tags=["schedule planning"])


class PlanningEntity(BaseModel):
    entity_type: Literal["group", "person", "auditorium"]
    entity_id: str = Field(min_length=1, max_length=128)
    entity_name: str | None = Field(default=None, max_length=255)
    selected_modules: list[str] | None = Field(default=None, max_length=100)
    lesson_mode: Literal["all", "exams_only"] = "all"

    @field_validator("entity_id")
    @classmethod
    def valid_identifier(cls, value):
        if not value.strip() or any(char in value for char in "/\\?#\x00"):
            raise ValueError("Invalid schedule identifier")
        return value.strip()


class PlanningRequest(BaseModel):
    entities: list[PlanningEntity] = Field(min_length=1, max_length=6)
    start_date: date
    end_date: date
    timezone: str = "Europe/Moscow"
    day_start: time = time(8)
    day_end: time = time(22)
    min_free_minutes: int = Field(default=30, ge=5, le=720)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        normalized = normalize_timezone(value)
        if normalized == "Europe/Moscow" and value != "Europe/Moscow":
            raise ValueError("Use a supported calendar timezone")
        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Timezone is unavailable") from exc
        return normalized

    @model_validator(mode="after")
    def bounded_window(self):
        validate_window(
            self.start_date, self.end_date, self.day_start, self.day_end, self.min_free_minutes
        )
        return self


@router.post("/plan")
async def plan_schedules(
    body: PlanningRequest, request: Request, http_session=Depends(get_shared_http_session)
):
    await enforce_rate_limit(request, scope="schedule_plan", settings=RATE_LIMIT_SCHEDULE_DATA)
    client = create_ruz_api_client(
        http_session,
        max_retries=1,
        request_timeout_seconds=SCHEDULE_INTERACTIVE_UPSTREAM_TIMEOUT_SECONDS,
    )
    try:
        return await load_schedule_plan(
            client,
            [entity.model_dump() for entity in body.entities],
            start_date=body.start_date,
            end_date=body.end_date,
            timezone=body.timezone,
            day_start=body.day_start,
            day_end=body.day_end,
            min_free_minutes=body.min_free_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
