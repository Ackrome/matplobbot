# c:/Users/ivant/Desktop/proj/matplobbot/fastapi_stats_app/routers/ws_router.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from starlette.websockets import WebSocketState
import logging
import asyncio
import aiofiles
import asyncpg, datetime
import json # Добавляем импорт json
import os

from shared_lib.database import (
    get_db_connection_obj, # This function is in shared_lib/database.py
    get_leaderboard_data_from_db,
    get_popular_commands_data_from_db,
    get_popular_messages_data_from_db,
    get_action_types_distribution_from_db,
    get_activity_over_time_data_from_db
)
from ..config import LOG_DIR, BOT_LOG_FILE_NAME,FASTAPI_LOG_FILE_NAME # Обновленные импорты

router = APIRouter()
logger = logging.getLogger(__name__)
# Конфигурация logging.basicConfig теперь находится в main.py и выполняется при старте приложения.
logging.getLogger("aiogram.event").setLevel(logging.WARNING)

# Класс для управления WebSocket соединениями
class ConnectionManager:
    def __init__(self, name: str = "default"):
        self.active_connections: list[WebSocket] = []
        self.name = name  # Для логирования
        self._lock = asyncio.Lock() # Для защиты списка active_connections

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected: {websocket.client} to manager '{self.name}'. Total: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                logger.info(f"WebSocket client {websocket.client} removed from manager '{self.name}'. Total: {len(self.active_connections)}")
            # else:
                # logger.debug(f"WebSocket client {websocket.client} already removed or not found in manager '{self.name}'.")

    async def send_personal_json(self, data: dict, websocket: WebSocket):
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_json(data)
            except (WebSocketDisconnect, RuntimeError) as e:
                # These errors are expected if the client disconnects during a send operation.
                # Log them at a lower level to reduce noise.
                logger.debug(f"Could not send JSON to {websocket.client} (disconnected): {e}")
            except Exception as e:
                logger.error(f"Unexpected error sending personal JSON to {websocket.client} in manager '{self.name}': {e}")
                # Consider auto-disconnecting on send error after multiple retries or specific errors

    async def send_personal_text(self, message: str, websocket: WebSocket):
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_text(message)
            except (WebSocketDisconnect, RuntimeError) as e:
                # Gracefully handle cases where the client disconnects while we're trying to send.
                # This is the exact cause of the "Cannot call 'send' once a close message has been sent" error.
                logger.debug(f"Could not send text to {websocket.client} (disconnected): {e}")
            except Exception as e:
                logger.error(f"Unexpected error sending personal text to {websocket.client} in manager '{self.name}': {e}")

    async def _broadcast(self, send_callable_name: str, payload):
        async with self._lock:
            # Итерируемся по копии для безопасного удаления во время итерации (если потребуется)
            connections_to_broadcast = list(self.active_connections)
        
        if not connections_to_broadcast:
            return

        disconnected_during_broadcast = []

        for connection in connections_to_broadcast:
            if connection.client_state == WebSocketState.CONNECTED:
                try:
                    if send_callable_name == "send_json":
                        await connection.send_json(payload)
                    elif send_callable_name == "send_text":
                        await connection.send_text(payload)
                except Exception as e: # WebSocketDisconnect, RuntimeError, etc.
                    logger.warning(f"Error broadcasting {send_callable_name} to {connection.client} in manager '{self.name}': {e}. Marking for disconnect.")
                    disconnected_during_broadcast.append(connection)
            else: # Уже отключен или в процессе отключения
                disconnected_during_broadcast.append(connection)
        
        if disconnected_during_broadcast:
            async with self._lock:
                for ws in disconnected_during_broadcast:
                    if ws in self.active_connections: # Проверяем еще раз перед удалением
                        self.active_connections.remove(ws)
                        logger.info(f"WebSocket client {ws.client} removed post-broadcast due to error/disconnect from manager '{self.name}'.")

    async def broadcast_json(self, data: dict):
        await self._broadcast("send_json", data)

    async def broadcast_text(self, message: str):
        await self._broadcast("send_text", message)


# Создаем экземпляры менеджеров
stats_manager = ConnectionManager(name="stats")
log_manager = ConnectionManager(name="bot_log")

# Глобальное состояние для задачи обновления статистики
stats_update_task = None
last_sent_stats_data_str = "" # Для предотвращения отправки одних и тех же данных
last_checked_actions_count = -1 # Для быстрой проверки изменений

