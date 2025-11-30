# fastapi_stats_app/routers/ws_router.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
import logging
import asyncio
import aiofiles
import asyncpg
import datetime
import json
import os
from typing import Set, Dict, Any

from shared_lib.redis_client import redis_client # Импортируем клиент

from shared_lib.database import (
    get_db_connection_obj,
    get_leaderboard_data_from_db,
    get_popular_commands_data_from_db,
    get_popular_messages_data_from_db,
    get_action_types_distribution_from_db,
    get_activity_over_time_data_from_db,
    get_new_users_per_day_from_db
)
from ..config import LOG_DIR, BOT_LOG_FILE_NAME

router = APIRouter()
logger = logging.getLogger(__name__)

# --- WebSocket Connection Manager ---

class ConnectionManager:
    """Менеджер для управления множеством WebSocket соединений."""
    def __init__(self, name: str = "default"):
        self.active_connections: Set[WebSocket] = set()
        self.name = name

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WS Manager '{self.name}': Client connected {websocket.client}. Total: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WS Manager '{self.name}': Client disconnected {websocket.client}. Remaining: {len(self.active_connections)}")

    async def send_personal_json(self, data: Dict[str, Any], websocket: WebSocket) -> bool:
        """Отправляет JSON конкретному клиенту. Возвращает True, если успешно."""
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_json(data)
                return True
            except Exception as e:
                logger.error(f"WS Manager '{self.name}': Error sending JSON to {websocket.client}: {e}")
                await self.disconnect(websocket)
                return False
        return False

    async def send_personal_text(self, message: str, websocket: WebSocket) -> bool:
        """Отправляет текст конкретному клиенту. Возвращает True, если успешно."""
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_text(message)
                return True
            except Exception as e:
                # Логируем ошибку только один раз при разрыве, чтобы не спамить
                # logger.error(f"WS Manager '{self.name}': Error sending text: {e}")
                await self.disconnect(websocket)
                return False
        return False

    async def broadcast_json(self, data: Dict[str, Any]):
        """Рассылает JSON всем активным клиентам."""
        if not self.active_connections:
            return
        
        # Создаем копию списка, чтобы избежать ошибки изменения размера множества во время итерации
        connections = list(self.active_connections)
        for connection in connections:
            await self.send_personal_json(data, connection)

    async def broadcast_text(self, message: str):
        """Рассылает текст всем активным клиентам."""
        if not self.active_connections:
            return
            
        connections = list(self.active_connections)
        for connection in connections:
            await self.send_personal_text(message, connection)

# Глобальные менеджеры
stats_manager = ConnectionManager(name="stats")
log_manager = ConnectionManager(name="bot_log")

# Глобальные переменные для background task
stats_update_task: asyncio.Task | None = None
last_sent_stats_data_str: str = ""
last_checked_actions_count: int = -1

async def periodic_stats_updater():
    """Фоновая задача: собирает статистику из БД и рассылает её клиентам при изменениях."""
    global last_sent_stats_data_str, last_checked_actions_count
    logger.info("Starting periodic_stats_updater task.")
    
    while True:
        try:
            # Оптимизация: если нет клиентов, спим дольше и не грузим БД
            if not stats_manager.active_connections:
                await asyncio.sleep(5)
                continue

            async with get_db_connection_obj() as db:
                # Быстрая проверка: изменилось ли количество действий?
                current_actions = await db.fetchval("SELECT COUNT(*) FROM user_actions") or 0

                if current_actions == last_checked_actions_count:
                    await asyncio.sleep(2)
                    continue
                
                last_checked_actions_count = current_actions
                logger.debug(f"Action count changed. Fetching full stats (Total: {current_actions}).")

                # Параллельный сбор данных можно было бы сделать через asyncio.gather, 
                # но для asyncpg один коннект - один запрос. Последовательно тоже ок.
                leaderboard_data = await get_leaderboard_data_from_db(db)
                popular_commands_data = await get_popular_commands_data_from_db(db)
                popular_messages_data = await get_popular_messages_data_from_db(db)
                action_types_data = await get_action_types_distribution_from_db(db)
                
                activity_over_time_data = {
                    'day': await get_activity_over_time_data_from_db(db, period='day'),
                    'week': await get_activity_over_time_data_from_db(db, period='week'),
                    'month': await get_activity_over_time_data_from_db(db, period='month'),
                }
                new_users_data = await get_new_users_per_day_from_db(db)

            current_data = {
                "total_actions": current_actions,
                "leaderboard": leaderboard_data,
                "popular_commands": popular_commands_data,
                "popular_messages": popular_messages_data,
                "action_types_distribution": action_types_data,
                "activity_over_time": activity_over_time_data,
                "new_users_per_day": new_users_data,
                "last_updated": datetime.datetime.now().isoformat()
            }

            # Сериализуем для сравнения
            current_data_json_str = json.dumps(current_data, ensure_ascii=False, sort_keys=True)

            if current_data_json_str != last_sent_stats_data_str:
                await stats_manager.broadcast_json(current_data)
                last_sent_stats_data_str = current_data_json_str
                logger.info("Broadcasted updated stats.")

        except asyncpg.PostgresError as e:
            logger.error(f"StatsUpdater DB Error: {e}")
            await stats_manager.broadcast_json({"error": "Database error fetching stats"})
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"StatsUpdater Unexpected Error: {e}", exc_info=True)
            await stats_manager.broadcast_json({"error": "Internal server error updating stats"})
            await asyncio.sleep(10)
            
        await asyncio.sleep(2)

