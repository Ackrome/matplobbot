from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse # StreamingResponse убран, т.к. SSE заменяется WebSocket
from fastapi.templating import Jinja2Templates
import aiosqlite
import os
import logging
import aiofiles # Для асинхронного чтения файла
# Настройка логгирования для FastAPI приложения
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
import asyncio # Добавляем asyncio
logger = logging.getLogger(__name__)

app = FastAPI(title="Bot Stats API", version="0.1.0")

# Путь к базе данных такой же, как и для бота, так как volume будет смонтирован
# Docker-контейнер бота создает БД в /app/db_data/user_actions.db
# Этот же volume будет смонтирован в /app/db_data для FastAPI контейнера
DB_PATH = "/app/db_data/user_actions.db"
LOG_FILE_PATH = "/app/logs/bot.log" # Путь к файлу логов бота

# Настройка Jinja2 для шаблонов
templates = Jinja2Templates(directory="templates")

# Изменяем get_db_connection на синхронную функцию,
# которая возвращает awaitable context manager.
def get_db_connection_obj(): # Переименовано для ясности, можно оставить get_db_connection
    """
    Проверяет наличие файла БД и возвращает объект aiosqlite.connect(),
    который является awaitable context manager.
    """
    if not os.path.exists(DB_PATH):
        logger.warning(f"Файл базы данных {DB_PATH} еще не существует. Возможно, бот еще не создал его.")
        raise HTTPException(status_code=503, detail="База данных еще не инициализирована ботом. Пожалуйста, подождите или убедитесь, что бот запущен и работает корректно.")
    # aiosqlite.connect() сам по себе не вызывает ошибок подключения на этом этапе,
    # он просто возвращает объект. Ошибки возникнут при фактическом await.
    return aiosqlite.connect(DB_PATH)