async def periodic_stats_updater():
    global last_sent_stats_data_str, last_checked_actions_count
    logger.info("Starting periodic_stats_updater task.")
    while True:
        if not stats_manager.active_connections: # Выполняем только если есть активные соединения
            await asyncio.sleep(5) # Спим дольше, если никто не подключен
            continue
        try:
            async with get_db_connection_obj() as db:
                # Use fetchval to get a single value directly
                current_actions = await db.fetchval("SELECT COUNT(*) FROM user_actions") or 0

                # Если количество действий не изменилось, нет смысла пересчитывать остальное
                if current_actions == last_checked_actions_count:
                    await asyncio.sleep(2) # Короткая пауза и следующая итерация
                    continue
                
                logger.info(f"Action count changed from {last_checked_actions_count} to {current_actions}. Fetching full stats.")
                last_checked_actions_count = current_actions

                leaderboard_data = await get_leaderboard_data_from_db(db)
                popular_commands_data = await get_popular_commands_data_from_db(db)
                popular_messages_data = await get_popular_messages_data_from_db(db)
                action_types_data = await get_action_types_distribution_from_db(db)
                # Fetch activity data for all periods
                activity_over_time_data = {
                    'day': await get_activity_over_time_data_from_db(db, period='day'),
                    'week': await get_activity_over_time_data_from_db(db, period='week'),
                    'month': await get_activity_over_time_data_from_db(db, period='month'),
                }

            current_data = {
                "total_actions": current_actions,
                "leaderboard": leaderboard_data,
                "popular_commands": popular_commands_data,
                "popular_messages": popular_messages_data,
                "action_types_distribution": action_types_data,
                "activity_over_time": activity_over_time_data,
                "last_updated": datetime.datetime.now().isoformat()
            }
            # Используем json.dumps для корректного сравнения и хранения JSON-строки
            current_data_json_str = json.dumps(current_data, ensure_ascii=False, sort_keys=True)

            if current_data_json_str != last_sent_stats_data_str:
                await stats_manager.broadcast_json(current_data)
                last_sent_stats_data_str = current_data_json_str # Сохраняем JSON-строку
                logger.info(f"StatsUpdater: Broadcasted updated stats (total_actions: {current_actions}, leaderboard: {len(leaderboard_data)} users, ...)")

        except asyncpg.PostgresError as e:
            logger.error(f"StatsUpdater: Database error: {e}", exc_info=True)
            await stats_manager.broadcast_json({"error": "Ошибка получения данных из БД для статистики"})
            await asyncio.sleep(10) # Пауза перед повторной попыткой при ошибке БД
        except HTTPException as e: # Может быть вызвано get_db_connection_obj
            logger.error(f"StatsUpdater: HTTPException: {e.detail}")
            await stats_manager.broadcast_json({"error": e.detail})
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"StatsUpdater: Unexpected error: {e}", exc_info=True)
            await stats_manager.broadcast_json({"error": "Непредвиденная ошибка на сервере при обновлении статистики"})
            await asyncio.sleep(10)
            
        await asyncio.sleep(2) # Интервал для проверки/отправки обновлений

@router.websocket("/ws/stats/total_actions")
async def websocket_total_actions_endpoint(websocket: WebSocket):
    global stats_update_task, last_sent_stats_data_str # Убедимся, что last_sent_stats_data_str доступен
    await stats_manager.connect(websocket)

    # Отправить текущие кэшированные данные новому клиенту, если они есть
    if last_sent_stats_data_str:
        try:
            # last_sent_stats_data_str хранит JSON-строку, которую нужно преобразовать в Python dict
            data_to_send = json.loads(last_sent_stats_data_str)
            await stats_manager.send_personal_json(data_to_send, websocket)
            logger.info(f"Sent initial cached stats data to newly connected client {websocket.client}")
        except json.JSONDecodeError:
            logger.error(f"Failed to parse last_sent_stats_data_str for initial send to {websocket.client}. Data: '{last_sent_stats_data_str[:200]}...'")
        except Exception as e:
            logger.error(f"Error sending initial cached stats data to {websocket.client}: {e}", exc_info=True)

    # Запускаем фоновую задачу, если она еще не запущена
    if stats_update_task is None or stats_update_task.done():
        if stats_update_task and stats_update_task.done(): # Проверяем, не завершилась ли задача с ошибкой
            try:
                stats_update_task.result() 
            except Exception as e:
                logger.error(f"Previous stats_update_task ended with error: {e}")
        logger.info("Creating and starting new periodic_stats_updater task.")
        stats_update_task = asyncio.create_task(periodic_stats_updater())
    
    try:
        while websocket.client_state == WebSocketState.CONNECTED:
            # Этот цикл удерживает соединение открытым и обрабатывает WebSocketDisconnect.
            # Мы не ожидаем сообщений от клиента здесь, сервер сам отправляет данные.
            await websocket.receive_text() # Ожидаем любое сообщение или разрыв соединения
    except WebSocketDisconnect:
        logger.info(f"Client {websocket.client} disconnected from stats websocket.")
    except Exception as e: # Другие возможные ошибки WebSocket
        logger.error(f"Unexpected error in stats websocket for {websocket.client}: {e}", exc_info=True)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close(code=1011) # Internal server error
            except RuntimeError: # pragma: no cover
                logger.warning(f"Stats WS: Error closing connection for {websocket.client}, already closed.")
    finally:
        await stats_manager.disconnect(websocket)
        logger.info(f"Stats WebSocket session ended for client: {websocket.client}")
        # Можно добавить логику остановки periodic_stats_updater, если активных клиентов не осталось,
        # но текущая реализация periodic_stats_updater сама проверяет наличие активных клиентов.

