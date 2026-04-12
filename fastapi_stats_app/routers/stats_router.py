# fastapi_stats_app/routers/stats_router.py
import csv
import html
import json
import logging
import math
import os
from datetime import UTC, date, datetime, time, timedelta
from email.utils import format_datetime
from io import StringIO
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
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
from shared_lib.egress import get_telegram_proxy_url
from shared_lib.redis_client import redis_client
from shared_lib.request_context import generate_correlation_id, get_correlation_id
from shared_lib.schemas import (
    ActionUsersResponse,
    SendMessageRequest,
    UserProfileResponse,
)
from shared_lib.telegram_http import build_telegram_http_client_config

from ..auth import require_admin

router = APIRouter(prefix="/stats", tags=["stats"])
logger = logging.getLogger(__name__)

CACHE_TTL = 300
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPPORTED_USER_EXPORT_FORMATS = {"json", "csv", "weekly_pdf"}
PROFILE_SORT_BY_ALLOWED = ("id", "action_type", "action_details", "timestamp")
ACTION_USERS_SORT_BY_ALLOWED = ("user_id", "full_name", "username")
SORT_ORDER_ALLOWED = ("asc", "desc")
ADMIN_SEND_MESSAGE_RATE_LIMIT_PER_MINUTE = int(os.getenv("ADMIN_SEND_MESSAGE_RATE_LIMIT", "12"))
ADMIN_SEND_MESSAGE_WINDOW_SECONDS = 60
DEFAULT_EXPORT_TIMEZONE = "UTC"
LEGACY_ACTION_USERS_ALIAS_ENABLED = os.getenv(
    "ENABLE_LEGACY_ACTION_USERS_ALIAS", "true"
).strip().lower() not in {"0", "false", "no", "off"}
LEGACY_ACTION_USERS_ALIAS_SUNSET_DATE = date(2026, 7, 1)
LEGACY_ACTION_USERS_ALIAS_DOC_URL = (
    "https://github.com/Ackrome/matplobbot/blob/main/docs/wiki.md#stats-action-users-endpoint"
)


def _resolve_correlation_id(request: Request) -> str:
    from_context = get_correlation_id()
    if from_context and from_context != "-":
        return from_context
    from_header = (request.headers.get("X-Request-ID") or "").strip()
    if from_header:
        return from_header
    return generate_correlation_id(prefix="http-fallback")


def _resolve_admin_id(current_user: dict | None) -> int | str:
    if not current_user:
        return "unknown"
    return current_user.get("telegram_id") or current_user.get("id") or "unknown"


async def _enforce_send_message_rate_limit(admin_id: int | str) -> None:
    bucket = int(datetime.now(UTC).timestamp()) // ADMIN_SEND_MESSAGE_WINDOW_SECONDS
    rate_key = f"rate_limit:stats:send_message:{admin_id}:{bucket}"

    try:
        current_count = await redis_client.client.incr(rate_key)
        if current_count == 1:
            await redis_client.client.expire(rate_key, ADMIN_SEND_MESSAGE_WINDOW_SECONDS + 1)
    except Exception as exc:
        logger.warning(
            "Rate limit backend unavailable for admin send_message (admin_id=%s): %s",
            admin_id,
            exc,
        )
        return

    if current_count > ADMIN_SEND_MESSAGE_RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail=(
                "Rate limit exceeded for admin send_message. "
                f"Try again in about {ADMIN_SEND_MESSAGE_WINDOW_SECONDS} seconds."
            ),
        )


def _emit_admin_send_audit(
    *,
    admin_id: int | str,
    target_id: int,
    correlation_id: str,
    timestamp: datetime,
    result: str,
    error: str | None = None,
) -> None:
    payload = {
        "admin_id": admin_id,
        "target_id": target_id,
        "timestamp": timestamp.isoformat(),
        "result": result,
        "correlation_id": correlation_id,
    }
    if error:
        payload["error"] = error
    logger.info(
        "admin_send_message_audit=%s", json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )


def _parse_export_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _resolve_export_timezone(timezone_name: str | None) -> ZoneInfo:
    normalized = (timezone_name or DEFAULT_EXPORT_TIMEZONE).strip() or DEFAULT_EXPORT_TIMEZONE
    try:
        return ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported timezone '{timezone_name}'. "
                "Use an IANA timezone like UTC, Europe/Moscow, or America/New_York."
            ),
        ) from exc


def _filter_actions_by_date_range(
    actions: list[dict[str, Any]],
    *,
    date_from: date | None,
    date_to: date | None,
    timezone: ZoneInfo,
) -> list[dict[str, Any]]:
    if not date_from and not date_to:
        return list(actions)

    filtered_actions: list[dict[str, Any]] = []
    for action in actions:
        parsed = _parse_export_timestamp(str(action.get("timestamp") or ""))
        if parsed is None:
            continue
        local_date = parsed.astimezone(timezone).date()
        if date_from and local_date < date_from:
            continue
        if date_to and local_date > date_to:
            continue
        filtered_actions.append(action)
    return filtered_actions


