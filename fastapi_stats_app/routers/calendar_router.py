import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from shared_lib.database import (
    get_or_create_calendar_secret,
    get_user_id_by_calendar_secret,
    get_user_subscriptions,
    regenerate_calendar_secret,
)
from shared_lib.redis_client import redis_client
from shared_lib.schemas import CalendarSubscriptionResponse
from shared_lib.services.schedule_service import (
    generate_ical_from_aggregated_schedule,
    get_aggregated_schedule,
)

from ..auth import get_current_user
from ..config import PUBLIC_API_URL

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_calendar_base_url(request: Request) -> str:
    if PUBLIC_API_URL:
        return PUBLIC_API_URL
    return str(request.base_url).rstrip("/")


def _build_calendar_subscription_response(
    request: Request, secret: str
) -> CalendarSubscriptionResponse:
    http_url = f"{_get_calendar_base_url(request)}/api/cal/{secret}.ics"
    if http_url.startswith("https://"):
        webcal_url = http_url.replace("https://", "webcal://", 1)
    elif http_url.startswith("http://"):
        webcal_url = http_url.replace("http://", "webcal://", 1)
    else:
        webcal_url = http_url

    return CalendarSubscriptionResponse(
        enabled=True,
        http_url=http_url,
        webcal_url=webcal_url,
    )


@router.get(
    "/cal/subscription",
    response_model=CalendarSubscriptionResponse,
    summary="Get the authorized user's personal calendar subscription links",
)
async def get_calendar_subscription(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    telegram_id = current_user.get("telegram_id")
    if not telegram_id:
        return CalendarSubscriptionResponse(enabled=False)

    secret = await get_or_create_calendar_secret(telegram_id)
    return _build_calendar_subscription_response(request, secret)


@router.post(
    "/cal/subscription/reset",
    response_model=CalendarSubscriptionResponse,
    summary="Rotate the authorized user's calendar subscription link",
)
async def reset_calendar_subscription(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    telegram_id = current_user.get("telegram_id")
    if not telegram_id:
        raise HTTPException(
            status_code=400,
            detail="Calendar subscription is unavailable for this account",
        )

    secret = await regenerate_calendar_secret(telegram_id)
    return _build_calendar_subscription_response(request, secret)


@router.api_route(
    "/cal/{secret_token}/basic.ics",
    methods=["GET", "HEAD"],
    summary="Публичная подписка на расписание (WebCal)",
)
@router.api_route(
    "/cal/{secret_token}.ics", methods=["GET", "HEAD"], summary="WebCal через расширение"
)
async def get_webcal_schedule(secret_token: str):
    clean_token = secret_token.replace(".ics", "")

    user_id = await get_user_id_by_calendar_secret(clean_token)
    if not user_id:
        raise HTTPException(status_code=404, detail="Calendar not found")

    try:
        subs, _ = await get_user_subscriptions(user_id, page=0, page_size=100)
        active_subs = [s for s in subs if s["is_active"]]

        raw_filters = await redis_client.get_user_cache(user_id, "mysch_filters")
        filters = raw_filters or {"excluded_subs": [], "excluded_types": []}

        today = date.today()
        start_date = today - timedelta(days=14)  # Чуть больше истории
        end_date = today + timedelta(days=90)

        schedule = await get_aggregated_schedule(
            user_id, active_subs, start_date, end_date, filters
        )

        # Генерация строки (с правильными \r\n внутри)
        # Теперь эта функция возвращает bytes
        ical_bytes = generate_ical_from_aggregated_schedule(schedule)

        return Response(
            content=ical_bytes,
            media_type="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": "inline; filename=schedule.ics",
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )

    except Exception as e:
        logger.error(f"Error generating webcal for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Error")
