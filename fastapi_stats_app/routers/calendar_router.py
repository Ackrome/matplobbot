from fastapi import APIRouter, Response, HTTPException
import logging
from datetime import date, timedelta
from shared_lib.database import get_user_id_by_calendar_secret, get_user_subscriptions
from shared_lib.redis_client import redis_client
from shared_lib.services.schedule_service import get_aggregated_schedule, generate_ical_from_aggregated_schedule

router = APIRouter()
logger = logging.getLogger(__name__)

@router.api_route(
    "/cal/{secret_token}/basic.ics", 
    methods=["GET", "HEAD"], 
    summary="Публичная подписка на расписание (WebCal)"
)
@router.api_route(
    "/cal/{secret_token}.ics", 
    methods=["GET", "HEAD"], 
    summary="WebCal через расширение"
)
async def get_webcal_schedule(secret_token: str):
    clean_token = secret_token.replace(".ics", "")
    
    user_id = await get_user_id_by_calendar_secret(clean_token)
    if not user_id:
        raise HTTPException(status_code=404, detail="Calendar not found")

    try:
        subs, _ = await get_user_subscriptions(user_id, page=0, page_size=100)
        active_subs = [s for s in subs if s['is_active']]

        raw_filters = await redis_client.get_user_cache(user_id, "mysch_filters")
        filters = raw_filters or {'excluded_subs': [], 'excluded_types': []}

        today = date.today()
        start_date = today - timedelta(days=14) # Чуть больше истории
        end_date = today + timedelta(days=90)

        schedule = await get_aggregated_schedule(user_id, active_subs, start_date, end_date, filters)
        
        # Генерация строки (с правильными \r\n внутри)
        # Теперь эта функция возвращает bytes
        ical_bytes = generate_ical_from_aggregated_schedule(schedule)

        return Response(
            content=ical_bytes, 
            media_type="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": "inline; filename=schedule.ics",
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache"
            }
        )

    except Exception as e:
        logger.error(f"Error generating webcal for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Error")