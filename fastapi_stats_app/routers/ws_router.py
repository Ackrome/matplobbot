# fastapi_stats_app/routers/ws_router.py
import asyncio
import datetime
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, WebSocketException, status
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.websockets import WebSocketState

from shared_lib.database import (
    get_action_types_distribution_from_db,
    get_activity_over_time_data_from_db,
    get_leaderboard_data_from_db,
    get_new_users_per_day_from_db,
    get_popular_commands_data_from_db,
    get_popular_messages_data_from_db,
    get_session,
)
from shared_lib.models import WebAccount
from shared_lib.redis_client import redis_client

from ..auth import get_ws_user, require_ws_admin, resolve_account_role

router = APIRouter()
logger = logging.getLogger(__name__)


async def websocket_account_is_active(
    user: dict, *, admin_only: bool = False, target_user_id: int | None = None,
) -> bool:
    """Recheck the live DB identity with a bounded timeout, including after deletion."""
    try:
        async with asyncio.timeout(2):
            async with get_session() as session:
                account = (await session.execute(select(WebAccount).where(
                    WebAccount.id == user["id"]
                ))).scalar_one_or_none()
        if account is None:
            return False
        role = resolve_account_role(account)
        if admin_only and role != "admin":
            return False
        return target_user_id is None or role == "admin" or account.telegram_id == target_user_id
    except Exception:
        logger.warning("WebSocket identity could not be revalidated; closing stream")
        return False


class ConnectionManager:
    def __init__(self, name: str = "default"):
        self.active_connections: set[WebSocket] = set()
        self.name = name
        self.identities: dict[WebSocket, dict] = {}
        self.guards: dict[WebSocket, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, user: dict, *, admin_only=False, target_user_id=None):
        await websocket.accept()
        self.active_connections.add(websocket)
        self.identities[websocket] = {
            "user": user, "admin_only": admin_only, "target_user_id": target_user_id,
        }
        self.guards[websocket] = asyncio.create_task(self._watch_identity(websocket))
        logger.info(
            f"WS Manager '{self.name}': Client connected {websocket.client}. Total: {len(self.active_connections)}"
        )

    async def disconnect(self, websocket: WebSocket):
        self.identities.pop(websocket, None)
        guard = self.guards.pop(websocket, None)
        if guard and guard is not asyncio.current_task():
            guard.cancel()
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(
                f"WS Manager '{self.name}': Client disconnected {websocket.client}. Remaining: {len(self.active_connections)}"
            )

    async def _authorized(self, websocket: WebSocket) -> bool:
        identity = self.identities.get(websocket)
        if identity and await websocket_account_is_active(**identity):
            return True
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except RuntimeError:
            pass  # Another send/guard may already have closed this socket.
        finally:
            await self.disconnect(websocket)
        return False

    async def _watch_identity(self, websocket: WebSocket):
        while websocket in self.active_connections:
            await asyncio.sleep(15)
            if not await self._authorized(websocket):
                return

    async def send_personal_json(self, data: dict[str, Any], websocket: WebSocket) -> bool:
        if websocket.client_state == WebSocketState.CONNECTED:
            if not await self._authorized(websocket):
                return False
            try:
                await websocket.send_json(data)
                return True
            except Exception as e:
                logger.error(
                    f"WS Manager '{self.name}': Error sending JSON to {websocket.client}: {e}"
                )
                await self.disconnect(websocket)
                return False
        return False

    async def send_personal_text(self, message: str, websocket: WebSocket) -> bool:
        if websocket.client_state == WebSocketState.CONNECTED:
            if not await self._authorized(websocket):
                return False
            try:
                await websocket.send_text(message)
                return True
            except Exception:
                await self.disconnect(websocket)
                return False
        return False

    async def broadcast_json(self, data: dict[str, Any]):
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
STATS_MIN_POLL_SECONDS = 10
STATS_MAX_IDLE_POLL_SECONDS = 15


def can_subscribe_user_updates(user: dict, target_user_id: int) -> bool:
    return user.get("role") == "admin" or user.get("telegram_id") == target_user_id


async def periodic_stats_updater():
    global last_sent_stats_data_str, last_checked_actions_count
    logger.info("Starting periodic_stats_updater task.")
    idle_sleep_seconds = STATS_MIN_POLL_SECONDS

    while True:
        try:
            if not stats_manager.active_connections:
                idle_sleep_seconds = STATS_MIN_POLL_SECONDS
                await asyncio.sleep(5)
                continue

            async with get_session() as db:
                result = await db.execute(text("SELECT COUNT(*) FROM user_actions"))
                current_actions = result.scalar() or 0

                if current_actions == last_checked_actions_count:
                    await asyncio.sleep(idle_sleep_seconds)
                    idle_sleep_seconds = min(idle_sleep_seconds * 2, STATS_MAX_IDLE_POLL_SECONDS)
                    continue

                idle_sleep_seconds = STATS_MIN_POLL_SECONDS
                last_checked_actions_count = current_actions

                leaderboard_data = await get_leaderboard_data_from_db(db)
                popular_commands_data = await get_popular_commands_data_from_db(db)
                popular_messages_data = await get_popular_messages_data_from_db(db)
                action_types_data = await get_action_types_distribution_from_db(db)

                activity_over_time_data = {
                    "day": await get_activity_over_time_data_from_db(db, period="day"),
                    "week": await get_activity_over_time_data_from_db(db, period="week"),
                    "month": await get_activity_over_time_data_from_db(db, period="month"),
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
                "last_updated": datetime.datetime.now().isoformat(),
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

        await asyncio.sleep(STATS_MIN_POLL_SECONDS)


@router.websocket("/ws/stats/total_actions")
async def websocket_total_actions_endpoint(
    websocket: WebSocket,
    user: dict = Depends(require_ws_admin),
):
    global stats_update_task

    await stats_manager.connect(websocket, user, admin_only=True)

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
    await manager.send_personal_text(
        "File-based bot log streaming is disabled. Use `docker compose logs -f "
        "mpb-telegram-bot` or the Docker logging driver output instead.",
        websocket,
    )


@router.websocket("/ws/bot_log")
async def websocket_bot_log_endpoint(websocket: WebSocket, user: dict = Depends(get_ws_user)):
    await log_manager.connect(websocket, user)
    try:
        await stream_log_file_to_websocket(websocket, log_manager)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Bot Log WS Error: {e}")
    finally:
        await log_manager.disconnect(websocket)


@router.websocket("/ws/users/{user_id}")
async def websocket_user_updates(
    websocket: WebSocket, user_id: int, user: dict = Depends(get_ws_user)
):
    if not can_subscribe_user_updates(user, user_id):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    manager = ConnectionManager(name="user_updates")
    await manager.connect(websocket, user, target_user_id=user_id)

    pubsub = redis_client.client.pubsub()
    channel_name = f"user_updates:{user_id}"

    try:
        await pubsub.subscribe(channel_name)
        while websocket in manager.active_connections:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                if not await manager.send_personal_text(message["data"], websocket):
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Error in user updates WS: {e}")
    finally:
        await manager.disconnect(websocket)
        await pubsub.unsubscribe(channel_name)
        await pubsub.close()
