# fastapi_stats_app/routers/stats_router.py
from fastapi import APIRouter, HTTPException, Query, status
import asyncpg
import math
import logging
from typing import Any

from shared_lib.database import (
    get_db_connection_obj,
    get_user_profile_data_from_db,
    get_users_for_action,
    get_all_user_actions
)
from shared_lib.redis_client import redis_client
from shared_lib.schemas import (
    UserProfileResponse, 
    ActionUsersResponse, 
    ExportActionsResponse
)

router = APIRouter()
logger = logging.getLogger(__name__)

# TTL кэша в секундах (5 минут)
CACHE_TTL = 300

@router.get(
    "/health",
    summary="Health Check",
    description="Проверяет доступность сервиса и подключение к базе данных.",
    response_model=dict[str, str],
    status_code=status.HTTP_200_OK
)
async def health_check() -> dict[str, str]:
    """
    Легковесная проверка здоровья сервиса.
    """
    try:
        async with get_db_connection_obj() as db:
            await db.fetchval("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "error", "database": "disconnected", "reason": str(e)}
        )

@router.get(
    "/users/{user_id}/profile",
    summary="Профиль пользователя",
    description="Возвращает детальную информацию о пользователе и историю его действий с пагинацией.",
    response_model=UserProfileResponse
)
async def get_user_profile(
    user_id: int,
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(50, ge=1, le=200, description="Размер страницы"),
    sort_by: str = Query('timestamp', description="Поле сортировки (id, action_type, action_details, timestamp)"),
    sort_order: str = Query('desc', description="Порядок сортировки (asc, desc)")
) -> Any:
    # 1. Проверяем кэш
    cache_key = f"user_profile:{user_id}:p{page}:s{page_size}:{sort_by}:{sort_order}"
    try:
        cached_data = await redis_client.get_cache(cache_key)
        if cached_data:
            logger.info(f"Cache hit for user profile: {cache_key}")
            # Возвращаем dict, FastAPI сам провалидирует его через UserProfileResponse
            return cached_data
    except Exception as e:
        logger.warning(f"Redis cache error: {e}")

    # 2. Запрашиваем БД
    try:
        async with get_db_connection_obj() as db:
            profile_data = await get_user_profile_data_from_db(
                db, user_id, page, page_size, sort_by, sort_order
            )
            
            if profile_data is None:
                raise HTTPException(status_code=404, detail="Пользователь не найден.")

            # Расчет пагинации
            total_actions = profile_data["total_actions"]
            total_pages = math.ceil(total_actions / page_size) if page_size > 0 else 0

            # Формируем ответ, соответствующий UserProfileResponse
            response_data = {
                "user_details": profile_data["user_details"],
                "actions": profile_data["actions"],
                "total_actions": total_actions, # Дублируем для верхнего уровня
                "pagination": {
                    "current_page": page,
                    "total_pages": total_pages,
                    "page_size": page_size,
                    "sort_by": sort_by,
                    "sort_order": sort_order
                }
            }

            # 3. Сохраняем в кэш (fire-and-forget, ошибки не должны ломать запрос)
            try:
                await redis_client.set_cache(cache_key, response_data, ttl=CACHE_TTL)
            except Exception as e:
                logger.error(f"Failed to set cache: {e}")

            return response_data

    except asyncpg.PostgresError as e:
        logger.error(f"Database error fetching user profile {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Database Error")

@router.get(
    "/stats/action_users",
    summary="Пользователи по действию",
    description="Возвращает список пользователей, совершивших конкретное действие (команду или сообщение).",
    response_model=ActionUsersResponse
)
async def get_action_users(
    action_type: str = Query(..., description="Тип действия (command, text_message)"),
    action_details: str = Query(..., description="Содержание действия (например, /start)"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(15, ge=1, le=100, description="Размер страницы"),
    sort_by: str = Query('full_name', description="Поле сортировки (full_name, username)"),
    sort_order: str = Query('asc', description="Порядок сортировки (asc, desc)")
) -> Any:
    # 1. Проверяем кэш
    cache_key = f"action_users:{action_type}:{action_details}:p{page}:s{page_size}:{sort_by}:{sort_order}"
    try:
        cached_data = await redis_client.get_cache(cache_key)
        if cached_data:
            return cached_data
    except Exception as e:
        logger.warning(f"Redis cache error: {e}")

    # 2. Запрашиваем БД
    try:
        async with get_db_connection_obj() as db:
            data = await get_users_for_action(
                db, action_type, action_details, page, page_size, sort_by, sort_order
            )
            
            total_users = data["total_users"]
            total_pages = math.ceil(total_users / page_size) if page_size > 0 else 0

            response_data = {
                "users": data["users"],
                "pagination": {
                    "current_page": page,
                    "total_pages": total_pages,
                    "page_size": page_size,
                    "sort_by": sort_by,
                    "sort_order": sort_order
                }
            }

            # 3. Сохраняем в кэш
            try:
                await redis_client.set_cache(cache_key, response_data, ttl=CACHE_TTL)
            except Exception as e:
                logger.error(f"Failed to set cache: {e}")

            return response_data

    except asyncpg.PostgresError as e:
        logger.error(f"Database error fetching action users: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Database Error")

@router.get(
    "/users/{user_id}/export_actions",
    summary="Экспорт действий",
    description="Выгружает полную историю действий пользователя для экспорта (например, в CSV).",
    response_model=ExportActionsResponse
)
async def export_user_actions(user_id: int) -> Any:
    # 1. Проверяем кэш
    cache_key = f"export_actions:{user_id}"
    try:
        cached_data = await redis_client.get_cache(cache_key)
        if cached_data:
            return cached_data
    except Exception as e:
        logger.warning(f"Redis cache error: {e}")

    # 2. Запрашиваем БД
    try:
        async with get_db_connection_obj() as db:
            actions = await get_all_user_actions(db, user_id)
            
            response_data = {"actions": actions}

            # 3. Сохраняем в кэш
            try:
                await redis_client.set_cache(cache_key, response_data, ttl=CACHE_TTL)
            except Exception as e:
                logger.error(f"Failed to set cache: {e}")

            return response_data

    except asyncpg.PostgresError as e:
        logger.error(f"Database error exporting actions for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Database Error")