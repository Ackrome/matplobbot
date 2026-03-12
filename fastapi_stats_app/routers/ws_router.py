# fastapi_stats_app/routers/ws_router.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from starlette.websockets import WebSocketState
import logging
import asyncio
import aiofiles
import datetime
import json
import os
from typing import Set, Dict, Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from shared_lib.redis_client import redis_client
from shared_lib.models import WebUser

from shared_lib.database import (
    get_session, 
    get_leaderboard_data_from_db,
    get_popular_commands_data_from_db,
    get_popular_messages_data_from_db,
    get_action_types_distribution_from_db,
    get_activity_over_time_data_from_db,
    get_new_users_per_day_from_db
)
from ..config import LOG_DIR, BOT_LOG_FILE_NAME
from ..auth import get_ws_user

router = APIRouter()
logger = logging.getLogger(__name__)

class ConnectionManager:
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
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_text(message)
                return True
            except Exception as e:
                await self.disconnect(websocket)
                return False
        return False

    async def broadcast_json(self, data: Dict[str, Any]):
        if not self.active_connections:
            return
        connections = list(self.active_connections)
        for connection in connections:
            await self.send_personal_json(data, connection)

    async def broadcast_text(self, message: str):
        if not self.active_connections:
            return
        connections = list(self.active_connections)
        for connection in connections:
            await self.send_personal_text(message, connection)

stats_manager = ConnectionManager(name="stats")
log_manager = ConnectionManager(name="bot_log")

stats_update_task: asyncio.Task | None = None
last_sent_stats_data_str: str = ""
last_checked_actions_count: int = -1

async def periodic_stats_updater():
    global last_sent_stats_data_str, last_checked_actions_count
    logger.info("Starting periodic_stats_updater task.")
    
    while True:
        try:
            if not stats_manager.active_connections:
                await asyncio.sleep(5)
                continue

            async with get_session() as db:
                result = await db.execute(text("SELECT COUNT(*) FROM user_actions"))
                current_actions = result.scalar() or 0

                if current_actions == last_checked_actions_count:
                    await asyncio.sleep(2)
                    continue
                
                last_checked_actions_count = current_actions

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

            current_data_json_str = json.dumps(current_data, ensure_ascii=False, sort_keys=True)

            if current_data_json_str != last_sent_stats_data_str:
                await stats_manager.broadcast_json(current_data)
                last_sent_stats_data_str = current_data_json_str

        except SQLAlchemyError as e:
            logger.error(f"StatsUpdater DB Error: {e}")
            await stats_manager.broadcast_json({"error": "Database error fetching stats"})
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"StatsUpdater Unexpected Error: {e}", exc_info=True)
            await stats_manager.broadcast_json({"error": "Internal server error updating stats"})
            await asyncio.sleep(10)
            
        await asyncio.sleep(2)

@router.websocket("/ws/stats/total_actions")
async def websocket_total_actions_endpoint(websocket: WebSocket, user: WebUser = Depends(get_ws_user)):
    global stats_update_task
    
    await stats_manager.connect(websocket)

    if last_sent_stats_data_str:
        try:
            await stats_manager.send_personal_json(json.loads(last_sent_stats_data_str), websocket)
        except Exception as e:
            logger.error(f"Error sending initial stats: {e}")

    if stats_update_task is None or stats_update_task.done():
        stats_update_task = asyncio.create_task(periodic_stats_updater())
    
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await stats_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Stats WS Error: {e}")
        await stats_manager.disconnect(websocket)

async def stream_log_file_to_websocket(websocket: WebSocket, manager: ConnectionManager):
    bot_log_full_path = os.path.join(LOG_DIR, BOT_LOG_FILE_NAME)
    
    try:
        if os.path.exists(bot_log_full_path):
            async with aiofiles.open(bot_log_full_path, mode='r', encoding='utf-8', errors='ignore') as f:
                lines = await f.readlines()
                for line in lines[-50:]:
                    if not await manager.send_personal_text(line.strip(), websocket):
                        return
                
                if not await manager.send_personal_text("--- LIVE LOG STREAM STARTED ---", websocket):
                    return
        else:
            if not await manager.send_personal_text(f"Waiting for log file: {bot_log_full_path}...", websocket):
                return

        while not os.path.exists(bot_log_full_path):
            await asyncio.sleep(2)
            if websocket.client_state != WebSocketState.CONNECTED:
                return

        async with aiofiles.open(bot_log_full_path, mode='r', encoding='utf-8', errors='ignore') as f:
            await f.seek(0, os.SEEK_END)
            
            while websocket.client_state == WebSocketState.CONNECTED:
                line = await f.readline()
                if line:
                    success = await manager.send_personal_text(line.strip(), websocket)
                    if not success:
                        break
                else:
                    await asyncio.sleep(0.5)

    except Exception as e:
        if "Cannot call \"send\"" not in str(e):
            logger.error(f"Log Stream Error: {e}")
            await manager.send_personal_text(f"Error reading log: {str(e)}", websocket)

@router.websocket("/ws/bot_log")
async def websocket_bot_log_endpoint(websocket: WebSocket, user: WebUser = Depends(get_ws_user)):
    await log_manager.connect(websocket)
    try:
        await stream_log_file_to_websocket(websocket, log_manager)
    except WebSocketDisconnect:
        await log_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Bot Log WS Error: {e}")
        await log_manager.disconnect(websocket)
        
@router.websocket("/ws/users/{user_id}")
async def websocket_user_updates(websocket: WebSocket, user_id: int, user: WebUser = Depends(get_ws_user)):
    await websocket.accept()
    
    pubsub = redis_client.client.pubsub()
    channel_name = f"user_updates:{user_id}"
    
    try:
        await pubsub.subscribe(channel_name)
        async for message in pubsub.listen():
            if message['type'] == 'message':
                await websocket.send_text(message['data'])
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Error in user updates WS: {e}")
    finally:
        await pubsub.unsubscribe(channel_name)
        await pubsub.close()