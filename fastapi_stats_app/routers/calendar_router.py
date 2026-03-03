from fastapi import APIRouter, Response, HTTPException
import logging
from datetime import date, timedelta
from shared_lib.database import get_user_id_by_calendar_secret, get_user_subscriptions
from shared_lib.redis_client import redis_client
from shared_lib.services.schedule_service import get_aggregated_schedule, generate_ical_from_aggregated_schedule

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/cal/{secret_token}.ics", summary="Публичная подписка на расписание (WebCal)")
async def get_webcal_schedule(secret_token: str):
    user_id = await get_user_id_by_calendar_secret(secret_token)
    if not user_id:
        # Google Calendar может кэшировать 404, поэтому лучше отвечать 404, если токен невалиден
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
        
        ical_data = generate_ical_from_aggregated_schedule(schedule)

        return Response(
            content=ical_data, 
            media_type="text/calendar; charset=utf-8",
            headers={
                # inline = "не скачивай, а показывай/обрабатывай"
                "Content-Disposition": "inline; filename=schedule.ics",
                # Запрет кэширования, чтобы календарь забирал свежее
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache"
            }
        )

    except Exception as e:
        logger.error(f"Error generating webcal for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Error")