async def stream_log_file_to_websocket(websocket: WebSocket, manager: ConnectionManager):
    bot_log_full_path = os.path.join(LOG_DIR, BOT_LOG_FILE_NAME) # Формируем путь здесь
    try:
        # Отправляем последние N строк при подключении
        try:
            async with aiofiles.open(bot_log_full_path, mode='r', encoding='utf-8', errors='ignore') as f:
                lines = await f.readlines()
                last_lines = lines[-50:]
                if last_lines:
                    await manager.send_personal_text("--- Последние строки лога ---", websocket)
                    for line in last_lines:
                        if websocket.client_state != WebSocketState.CONNECTED: return
                        await manager.send_personal_text(line.strip(), websocket)
                    await manager.send_personal_text("--- Начало трансляции новых логов ---", websocket)
        except FileNotFoundError:
            if websocket.client_state != WebSocketState.DISCONNECTED:
                await manager.send_personal_text(f"ПРЕДУПРЕЖДЕНИЕ: Файл лога {bot_log_full_path} еще не создан ботом.", websocket)

        # Ожидаем создания файла, если его нет
        if not os.path.exists(bot_log_full_path):
            logger.warning(f"Log file {bot_log_full_path} does not exist. Waiting for it to be created.")
            while not os.path.exists(bot_log_full_path):
                if websocket.client_state != WebSocketState.CONNECTED: return
                await manager.send_personal_text(f"ОЖИДАНИЕ: Файл лога {bot_log_full_path} еще не создан...", websocket)
                await asyncio.sleep(5)
            if websocket.client_state == WebSocketState.CONNECTED:
                 await manager.send_personal_text(f"ИНФО: Файл лога {bot_log_full_path} найден. Начинаю трансляцию.", websocket)

        # Стриминг новых строк
        async with aiofiles.open(bot_log_full_path, mode='r', encoding='utf-8', errors='ignore') as f:
            await f.seek(0, os.SEEK_END) # Переходим в конец файла
            while websocket.client_state == WebSocketState.CONNECTED:
                line = await f.readline()
                if not line:
                    await asyncio.sleep(0.2) # Ждем новые строки
                    continue
                if websocket.client_state == WebSocketState.CONNECTED: # Дополнительная проверка перед отправкой
                    await manager.send_personal_text(line.strip(), websocket)
                else:
                    break # Выходим из цикла, если клиент отключился

    except FileNotFoundError: # На случай, если файл удален между проверками
        logger.error(f"Log Stream: Файл лога не найден во время стриминга: {bot_log_full_path}")
        if websocket.client_state == WebSocketState.CONNECTED:
            await manager.send_personal_text(f"ОШИБКА: Файл лога не найден: {bot_log_full_path}.", websocket)
    except Exception as e:
        # WebSocketDisconnect будет обработан в вызывающей функции websocket_bot_log_endpoint
        if not isinstance(e, WebSocketDisconnect):
            logger.error(f"Log Stream: Ошибка при чтении файла лога: {e}", exc_info=True)
            if websocket.client_state == WebSocketState.CONNECTED:
                try:
                    await manager.send_personal_text(f"ОШИБКА СЕРВЕРА ПРИ ЧТЕНИИ ЛОГА: {str(e)}", websocket)
                except Exception as send_err:
                    logger.error(f"Log Stream: Error sending error message to client: {send_err}")

@router.websocket("/ws/bot_log")
async def websocket_bot_log_endpoint(websocket: WebSocket):
    await log_manager.connect(websocket)
    try:
        await stream_log_file_to_websocket(websocket, log_manager)
        # stream_log_file_to_websocket будет работать, пока соединение активно.
        # Если он завершится (например, из-за ошибки файла, не обработанной внутри),
        # соединение может закрыться. Для явного удержания:
        while websocket.client_state == WebSocketState.CONNECTED:
             # Этот цикл гарантирует, что эндпоинт не завершится, пока клиент подключен,
             # даже если stream_log_file_to_websocket завершился по какой-то причине, кроме disconnect.
            await asyncio.sleep(1) # Просто поддерживаем жизнь, проверяя состояние.

    except WebSocketDisconnect:
        logger.info(f"Client {websocket.client} disconnected from bot_log websocket (expected).")
    except Exception as e: # Другие возможные ошибки WebSocket
        logger.error(f"Unexpected error in bot_log websocket for {websocket.client}: {e}", exc_info=True)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close(code=1011)
            except RuntimeError:
                logger.warning(f"WebSocket лог: Ошибка при попытке закрыть соединение для {websocket.client}, возможно уже закрыто.")
    finally:
        await log_manager.disconnect(websocket)
        logger.info(f"Bot Log WebSocket session ended for client: {websocket.client}")