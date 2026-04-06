# fastapi_stats_app/routers/stats_router.py
import csv
import html
import json
import logging
import math
import os
from datetime import UTC, datetime, timedelta
from io import StringIO
from typing import Any

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared_lib.database import (
    get_activity_over_time_data_from_db,
    get_all_user_actions,
    get_db_session_dependency,
    get_leaderboard_data_from_db,
    get_session,
    get_user_profile_data_from_db,
    get_users_for_action,
    log_user_action,
)
from shared_lib.redis_client import redis_client
from shared_lib.schemas import (
    ActionUsersResponse,
    SendMessageRequest,
    UserProfileResponse,
)

from ..auth import require_admin

router = APIRouter(prefix="/stats", tags=["stats"])
logger = logging.getLogger(__name__)

CACHE_TTL = 300
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPPORTED_USER_EXPORT_FORMATS = {"json", "csv", "weekly_pdf"}


def _parse_export_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _build_actions_csv(actions: list[dict[str, Any]]) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["id", "action_type", "action_details", "timestamp"])
    for action in actions:
        writer.writerow(
            [
                action.get("id", ""),
                action.get("action_type", ""),
                action.get("action_details", ""),
                action.get("timestamp", ""),
            ]
        )
    # UTF-8 BOM helps spreadsheet apps open Cyrillic data correctly.
    return "\ufeff" + buffer.getvalue()


def _build_weekly_pdf_html(
    *,
    user_id: int,
    week_start_date: datetime,
    week_end_date: datetime,
    weekly_actions: list[dict[str, Any]],
) -> str:
    action_type_counts: dict[str, int] = {}
    for action in weekly_actions:
        action_type = str(action.get("action_type") or "unknown")
        action_type_counts[action_type] = action_type_counts.get(action_type, 0) + 1

    summary_rows = "".join(
        (
            "<tr>"
            f"<td>{html.escape(action_type)}</td>"
            f"<td>{count}</td>"
            "</tr>"
        )
        for action_type, count in sorted(
            action_type_counts.items(), key=lambda item: (-item[1], item[0])
        )
    )
    if not summary_rows:
        summary_rows = "<tr><td colspan='2'>No activity</td></tr>"

    action_rows = "".join(
        (
            "<tr>"
            f"<td>{html.escape(str(action.get('timestamp') or '-'))}</td>"
            f"<td>{html.escape(str(action.get('action_type') or '-'))}</td>"
            f"<td>{html.escape(str(action.get('action_details') or '-'))}</td>"
            "</tr>"
        )
        for action in weekly_actions[:300]
    )
    if not action_rows:
        action_rows = "<tr><td colspan='3'>No actions in this period.</td></tr>"

    period_label = (
        f"{week_start_date.strftime('%Y-%m-%d')} - {week_end_date.strftime('%Y-%m-%d')}"
    )
    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    body {{
      font-family: Arial, sans-serif;
      color: #111827;
      margin: 24px;
      font-size: 12px;
      line-height: 1.35;
    }}
    h1 {{ margin: 0 0 8px; font-size: 20px; }}
    h2 {{ margin: 20px 0 8px; font-size: 14px; }}
    .meta {{ margin-bottom: 12px; color: #4b5563; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 12px;
      table-layout: fixed;
      word-wrap: break-word;
    }}
    th, td {{
      border: 1px solid #d1d5db;
      padding: 6px 8px;
      vertical-align: top;
      text-align: left;
    }}
    th {{
      background: #f3f4f6;
      font-weight: 700;
    }}
  </style>
</head>
<body>
  <h1>Weekly User Activity Report</h1>
  <div class="meta">User ID: {user_id}<br/>Period: {period_label}<br/>Total actions: {len(weekly_actions)}</div>

  <h2>Action Type Summary</h2>
  <table>
    <thead>
      <tr><th style="width: 70%;">Action Type</th><th style="width: 30%;">Count</th></tr>
    </thead>
    <tbody>{summary_rows}</tbody>
  </table>

  <h2>Action Log (up to 300 latest entries)</h2>
  <table>
    <thead>
      <tr>
        <th style="width: 26%;">Timestamp</th>
        <th style="width: 22%;">Type</th>
        <th style="width: 52%;">Details</th>
      </tr>
    </thead>
    <tbody>{action_rows}</tbody>
  </table>
