from fastapi import APIRouter, HTTPException, Query, status, Depends
import math
import logging
import os
import aiohttp
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from shared_lib.database import (
    get_db_session_dependency, 
    get_user_profile_data_from_db,
    get_users_for_action,
    get_all_user_actions,
    log_user_action
)
from shared_lib.redis_client import redis_client
from shared_lib.schemas import (
    UserProfileResponse, 
    ActionUsersResponse, 
    ExportActionsResponse,
    SendMessageRequest 
)

router = APIRouter()
logger = logging.getLogger(__name__)

# TTL кэша в секундах (5 минут)
CACHE_TTL = 300

# Получаем токен из переменных окружения для отправки сообщений
BOT_TOKEN = os.getenv("BOT_TOKEN")

@router.get(
    "/health",
    summary="Health Check",
    description="Проверяет доступность сервиса и подключение к базе данных.",
    response_model=dict[str, str],
    status_code=status.HTTP_200_OK
)
async def health_check(db: AsyncSession = Depends(get_db_session_dependency)) -> dict[str, str]:
    """
    Легковесная проверка здоровья сервиса.
    """
    try:
        # Используем SQLAlchemy text() для выполнения сырого SQL запроса проверки
        await db.execute(text("SELECT 1"))
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
    sort_by: str = Query('timestamp', description="Поле сортировки"),
    sort_order: str = Query('desc', description="Порядок сортировки"),
    db: AsyncSession = Depends(get_db_session_dependency)
) -> Any:
    # 1. Проверяем кэш (только если не первая страница, чтобы видеть свежие логи сразу)
    cache_key = f"user_profile:{user_id}:p{page}:s{page_size}:{sort_by}:{sort_order}"
    if page > 1:
        try:
            cached_data = await redis_client.get_cache(cache_key)
            if cached_data:
                return cached_data
        except Exception as e:
            logger.warning(f"Redis cache error: {e}")

    # 2. Запрашиваем БД
    try:
        # Передаем сессию db, полученную через Depends
        profile_data = await get_user_profile_data_from_db(
            db, user_id, page, page_size, sort_by, sort_order
        )
        
        if profile_data is None:
            raise HTTPException(status_code=404, detail="Пользователь не найден.")

        total_actions = profile_data["total_actions"]
        total_pages = math.ceil(total_actions / page_size) if page_size > 0 else 0

        response_data = {
            "user_details": profile_data["user_details"],
            "actions": profile_data["actions"],
            "total_actions": total_actions,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "page_size": page_size,
                "sort_by": sort_by,
                "sort_order": sort_order
            }
        }

        # 3. Сохраняем в кэш (недолго)
        try:
            await redis_client.set_cache(cache_key, response_data, ttl=60) # 1 минута TTL для профиля
        except Exception as e:
            logger.error(f"Failed to set cache: {e}")

        return response_data

    except Exception as e:
        logger.error(f"Database error fetching user profile {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Database Error")

@router.get(
    "/stats/action_users",
    summary="Пользователи по действию",
    description="Возвращает список пользователей, совершивших конкретное действие.",
    response_model=ActionUsersResponse
)
async def get_action_users(
    action_type: str = Query(..., description="Тип действия"),
    action_details: str = Query(..., description="Содержание действия"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(15, ge=1, le=100, description="Размер страницы"),
    sort_by: str = Query('full_name', description="Поле сортировки"),
    sort_order: str = Query('asc', description="Порядок сортировки"),
    db: AsyncSession = Depends(get_db_session_dependency)
) -> Any:
    cache_key = f"action_users:{action_type}:{action_details}:p{page}:s{page_size}:{sort_by}:{sort_order}"
    try:
        cached_data = await redis_client.get_cache(cache_key)
        if cached_data:
            return cached_data
    except Exception as e:
        logger.warning(f"Redis cache error: {e}")

    try:
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

        try:
            await redis_client.set_cache(cache_key, response_data, ttl=CACHE_TTL)
        except Exception as e:
            logger.error(f"Failed to set cache: {e}")

        return response_data

    except Exception as e:
        logger.error(f"Database error fetching action users: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Database Error")

@router.get(
    "/users/{user_id}/export_actions",
    summary="Экспорт действий",
    description="Выгружает полную историю действий пользователя.",
    response_model=ExportActionsResponse
)
async def export_user_actions(
    user_id: int,
    db: AsyncSession = Depends(get_db_session_dependency)
) -> Any:
    try:
        actions = await get_all_user_actions(db, user_id)
        return {"actions": actions}
    except Exception as e:
        logger.error(f"Database error exporting actions for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Database Error")

@router.post(
    "/users/{user_id}/send_message",
    summary="Отправить сообщение пользователю",
    description="Отправляет сообщение в Telegram и сохраняет его в БД как исходящее от админа.",
    status_code=status.HTTP_200_OK
)
async def send_message_to_user(user_id: int, message_data: SendMessageRequest):
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN не настроен на сервере.")

    text = message_data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Сообщение не может быть пустым")
    
    # 1. Отправка в Telegram через Aiohttp (напрямую в API)
    tg_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": user_id,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(tg_url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to send message to {user_id}: {error_text}")
                    raise HTTPException(status_code=400, detail=f"Telegram API Error: {error_text}")
                
    except aiohttp.ClientError as e:
        logger.error(f"Network error sending message to {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка сети при отправке в Telegram")

    # 2. Сохранение сообщения в БД и публикация в Redis
    # Мы используем обновленную функцию log_user_action, которая сама управляет сессией и Redis
    try:
        await log_user_action(
            user_id=user_id,
            username=None,
            full_name="System", # Помечаем как системное сообщение
            avatar_pic_url=None,
            action_type='admin_message',
            action_details=text
        )
    except Exception as e:
        logger.error(f"Error logging admin message to DB for user {user_id}: {e}", exc_info=True)
        # Не возвращаем ошибку клиенту (500), так как сообщение в Телеграм уже успешно ушло.
        # Логируем и возвращаем успех.
    
    return {"status": "success"}