# Изменяем корневой эндпоинт для отображения HTML страницы
@app.get("/", response_class=HTMLResponse, summary="Главная страница статистики", description="Отображает HTML страницу со статистикой бота.")
async def read_root_html(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/stats/total_actions", summary="Общее количество действий", description="Возвращает общее количество записанных действий пользователей.")
async def get_total_actions():
    try:
        # async with теперь корректно обработает awaitable, возвращаемый get_db_connection_obj()
        async with get_db_connection_obj() as db:
            async with db.execute("SELECT COUNT(*) FROM user_actions") as cursor:
                row = await cursor.fetchone()
                return {"total_actions": row[0] if row else 0}
    except aiosqlite.Error as e:
        logger.error(f"Ошибка базы данных при получении total_actions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка при запросе к базе данных (total_actions).")

async def get_leaderboard_data_from_db(db_conn):
    """Извлекает данные для таблицы лидеров из БД, включая аватар."""
    query = """
        SELECT
            u.user_id,
            u.full_name,
            COALESCE(u.username, 'Нет username') AS username,
            u.avatar_pic_url,
            COUNT(ua.id) AS actions_count,
            STRFTIME('%Y-%m-%d %H:%M:%S', MAX(ua.timestamp)) AS last_action_time
        FROM
            users u
        JOIN
            user_actions ua ON u.user_id = ua.user_id
        GROUP BY
            u.user_id, u.full_name, u.username, u.avatar_pic_url
        ORDER BY
            actions_count DESC
        LIMIT 100; -- Ограничиваем вывод для производительности
    """
    async with db_conn.execute(query) as cursor:
        rows = await cursor.fetchall()
        leaderboard = []
        for row_tuple in rows:
            leaderboard.append({
                "user_id": row_tuple[0],
                "full_name": row_tuple[1],
                "username": row_tuple[2],
                "avatar_pic_url": row_tuple[3], # Новый столбец
                "actions_count": row_tuple[4],
                "last_action_time": row_tuple[5]
            })
        return leaderboard

async def get_popular_commands_data_from_db(db_conn):
    """Извлекает данные о популярных командах из БД."""
    query = """
        SELECT
            action_details as command,
            COUNT(id) as command_count
        FROM
            user_actions
        WHERE
            action_type = 'command'
        GROUP BY
            action_details
        ORDER BY
            command_count DESC
        LIMIT 10; -- Ограничим топ-10 командами для примера
    """
    async with db_conn.execute(query) as cursor:
        rows = await cursor.fetchall()
        popular_commands = []
        for row_tuple in rows: # Предполагаем, что action_details это команда, command_count это ее счетчик
            popular_commands.append({"command": row_tuple[0], "count": row_tuple[1]})
        return popular_commands

async def get_popular_messages_data_from_db(db_conn):
    """Извлекает данные о популярных текстовых сообщениях из БД."""
    query = """
        SELECT
            CASE
                WHEN LENGTH(action_details) > 30 THEN SUBSTR(action_details, 1, 27) || '...'
                ELSE action_details
            END as message_snippet,
            COUNT(id) as message_count
        FROM
            user_actions
        WHERE
            action_type = 'text_message' AND action_details IS NOT NULL AND action_details != ''
        GROUP BY
            message_snippet
        ORDER BY
            message_count DESC
        LIMIT 10; -- Ограничим топ-10 сообщениями
    """
    async with db_conn.execute(query) as cursor:
        rows = await cursor.fetchall()
        return [{"message": row[0], "count": row[1]} for row in rows]

async def get_action_types_distribution_from_db(db_conn):
    """Извлекает данные о распределении типов действий из БД."""
    query = """
        SELECT
            action_type,
            COUNT(id) as type_count
        FROM
            user_actions
        GROUP BY
            action_type
        ORDER BY
            type_count DESC;
    """
    async with db_conn.execute(query) as cursor:
        rows = await cursor.fetchall()
        # rows будут кортежами (action_type, type_count)
        return [{"action_type": row[0], "count": row[1]} for row in rows]

async def get_activity_over_time_data_from_db(db_conn, period='day'):
    """Извлекает данные об активности пользователей по времени (день, неделя, месяц) из БД."""
    if period == 'day':
        date_format = '%Y-%m-%d'
    elif period == 'month':
        date_format = '%Y-%m'
    else: # По умолчанию день
        date_format = '%Y-%m-%d'

    query = f"""
        SELECT
            STRFTIME('{date_format}', timestamp) as period_start,
            COUNT(id) as actions_count
        FROM user_actions
        GROUP BY period_start
        ORDER BY period_start ASC;
    """
    async with db_conn.execute(query) as cursor:
        rows = await cursor.fetchall()
        return [{"period": row[0], "count": row[1]} for row in rows]

@app.websocket("/ws/stats/total_actions")
async def websocket_total_actions_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info(f"WebSocket клиент подключен: {websocket.client.host}:{websocket.client.port}")
    last_sent_data_str = ""
    
    try:
        while True:
            # current_actions = -1 # Удаляем, т.к. будем получать из БД
            # leaderboard_data = [] # Инициализируем на случай ошибок до первого получения
            try:
                async with get_db_connection_obj() as db:
                    async with db.execute("SELECT COUNT(*) FROM user_actions") as cursor:
                        row = await cursor.fetchone()
                        current_actions = row[0] if row else 0
                    
                    leaderboard_data = await get_leaderboard_data_from_db(db)
                    popular_commands_data = await get_popular_commands_data_from_db(db)
                    popular_messages_data = await get_popular_messages_data_from_db(db)
                    action_types_data = await get_action_types_distribution_from_db(db)
                    activity_over_time_data = await get_activity_over_time_data_from_db(db, period='day') # Пока только по дням

                current_data = {
                    "total_actions": current_actions,
                    "leaderboard": leaderboard_data,
                    "popular_commands": popular_commands_data,
                    "popular_messages": popular_messages_data,
                    "action_types_distribution": action_types_data,
                    "activity_over_time": activity_over_time_data
                }
                current_data_str = str(current_data) # Простой способ сравнить, изменились ли данные

                if current_data_str != last_sent_data_str:
                    await websocket.send_json(current_data)
                    last_sent_data_str = current_data_str
                    logger.info(f"WebSocket: Отправлены обновленные данные (total_actions: {current_actions}, leaderboard: {len(leaderboard_data)}, " 
                                f"commands: {len(popular_commands_data)}, messages: {len(popular_messages_data)}, action_types: {len(action_types_data)}, "
                                f"activity_over_time: {len(activity_over_time_data)})")

            except aiosqlite.Error as e:
                logger.error(f"WebSocket: Ошибка БД при получении total_actions: {e}", exc_info=True)
                await websocket.send_json({"error": "Ошибка получения данных из БД"})
                await asyncio.sleep(5) # Ждем дольше при ошибке БД
                continue
            except HTTPException as e:
                logger.error(f"WebSocket: HTTPException: {e.detail}")
                await websocket.send_json({"error": e.detail})
                break # Прерываем цикл, если БД недоступна
            
            await asyncio.sleep(2)  # Проверяем каждые 2 секунды
    except WebSocketDisconnect:
        logger.info(f"WebSocket клиент отключился: {websocket.client}")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка WebSocket: {e}", exc_info=True)
        # Попытка закрыть соединение, если оно еще открыто
        if websocket.client_state != websocket.client_state.DISCONNECTED:
            await websocket.close(code=1011) # Internal Error
    finally:
        logger.info(f"Завершение WebSocket сессии для клиента: {websocket.client}")

async def stream_log_file(websocket: WebSocket):
    """Транслирует новые строки из файла лога."""
    try:
        # Отправляем последние N строк при подключении (опционально)
        # Например, последние 50 строк
        try:
            async with aiofiles.open(LOG_FILE_PATH, mode='r', encoding='utf-8', errors='ignore') as f:
                lines = await f.readlines()
                last_lines = lines[-50:] # Берем последние 50 строк
                if last_lines:
                    await websocket.send_text("--- Последние строки лога ---")
                    for line in last_lines:
                        await websocket.send_text(line.strip())
                    await websocket.send_text("--- Начало трансляции новых логов ---")
        except FileNotFoundError:
            await websocket.send_text(f"ПРЕДУПРЕЖДЕНИЕ: Файл лога {LOG_FILE_PATH} еще не создан ботом.")

        async with aiofiles.open(LOG_FILE_PATH, mode='r', encoding='utf-8', errors='ignore') as f:
            await f.seek(0, 2) # Переходим в конец файла
            while True:
                line = await f.readline()
                if not line:
                    await asyncio.sleep(0.2) # Ждем новые строки
                    continue
                await websocket.send_text(line.strip())
    except FileNotFoundError:
        logger.error(f"Файл лога не найден: {LOG_FILE_PATH}")
        await websocket.send_text(f"ОШИБКА: Файл лога не найден: {LOG_FILE_PATH}. Убедитесь, что бот запущен и пишет логи.")
    except Exception as e:
        logger.error(f"Ошибка при чтении файла лога: {e}", exc_info=True)
        await websocket.send_text(f"ОШИБКА СЕРВЕРА ПРИ ЧТЕНИИ ЛОГА: {str(e)}")

@app.websocket("/ws/bot_log")
async def websocket_bot_log_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info(f"WebSocket клиент для лога подключен: {websocket.client.host}:{websocket.client.port}")
    try:
        await stream_log_file(websocket)
    except WebSocketDisconnect:
        logger.info(f"WebSocket клиент для лога отключился: {websocket.client}")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка WebSocket для лога: {e}", exc_info=True)
        if websocket.client_state != websocket.client_state.DISCONNECTED: # Проверяем состояние перед закрытием
            try:
                await websocket.close(code=1011)
            except RuntimeError: # Может возникнуть, если соединение уже закрыто
                pass
    finally:
        logger.info(f"Завершение WebSocket сессии для лога клиента: {websocket.client}")