@router.websocket("/ws/stats/total_actions")
async def websocket_total_actions_endpoint(websocket: WebSocket):
    """Эндпоинт WebSocket для живой статистики."""
    global stats_update_task
    
    await stats_manager.connect(websocket)

    # Отправляем последние известные данные сразу при подключении
    if last_sent_stats_data_str:
        try:
            await stats_manager.send_personal_json(json.loads(last_sent_stats_data_str), websocket)
        except Exception as e:
            logger.error(f"Error sending initial stats: {e}")

    # Запускаем фоновую задачу (синглтон)
    if stats_update_task is None or stats_update_task.done():
        stats_update_task = asyncio.create_task(periodic_stats_updater())
    
    try:
        while True:
            # Просто поддерживаем соединение, данные идут от сервера к клиенту
            await websocket.receive_text()
    except WebSocketDisconnect:
        await stats_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Stats WS Error: {e}")
        await stats_manager.disconnect(websocket)

async def stream_log_file_to_websocket(websocket: WebSocket, manager: ConnectionManager):
    """Читает лог-файл и отправляет новые строки в WebSocket (аналог tail -f)."""
    bot_log_full_path = os.path.join(LOG_DIR, BOT_LOG_FILE_NAME)
    
    try:
        # 1. Отправка последних строк
        if os.path.exists(bot_log_full_path):
            async with aiofiles.open(bot_log_full_path, mode='r', encoding='utf-8', errors='ignore') as f:
                lines = await f.readlines()
                for line in lines[-50:]:
                    if not await manager.send_personal_text(line.strip(), websocket):
                        return # Выход, если клиент отключился
                
                if not await manager.send_personal_text("--- LIVE LOG STREAM STARTED ---", websocket):
                    return
        else:
            if not await manager.send_personal_text(f"Waiting for log file: {bot_log_full_path}...", websocket):
                return

        # 2. Ожидание появления файла
        while not os.path.exists(bot_log_full_path):
            await asyncio.sleep(2)
            if websocket.client_state != WebSocketState.CONNECTED:
                return

        # 3. Стриминг
        async with aiofiles.open(bot_log_full_path, mode='r', encoding='utf-8', errors='ignore') as f:
            await f.seek(0, os.SEEK_END)
            
            while websocket.client_state == WebSocketState.CONNECTED:
                line = await f.readline()
                if line:
                    # ВАЖНОЕ ИСПРАВЛЕНИЕ: Проверяем результат отправки
                    success = await manager.send_personal_text(line.strip(), websocket)
                    if not success:
                        logger.info("Client disconnected during log stream. Stopping stream.")
                        break
                else:
                    await asyncio.sleep(0.5)

    except Exception as e:
        # Игнорируем ошибку "Cannot call send...", так как мы её уже обработали выше
        if "Cannot call \"send\"" not in str(e):
            logger.error(f"Log Stream Error: {e}")
            await manager.send_personal_text(f"Error reading log: {str(e)}", websocket)

@router.websocket("/ws/bot_log")
async def websocket_bot_log_endpoint(websocket: WebSocket):
    """Эндпоинт WebSocket для стриминга логов."""
    await log_manager.connect(websocket)
    try:
        await stream_log_file_to_websocket(websocket, log_manager)
    except WebSocketDisconnect:
        await log_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Bot Log WS Error: {e}")
        await log_manager.disconnect(websocket)
        

@router.websocket("/ws/users/{user_id}")
async def websocket_user_updates(websocket: WebSocket, user_id: int):
    """
    WebSocket для получения обновлений конкретного пользователя в реальном времени.
    Использует Redis Pub/Sub.
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for user history: {user_id}")

    pubsub = redis_client.client.pubsub()
    channel_name = f"user_updates:{user_id}"
    
    try:
        # Подписываемся на канал Redis
        await pubsub.subscribe(channel_name)
        
        # Бесконечный цикл чтения из Redis и отправки в WebSocket
        async for message in pubsub.listen():
            if message['type'] == 'message':
                # message['data'] это JSON строка, которую мы отправили из database.py
                await websocket.send_text(message['data'])
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user history: {user_id}")
    except Exception as e:
        logger.error(f"Error in user updates WS: {e}")
    finally:
        await pubsub.unsubscribe(channel_name)
        await pubsub.close()
        # await websocket.close() # Обычно не нужно, если disconnect уже сработал