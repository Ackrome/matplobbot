"""Admin-only operational outcomes and privacy-minimal product aggregates."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared_lib.database import get_db_session_dependency
from shared_lib.models import CachedSchedule, ScheduleChangeDelivery
from shared_lib.operational_metrics import get_operational_snapshot
from shared_lib.product_metrics import get_product_snapshot

from ..auth import require_admin

router = APIRouter(prefix="/insights", tags=["stats"], dependencies=[Depends(require_admin)])


@router.get("/operations")
async def operational_insights(
    response: Response, db: AsyncSession = Depends(get_db_session_dependency)
):
    response.headers["Cache-Control"] = "no-store"
    snapshot = await get_operational_snapshot()
    counts = dict(
        (
            await db.execute(
                select(ScheduleChangeDelivery.status, func.count()).group_by(
                    ScheduleChangeDelivery.status
                )
            )
        ).all()
    )
    oldest = await db.scalar(
        select(func.min(ScheduleChangeDelivery.created_at)).where(
            ScheduleChangeDelivery.status.in_(["pending", "processing"])
        )
    )
    last_checked = await db.scalar(select(func.max(CachedSchedule.updated_at)))
    now = datetime.now(UTC)
    if oldest and oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=UTC)
    snapshot["deliveries"] = {
        "counts": counts,
        "oldest_pending_age_seconds": max(0, (now - oldest).total_seconds()) if oldest else None,
    }
    snapshot["schedule_last_checked_at"] = last_checked.isoformat() if last_checked else None
    snapshot["scope"] = "last schedule cache write is global, not freshness of every entity"
    return snapshot


@router.get("/product")
async def product_insights(
    response: Response,
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db_session_dependency),
):
    response.headers["Cache-Control"] = "no-store"
    return await get_product_snapshot(db, days)
