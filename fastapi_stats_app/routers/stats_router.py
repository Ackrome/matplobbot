# c:/Users/ivant/Desktop/proj/matplobbot/fastapi_stats_app/routers/stats_router.py
from fastapi import APIRouter, HTTPException
import aiosqlite
import logging
from ..db_utils import (
    get_db_connection_obj,
    get_leaderboard_data_from_db,
    get_popular_commands_data_from_db,
    get_popular_messages_data_from_db,
    get_action_types_distribution_from_db,
    get_activity_over_time_data_from_db
)

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/stats/total_actions", summary="Общее количество действий", description="Возвращает общее количество записанных действий пользователей.")
async def get_total_actions():
    try:
        async with get_db_connection_obj() as db:
            async with db.execute("SELECT COUNT(*) FROM user_actions") as cursor:
                row = await cursor.fetchone()
                return {"total_actions": row[0] if row else 0}
    except aiosqlite.Error as e:
        logger.error(f"Ошибка базы данных при получении total_actions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка при запросе к базе данных (total_actions).")

@router.get("/stats/leaderboard", summary="Таблица лидеров", description="Возвращает список пользователей с наибольшим количеством действий.")
async def get_leaderboard():
    try:
        async with get_db_connection_obj() as db:
            leaderboard_data = await get_leaderboard_data_from_db(db)
            return {"leaderboard": leaderboard_data}
    except aiosqlite.Error as e:
        logger.error(f"Ошибка базы данных при получении leaderboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка при запросе к базе данных (leaderboard).")

@router.get("/stats/popular_commands", summary="Популярные команды", description="Возвращает список наиболее часто используемых команд.")
async def get_popular_commands():
    try:
        async with get_db_connection_obj() as db:
            popular_commands_data = await get_popular_commands_data_from_db(db)
            return {"popular_commands": popular_commands_data}
    except aiosqlite.Error as e:
        logger.error(f"Ошибка базы данных при получении popular_commands: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка при запросе к базе данных (popular_commands).")

@router.get("/stats/popular_messages", summary="Популярные сообщения", description="Возвращает список наиболее часто отправляемых текстовых сообщений.")
async def get_popular_messages():
    try:
        async with get_db_connection_obj() as db:
            popular_messages_data = await get_popular_messages_data_from_db(db)
            return {"popular_messages": popular_messages_data}
    except aiosqlite.Error as e:
        logger.error(f"Ошибка базы данных при получении popular_messages: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка при запросе к базе данных (popular_messages).")

@router.get("/stats/action_types_distribution", summary="Распределение типов действий", description="Возвращает количество действий по их типам (команда, сообщение и т.д.).")
async def get_action_types_distribution():
    try:
        async with get_db_connection_obj() as db:
            distribution_data = await get_action_types_distribution_from_db(db)
            return {"action_types_distribution": distribution_data}
    except aiosqlite.Error as e:
        logger.error(f"Ошибка базы данных при получении action_types_distribution: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка при запросе к базе данных (action_types_distribution).")

@router.get("/stats/activity_over_time", summary="Активность по времени", description="Возвращает количество действий по дням.")
async def get_activity_over_time():
    try:
        async with get_db_connection_obj() as db:
            activity_data = await get_activity_over_time_data_from_db(db, period='day')
            return {"activity_over_time": activity_data}
    except aiosqlite.Error as e:
        logger.error(f"Ошибка базы данных при получении activity_over_time: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка при запросе к базе данных (activity_over_time).")