"""Bounded, authenticated UX timings without document, query or URL payloads."""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from shared_lib.product_metrics import record_product_event

from ..auth import get_current_user
from ..config import RateLimitSettings
from ..rate_limit import enforce_rate_limit

router = APIRouter(prefix="/ux", tags=["UX outcomes"])


class JourneyEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    journey: Literal["schedule_first", "studio_first", "calendar_connected", "error_recovered"]
    duration_ms: int = Field(ge=0, le=3_600_000)


@router.post("/events", status_code=202)
async def record_journey(
    data: JourneyEvent, request: Request, user: dict = Depends(get_current_user)
):
    await enforce_rate_limit(
        request,
        scope="ux_events",
        settings=RateLimitSettings(limit=30, window_seconds=60),
        current_user=user,
    )
    await record_product_event(
        "ux_" + data.journey, web_account_id=user["id"], duration_ms=data.duration_ms
    )
    return {"status": "accepted"}