</body>
</html>
"""


def _build_weekly_pdf_bytes(html_content: str) -> bytes:
    try:
        from weasyprint import HTML
    except Exception as error:  # pragma: no cover - environment-dependent import
        raise HTTPException(
            status_code=503,
            detail=f"PDF export is unavailable on this server: {error}",
        ) from error

    try:
        return HTML(string=html_content).write_pdf()
    except Exception as error:  # pragma: no cover - rendering failure
        logger.error("Failed to render weekly stats PDF: %s", error, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to render weekly PDF report") from error


@router.get(
    "/health",
    summary="Health Check",
    description="Проверяет доступность сервиса и подключение к базе данных.",
    response_model=dict[str, str],
    status_code=status.HTTP_200_OK,
)
async def health_check(db: AsyncSession = Depends(get_db_session_dependency)) -> dict[str, str]:
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "error", "database": "disconnected", "reason": str(e)},
        )


@router.get(
    "/users/{user_id}/profile",
    summary="Профиль пользователя",
    description="Возвращает детальную информацию о пользователе и историю его действий с пагинацией.",
    response_model=UserProfileResponse,
    dependencies=[Depends(require_admin)],
)
async def get_user_profile(
    user_id: int,
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(50, ge=1, le=200, description="Размер страницы"),
    sort_by: str = Query("timestamp", description="Поле сортировки"),
    sort_order: str = Query("desc", description="Порядок сортировки"),
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Any:
    cache_key = f"user_profile:{user_id}:p{page}:s{page_size}:{sort_by}:{sort_order}"
    if page > 1:
        try:
            cached_data = await redis_client.get_cache(cache_key)
            if cached_data:
                return cached_data
        except Exception as e:
            logger.warning(f"Redis cache error: {e}")

    try:
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
                "sort_order": sort_order,
            },
        }

        try:
            await redis_client.set_cache(cache_key, response_data, ttl=60)
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
    response_model=ActionUsersResponse,
    dependencies=[Depends(require_admin)],
)
async def get_action_users(
    action_type: str = Query(..., description="Тип действия"),
    action_details: str = Query(..., description="Содержание действия"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(15, ge=1, le=100, description="Размер страницы"),
    sort_by: str = Query("full_name", description="Поле сортировки"),
    sort_order: str = Query("asc", description="Порядок сортировки"),
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Any:
    cache_key = (
        f"action_users:{action_type}:{action_details}:p{page}:s{page_size}:{sort_by}:{sort_order}"
    )
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
                "sort_order": sort_order,
            },
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
    dependencies=[Depends(require_admin)],
)
async def export_user_actions(
    user_id: int,
    format: str = Query(
        "json",
        description="Supported formats: json, csv, weekly_pdf",
    ),
    download: bool = Query(
        False,
        description="When format=json, return a downloadable file instead of JSON payload.",
    ),
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Any | Response:
    normalized_format = format.strip().lower()
    if normalized_format not in SUPPORTED_USER_EXPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported export format '{format}'. Use one of: {sorted(SUPPORTED_USER_EXPORT_FORMATS)}",
        )

    try:
        actions = await get_all_user_actions(db, user_id)
    except Exception as e:
        logger.error(f"Database error exporting actions for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Database Error")

    if normalized_format == "json":
        payload = {"actions": actions}
        if not download:
            return payload
        filename = f"user_{user_id}_actions.json"
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    if normalized_format == "csv":
        csv_content = _build_actions_csv(actions)
        filename = f"user_{user_id}_actions.csv"
        return Response(
            content=csv_content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    week_end = datetime.now(UTC)
    week_start = week_end - timedelta(days=6)
    weekly_actions = [
        action
        for action in actions
        if (parsed := _parse_export_timestamp(str(action.get("timestamp") or "")))
        and week_start.date() <= parsed.date() <= week_end.date()
    ]
    weekly_actions.sort(
        key=lambda action: _parse_export_timestamp(str(action.get("timestamp") or ""))
        or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    weekly_html = _build_weekly_pdf_html(
        user_id=user_id,
        week_start_date=week_start,
        week_end_date=week_end,
        weekly_actions=weekly_actions,
    )
    pdf_bytes = _build_weekly_pdf_bytes(weekly_html)
    filename = f"user_{user_id}_weekly_report_{week_end.strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/users/{user_id}/send_message",
    summary="Отправить сообщение пользователю",
    description="Отправляет сообщение в Telegram и сохраняет его в БД как исходящее от админа.",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
async def send_message_to_user(user_id: int, message_data: SendMessageRequest):
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN не настроен на сервере.")

    text = message_data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Сообщение не может быть пустым")

    tg_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": user_id, "text": text, "parse_mode": "HTML"}

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

    try:
        await log_user_action(
            user_id=user_id,
            username=None,
            full_name="System",
            avatar_pic_url=None,
            action_type="admin_message",
            action_details=text,
        )
    except Exception as e:
        logger.error(f"Error logging admin message to DB for user {user_id}: {e}", exc_info=True)

    return {"status": "success"}


@router.get("/leaderboard")
async def get_leaderboard(current_user: dict = Depends(require_admin)):
    try:
        async with get_session() as db:
            return await get_leaderboard_data_from_db(db)
    except Exception as e:
        logger.error(f"Database error fetching leaderboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Database Error")


@router.get("/activity")
async def get_activity(current_user: dict = Depends(require_admin)):
    try:
        async with get_session() as db:
            return await get_activity_over_time_data_from_db(db, period="day")
    except Exception as e:
        logger.error(f"Database error fetching activity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Database Error")
