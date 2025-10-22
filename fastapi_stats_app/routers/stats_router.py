# c:/Users/ivant/Desktop/proj/matplobbot/fastapi_stats_app/routers/stats_router.py
from fastapi import APIRouter, HTTPException, Query
import asyncpg
import math
import logging
from ..db_utils import (
    get_db_connection_obj,
    get_leaderboard_data_from_db,
    get_popular_commands_data_from_db,
    get_popular_messages_data_from_db,
    get_action_types_distribution_from_db,
    get_activity_over_time_data_from_db,
    get_user_profile_data_from_db,
    get_users_for_action
)

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/health", summary="Health Check", description="Проверяет состояние сервиса и его зависимостей (например, подключение к БД).")
async def health_check():
    """
    Проверяет работоспособность сервиса. В данном случае, основная проверка -
    это возможность успешно выполнить запрос к базе данных.
    """
    try:
        async with get_db_connection_obj() as db:
            # Выполняем очень простой и быстрый запрос, чтобы проверить, что соединение с БД живо.
            await db.fetchval("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: Database connection error: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail={"status": "error", "database": "disconnected", "reason": str(e)})

@router.get("/users/{user_id}/profile", summary="Профиль пользователя и его действия", description="Возвращает детали профиля пользователя и полный список его действий.")
async def get_user_profile(
    user_id: int,
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(50, ge=1, le=200, description="Количество записей на странице"),
    sort_by: str = Query('timestamp', description="Поле для сортировки: id, action_type, action_details, timestamp"),
    sort_order: str = Query('desc', description="Порядок сортировки: asc или desc")
):
    try:
        async with get_db_connection_obj() as db:
            profile_data = await get_user_profile_data_from_db(
                db, user_id, page, page_size, sort_by, sort_order
            )
            if profile_data is None:
                raise HTTPException(status_code=404, detail="Пользователь не найден.")

            total_actions = profile_data["total_actions"]
            total_pages = math.ceil(total_actions / page_size)

            return {
                **profile_data,
                "pagination": {
                    "current_page": page,
                    "total_pages": total_pages,
                    "page_size": page_size,
                    "sort_by": sort_by,
                    "sort_order": sort_order
                }
            }
    except asyncpg.PostgresError as e:
        logger.error(f"Ошибка базы данных при получении профиля пользователя {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка базы данных (профиль пользователя): {e}")

@router.get("/stats/action_users", summary="Пользователи для действия", description="Возвращает список пользователей, совершивших определенное действие.")
async def get_action_users(
    action_type: str = Query(..., description="Тип действия ('command' или 'message')"),
    action_details: str = Query(..., description="Детали действия (текст команды или сообщения)"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(15, ge=1, le=100, description="Количество пользователей на странице"),
    sort_by: str = Query('full_name', description="Поле для сортировки: user_id, full_name, username"),
    sort_order: str = Query('asc', description="Порядок сортировки: asc или desc")
):
    try:
        async with get_db_connection_obj() as db:
            data = await get_users_for_action(db, action_type, action_details, page, page_size, sort_by, sort_order)
            total_users = data["total_users"]
            total_pages = math.ceil(total_users / page_size)
            return {
                "users": data["users"],
                "pagination": {
                    "current_page": page,
                    "total_pages": total_pages,
                    "page_size": page_size,
                    "sort_by": sort_by,
                    "sort_order": sort_order
                }
            }
    except asyncpg.PostgresError as e:
        logger.error(f"Ошибка базы данных при получении пользователей для действия: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка базы данных (пользователи для действия): {e}")