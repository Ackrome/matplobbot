from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User, UserAction


async def get_user_profile_data_from_db(
    session: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "timestamp",
    sort_order: str = "desc",
):
    # User Details
    user_stmt = select(User).where(User.user_id == user_id)
    user = (await session.execute(user_stmt)).scalar_one_or_none()

    if not user:
        return None

    count_stmt = select(func.count()).select_from(UserAction).where(UserAction.user_id == user_id)
    total_actions = (await session.execute(count_stmt)).scalar() or 0

    # Actions List
    valid_sort_cols = {
        "id": UserAction.id,
        "action_type": UserAction.action_type,
        "action_details": UserAction.action_details,
        "timestamp": UserAction.timestamp,
    }
    sort_col = valid_sort_cols.get(sort_by, UserAction.timestamp)
    order_clause = sort_col.desc() if sort_order.lower() == "desc" else sort_col.asc()

    stmt = (
        select(
            UserAction.id, UserAction.action_type, UserAction.action_details, UserAction.timestamp
        )
        .where(UserAction.user_id == user_id)
        .order_by(order_clause)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )

    rows = await session.execute(stmt)
    actions = [
        {
            "id": r.id,
            "action_type": r.action_type,
            "action_details": r.action_details,
            # Formatting manually or in SQL? Let's do in Python to keep SA usage clean
            "timestamp": r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),  # simplistic TZ handling
        }
        for r in rows
    ]

    avatar_url = user.avatar_pic_url
    if avatar_url and "api.telegram.org/file/bot" in avatar_url:
        avatar_url = f"/api/stats/users/{user.user_id}/avatar"

    user_details = {
        "user_id": user.user_id,
        "full_name": user.full_name,
        "username": user.username or "Нет username",
        "avatar_pic_url": avatar_url,
        "total_actions": total_actions,
    }

    return {"user_details": user_details, "actions": actions, "total_actions": total_actions}


async def get_user_message_history(
    session: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 50,
):
    """Return paginated inbound/outbound text messages for one Telegram user.

    The existing ``user_actions`` stream is the source of truth: middleware
    records inbound text/commands as ``text_message``/``command`` and the
    admin send endpoint records outbound messages as ``admin_message``.
    """

    message_types = ("text_message", "command", "admin_message")
    filters = (
        UserAction.user_id == user_id,
        UserAction.action_type.in_(message_types),
    )
    count_stmt = select(func.count()).select_from(UserAction).where(*filters)
    total_messages = int((await session.execute(count_stmt)).scalar() or 0)

    stmt = (
        select(
            UserAction.id,
            UserAction.action_type,
            UserAction.action_details,
            UserAction.timestamp,
        )
        .where(*filters)
        .order_by(UserAction.timestamp.desc(), UserAction.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    rows = await session.execute(stmt)
    messages = [
        {
            "id": row.id,
            "direction": "outgoing" if row.action_type == "admin_message" else "incoming",
            "text": row.action_details or "",
            "timestamp": row.timestamp.isoformat() if row.timestamp else "",
        }
        for row in rows
    ]
    return {"messages": messages, "total_messages": total_messages}


async def get_users_for_action(
    session: AsyncSession,
    action_type: str,
    action_details: str,
    page: int = 1,
    page_size: int = 15,
    sort_by: str = "full_name",
    sort_order: str = "asc",
):
    db_action_type = "text_message" if action_type == "message" else action_type

    # Using raw SQL for complex aggregation grouping logic is often simpler/faster to write correctly
    # than debugging SA group_by logic unless using strict ORM models relationships.
    # We will stick to the previous optimized logic but execute via SA session.

    safe_sort = sort_by if sort_by in ["user_id", "full_name", "username"] else "full_name"
    safe_order = sort_order if sort_order.lower() in ["asc", "desc"] else "asc"

    count_sql = text(
        "SELECT COUNT(DISTINCT user_id) FROM user_actions WHERE action_type = :atype AND action_details = :adet"
    )
    total_users = (
        await session.execute(count_sql, {"atype": db_action_type, "adet": action_details})
    ).scalar()

    sql = text(f"""
        SELECT
            u.user_id,
            u.full_name,
            COALESCE(u.username, 'Нет username') AS username
        FROM users u
        JOIN user_actions ua ON u.user_id = ua.user_id
        WHERE ua.action_type = :atype AND ua.action_details = :adet
        GROUP BY u.user_id, u.full_name, u.username
        ORDER BY u.{safe_sort} {safe_order}
        LIMIT :limit OFFSET :offset
    """)

    result = await session.execute(
        sql,
        {
            "atype": db_action_type,
            "adet": action_details,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        },
    )

    return {"users": [dict(r._mapping) for r in result], "total_users": total_users}


async def get_all_user_actions(session: AsyncSession, user_id: int):
    stmt = (
        select(
            UserAction.id, UserAction.action_type, UserAction.action_details, UserAction.timestamp
        )
        .where(UserAction.user_id == user_id)
        .order_by(UserAction.timestamp.desc())
    )
    result = await session.execute(stmt)
    return [
        {
            "id": r.id,
            "action_type": r.action_type,
            "action_details": r.action_details,
            "timestamp": r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for r in result
    ]