def _build_legacy_action_users_deprecation_headers() -> dict[str, str]:
    sunset_dt = datetime.combine(LEGACY_ACTION_USERS_ALIAS_SUNSET_DATE, time(), tzinfo=UTC)
    return {
        "Deprecation": "true",
        "Sunset": format_datetime(sunset_dt),
        "Link": f'<{LEGACY_ACTION_USERS_ALIAS_DOC_URL}>; rel="deprecation"',
        "Warning": (
            '299 - "Legacy endpoint /api/stats/stats/action_users is deprecated. '
            'Use /api/stats/action_users instead."'
        ),
    }


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
    week_start_date: date,
    week_end_date: date,
    timezone_name: str,
    weekly_actions: list[dict[str, Any]],
) -> str:
    action_type_counts: dict[str, int] = {}
    for action in weekly_actions:
        action_type = str(action.get("action_type") or "unknown")
        action_type_counts[action_type] = action_type_counts.get(action_type, 0) + 1

    summary_rows = "".join(
        ("<tr>" f"<td>{html.escape(action_type)}</td>" f"<td>{count}</td>" "</tr>")
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

    period_label = f"{week_start_date.strftime('%Y-%m-%d')} - {week_end_date.strftime('%Y-%m-%d')}"
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
  <div class="meta">User ID: {user_id}<br/>Period: {period_label}<br/>Timezone: {html.escape(timezone_name)}<br/>Total actions: {len(weekly_actions)}</div>

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
    description="Checks service availability and database connectivity.",
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
    summary="User profile",
    description="Returns user details and action history with pagination.",
    response_model=UserProfileResponse,
    dependencies=[Depends(require_admin)],
)
async def get_user_profile(
    user_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Page size"),
    sort_by: Literal["id", "action_type", "action_details", "timestamp"] = Query(
        "timestamp",
        description="Allowed: id, action_type, action_details, timestamp",
    ),
    sort_order: Literal["asc", "desc"] = Query(
        "desc",
        description="Allowed: asc, desc",
    ),
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
            raise HTTPException(status_code=404, detail="User not found.")

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


async def _get_action_users_impl(
    action_type: str = Query(..., description="Action type"),
    action_details: str = Query(..., description="Action details"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(15, ge=1, le=100, description="Page size"),
    sort_by: Literal["user_id", "full_name", "username"] = Query(
        "full_name",
        description="Allowed: user_id, full_name, username",
    ),
    sort_order: Literal["asc", "desc"] = Query(
        "asc",
        description="Allowed: asc, desc",
    ),
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
    "/action_users",
    summary="Users by action",
    description="Returns users who performed the selected action with pagination and sorting.",
    response_model=ActionUsersResponse,
    dependencies=[Depends(require_admin)],
)
async def get_action_users(
    action_type: str = Query(..., description="Action type"),
    action_details: str = Query(..., description="Action details"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(15, ge=1, le=100, description="Page size"),
    sort_by: Literal["user_id", "full_name", "username"] = Query(
        "full_name",
        description="Allowed: user_id, full_name, username",
    ),
    sort_order: Literal["asc", "desc"] = Query(
        "asc",
        description="Allowed: asc, desc",
    ),
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Any:
    return await _get_action_users_impl(
        action_type=action_type,
        action_details=action_details,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        db=db,
    )


@router.get(
    "/stats/action_users",
    include_in_schema=False,
    response_model=ActionUsersResponse,
    dependencies=[Depends(require_admin)],
)
async def get_action_users_legacy_alias(
    response: Response,
    action_type: str = Query(..., description="Action type"),
    action_details: str = Query(..., description="Action details"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(15, ge=1, le=100, description="Page size"),
    sort_by: Literal["user_id", "full_name", "username"] = Query(
        "full_name",
        description="Allowed: user_id, full_name, username",
    ),
    sort_order: Literal["asc", "desc"] = Query(
        "asc",
        description="Allowed: asc, desc",
    ),
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Any:
    if not LEGACY_ACTION_USERS_ALIAS_ENABLED:
        raise HTTPException(
            status_code=410,
            detail=(
                "Legacy endpoint /api/stats/stats/action_users has been removed. "
                "Use /api/stats/action_users."
            ),
        )

    for header_name, header_value in _build_legacy_action_users_deprecation_headers().items():
        response.headers[header_name] = header_value

    logger.warning(
        "Legacy endpoint /api/stats/stats/action_users is deprecated and will be removed after %s.",
        LEGACY_ACTION_USERS_ALIAS_SUNSET_DATE.isoformat(),
    )

    return await _get_action_users_impl(
        action_type=action_type,
        action_details=action_details,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        db=db,
    )


@router.get(
    "/users/{user_id}/export_actions",
    summary="Export user actions",
    description=(
        "Exports user actions in JSON, CSV, or PDF. "
        "Optional date range and timezone filters are applied before export."
    ),
    response_model=None,
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
    date_from: date | None = Query(
        None,
        description="Inclusive start date in YYYY-MM-DD for export filtering.",
    ),
    date_to: date | None = Query(
        None,
        description="Inclusive end date in YYYY-MM-DD for export filtering.",
    ),
    timezone: str = Query(
        DEFAULT_EXPORT_TIMEZONE,
        description="IANA timezone used when applying date range filters.",
    ),
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Any | Response:
    normalized_format = format.strip().lower()
    if normalized_format not in SUPPORTED_USER_EXPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported export format '{format}'. Use one of: {sorted(SUPPORTED_USER_EXPORT_FORMATS)}",
        )

    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=400,
            detail="Invalid date range: date_from must be before or equal to date_to.",
        )

    export_timezone = _resolve_export_timezone(timezone)

    try:
        actions = await get_all_user_actions(db, user_id)
    except Exception as e:
        logger.error(f"Database error exporting actions for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Database Error")

    effective_date_from = date_from
    effective_date_to = date_to
    if normalized_format == "weekly_pdf" and not effective_date_from and not effective_date_to:
        timezone_today = datetime.now(UTC).astimezone(export_timezone).date()
        effective_date_to = timezone_today
        effective_date_from = timezone_today - timedelta(days=6)

    filtered_actions = _filter_actions_by_date_range(
        actions,
        date_from=effective_date_from,
        date_to=effective_date_to,
        timezone=export_timezone,
    )

    if normalized_format == "json":
        payload = {"actions": filtered_actions}
        if not download:
            return payload
        filename = f"user_{user_id}_actions.json"
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    if normalized_format == "csv":
        csv_content = _build_actions_csv(filtered_actions)
        filename = f"user_{user_id}_actions.csv"
        return Response(
            content=csv_content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    period_start = effective_date_from or datetime.now(UTC).astimezone(export_timezone).date()
    period_end = effective_date_to or period_start
    weekly_actions = list(filtered_actions)
    weekly_actions.sort(
        key=lambda action: _parse_export_timestamp(str(action.get("timestamp") or ""))
        or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    weekly_html = _build_weekly_pdf_html(
        user_id=user_id,
        week_start_date=period_start,
        week_end_date=period_end,
        timezone_name=str(export_timezone),
        weekly_actions=weekly_actions,
    )
    pdf_bytes = _build_weekly_pdf_bytes(weekly_html)
    filename = f"user_{user_id}_actions_{period_start.strftime('%Y%m%d')}_{period_end.strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/users/{user_id}/send_message",
    summary="Send message to user",
    description="Sends a Telegram message and stores it as an outgoing admin action.",
    status_code=status.HTTP_200_OK,
)
async def send_message_to_user(
    user_id: int,
    message_data: SendMessageRequest,
    request: Request,
    current_user: dict = Depends(require_admin),
):
    request_timestamp = datetime.now(UTC)
    correlation_id = _resolve_correlation_id(request)
    admin_id = _resolve_admin_id(current_user)

    if not BOT_TOKEN:
        _emit_admin_send_audit(
            admin_id=admin_id,
            target_id=user_id,
            correlation_id=correlation_id,
            timestamp=request_timestamp,
            result="server_misconfigured",
            error="BOT_TOKEN is not configured",
        )
        raise HTTPException(status_code=500, detail="BOT_TOKEN is not configured on the server.")

    text = message_data.text.strip()
    if not text:
        _emit_admin_send_audit(
            admin_id=admin_id,
            target_id=user_id,
            correlation_id=correlation_id,
            timestamp=request_timestamp,
            result="validation_failed",
            error="message text is empty",
        )
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        await _enforce_send_message_rate_limit(admin_id)
    except HTTPException as exc:
        _emit_admin_send_audit(
            admin_id=admin_id,
            target_id=user_id,
            correlation_id=correlation_id,
            timestamp=request_timestamp,
            result="rate_limited",
            error=str(exc.detail),
        )
        raise

    tg_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": user_id, "text": text, "parse_mode": "HTML"}

    try:
        timeout = aiohttp.ClientTimeout(total=60)
        session_kwargs, request_kwargs = build_telegram_http_client_config(
            timeout,
            get_telegram_proxy_url(),
            log_context="stats Telegram send",
        )
        async with aiohttp.ClientSession(**session_kwargs) as session:
            async with session.post(tg_url, json=payload, **request_kwargs) as response:
                if response.status != 200:
                    error_text = await response.text()
                    _emit_admin_send_audit(
                        admin_id=admin_id,
                        target_id=user_id,
                        correlation_id=correlation_id,
                        timestamp=request_timestamp,
                        result="telegram_error",
                        error=error_text[:500],
                    )
                    logger.error(f"Failed to send message to {user_id}: {error_text}")
                    raise HTTPException(status_code=400, detail=f"Telegram API Error: {error_text}")

    except aiohttp.ClientError as e:
        _emit_admin_send_audit(
            admin_id=admin_id,
            target_id=user_id,
            correlation_id=correlation_id,
            timestamp=request_timestamp,
            result="network_error",
            error=str(e),
        )
        logger.error(f"Network error sending message to {user_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Network error while sending message to Telegram"
        )

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

    _emit_admin_send_audit(
        admin_id=admin_id,
        target_id=user_id,
        correlation_id=correlation_id,
        timestamp=request_timestamp,
        result="success",
    )
    return {"status": "success", "correlation_id": correlation_id}


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
