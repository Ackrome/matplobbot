import logging
import json
import os
import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, update, delete, insert, func, text, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .models import (
    User, UserAction, UserFavorite, LatexCache, UserGithubRepo, 
    UserScheduleSubscription, ChatSettings, DisciplineShortName, 
    UserDisabledShortName, CachedSchedule, SearchDocument
)
from .redis_client import redis_client

logger = logging.getLogger(__name__)

# --- PostgreSQL Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    
# Global Engine & SessionMaker
async_engine = None
async_session_factory = None

async def init_db_pool():
    global async_engine, async_session_factory
    if async_engine is None:
        if not DATABASE_URL:
            logger.critical("DATABASE_URL is not set.")
            raise ValueError("DATABASE_URL is not set.")
        
        # SQLAlchemy Async Engine
        async_engine = create_async_engine(
            DATABASE_URL,
            echo=False, # Set True for SQL debugging
            pool_size=20,
            max_overflow=10
        )
        async_session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
        logger.info("Shared DB: SQLAlchemy Async Engine initialized.")

async def close_db_pool():
    global async_engine
    if async_engine:
        await async_engine.dispose()
        logger.info("Shared DB: SQLAlchemy Async Engine disposed.")

class SubscriptionConflictError(Exception):
    pass

# Context Manager для получения сессии (используется внутри функций ниже)
def get_session() -> AsyncSession:
    if async_session_factory is None:
        raise ConnectionError("Database not initialized. Call init_db_pool() first.")
    return async_session_factory()

# Вспомогательная функция для FastAPI (Dependency Injection)
async def get_db_session_dependency():
    async with get_session() as session:
        yield session

# --- User Settings Defaults ---
DEFAULT_SETTINGS = {
    'show_docstring': True,
    'latex_padding': 15,
    'md_display_mode': 'md_file',
    'latex_dpi': 300,
    'language': 'en',
    'show_schedule_emojis': True,
    'show_lecturer_emails': True, 
    'use_short_names': True,
    'admin_daily_summary_time': '09:00',
    'admin_summary_days': [0, 1, 2, 3, 4],
}


async def log_user_action(user_id: int, username: str | None, full_name: str | None, avatar_pic_url: str | None, action_type: str, action_details: str | None):
    async with get_session() as session:
        async with session.begin():
            # 1. СНАЧАЛА создаем или обновляем пользователя (Parent table)
            if full_name and full_name not in ["Admin", "System"]:
                stmt = pg_insert(User).values(
                    user_id=user_id,
                    username=username,
                    full_name=full_name,
                    avatar_pic_url=avatar_pic_url
                ).on_conflict_do_update(
                    index_elements=['user_id'],
                    set_=dict(
                        username=username,
                        full_name=full_name,
                        avatar_pic_url=avatar_pic_url
                    )
                )
            else:
                # Если это просто ID без данных (например, из callback), убедимся, что запись есть
                stmt = pg_insert(User).values(
                    user_id=user_id,
                    full_name='Unknown User'
                ).on_conflict_do_nothing()
            
            await session.execute(stmt)
            # Важно: flush не обязателен здесь, так как мы используем execute, 
            # но пользователь должен существовать до вставки action.

            # 2. ТЕПЕРЬ вставляем действие (Child table)
            new_action = UserAction(
                user_id=user_id,
                action_type=action_type,
                action_details=action_details
            )
            session.add(new_action)
            await session.flush() # Получаем ID и Timestamp

            # Prepare payload for Redis
            payload = {
                "id": new_action.id,
                "action_type": action_type,
                "action_details": action_details,
                "timestamp": new_action.timestamp.isoformat() if new_action.timestamp else datetime.datetime.now().isoformat()
            }
        
        # 3. Publish to Redis (after commit)
        try:
            await redis_client.client.publish(f"user_updates:{user_id}", json.dumps(payload))
        except Exception as e:
            logger.error(f"Redis publish error: {e}")

async def get_user_settings(user_id: int) -> dict:
    async with get_session() as session:
        result = await session.execute(select(User.settings).where(User.user_id == user_id))
        db_settings = result.scalar() or {}
        
    merged = DEFAULT_SETTINGS.copy()
    merged.update(db_settings)
    return merged

async def get_chat_settings(chat_id: int) -> dict:
    async with get_session() as session:
        # Upsert pattern via insert().on_conflict_do_nothing is cleaner, but simple select/insert works too
        stmt = pg_insert(ChatSettings).values(chat_id=chat_id).on_conflict_do_nothing()
        await session.execute(stmt)
        await session.commit()

        result = await session.execute(select(ChatSettings.settings).where(ChatSettings.chat_id == chat_id))
        db_settings = result.scalar() or {}

    merged = DEFAULT_SETTINGS.copy()
    merged.update(db_settings)
    return merged

async def update_user_settings_db(user_id: int, settings: dict):
    async with get_session() as session:
        await session.execute(
            update(User).where(User.user_id == user_id).values(settings=settings)
        )
        await session.commit()

async def update_chat_settings_db(chat_id: int, settings: dict):
    async with get_session() as session:
        await session.execute(
            update(ChatSettings).where(ChatSettings.chat_id == chat_id).values(settings=settings)
        )
        await session.commit()

async def delete_all_user_data(user_id: int) -> bool:
    async with get_session() as session:
        # Cascade handling relies on DB schema constraints
        result = await session.execute(delete(User).where(User.user_id == user_id))
        await session.commit()
        return result.rowcount > 0

async def is_onboarding_completed(user_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(select(User.onboarding_completed).where(User.user_id == user_id))
        return result.scalar() or False

async def set_onboarding_completed(user_id: int):
    async with get_session() as session:
        await session.execute(
            update(User).where(User.user_id == user_id).values(onboarding_completed=True)
        )
        await session.commit()

# --- Favorites ---
async def add_favorite(user_id: int, code_path: str):
    async with get_session() as session:
        stmt = pg_insert(UserFavorite).values(user_id=user_id, code_path=code_path).on_conflict_do_nothing()
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0

async def remove_favorite(user_id: int, code_path: str):
    async with get_session() as session:
        await session.execute(
            delete(UserFavorite).where(
                and_(UserFavorite.user_id == user_id, UserFavorite.code_path == code_path)
            )
        )
        await session.commit()

async def get_favorites(user_id: int) -> list:
    async with get_session() as session:
        result = await session.execute(select(UserFavorite.code_path).where(UserFavorite.user_id == user_id))
        return result.scalars().all()

# --- LaTeX Cache ---
async def clear_latex_cache():
    async with get_session() as session:
        await session.execute(text("TRUNCATE TABLE latex_cache")) # Truncate is faster/cleaner via text
        await session.commit()

# --- GitHub Repos ---
async def add_user_repo(user_id: int, repo_path: str) -> bool:
    async with get_session() as session:
        stmt = pg_insert(UserGithubRepo).values(user_id=user_id, repo_path=repo_path).on_conflict_do_nothing()
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0

async def get_user_repos(user_id: int) -> list[str]:
    async with get_session() as session:
        result = await session.execute(
            select(UserGithubRepo.repo_path)
            .where(UserGithubRepo.user_id == user_id)
            .order_by(UserGithubRepo.added_at.asc())
        )
        return result.scalars().all()

async def remove_user_repo(user_id: int, repo_path: str):
    async with get_session() as session:
        await session.execute(
            delete(UserGithubRepo).where(
                and_(UserGithubRepo.user_id == user_id, UserGithubRepo.repo_path == repo_path)
            )
        )
        await session.commit()

async def update_user_repo(user_id: int, old_repo_path: str, new_repo_path: str):
    async with get_session() as session:
        await session.execute(
            update(UserGithubRepo)
            .where(and_(UserGithubRepo.user_id == user_id, UserGithubRepo.repo_path == old_repo_path))
            .values(repo_path=new_repo_path)
        )
        await session.commit()

# --- Schedule Subscriptions ---
async def add_schedule_subscription(user_id: int, chat_id: int, message_thread_id: int | None, entity_type: str, entity_id: str, entity_name: str, notification_time: datetime.time) -> int | None:
    async with get_session() as session:
        stmt = pg_insert(UserScheduleSubscription).values(
            user_id=user_id,
            chat_id=chat_id,
            message_thread_id=message_thread_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            notification_time=notification_time
        ).on_conflict_do_update(
            constraint='uq_schedule_subs',
            set_=dict(
                entity_name=entity_name,
                is_active=True,
                user_id=user_id
            )
        ).returning(UserScheduleSubscription.id)
        
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar()

async def get_user_subscriptions(user_id: int, page: int = 0, page_size: int = 5) -> tuple[list, int]:
    async with get_session() as session:
        offset = page * page_size
        
        # Count
        count_stmt = select(func.count()).select_from(UserScheduleSubscription).where(UserScheduleSubscription.user_id == user_id)
        total_count = (await session.execute(count_stmt)).scalar() or 0
        
        # Data
        stmt = (
            select(UserScheduleSubscription)
            .where(UserScheduleSubscription.user_id == user_id)
            .order_by(UserScheduleSubscription.entity_name, UserScheduleSubscription.notification_time)
            .limit(page_size)
            .offset(offset)
        )
        result = await session.execute(stmt)
        subs = result.scalars().all()
        
        # Convert to dict to match old API
        return [
            {
                "id": s.id, "user_id": s.user_id, "chat_id": s.chat_id, 
                "entity_type": s.entity_type, "entity_id": s.entity_id, 
                "entity_name": s.entity_name, 
                "notification_time": s.notification_time.strftime('%H:%M'), 
                "is_active": s.is_active
            } 
            for s in subs
        ], total_count

async def get_chat_subscriptions(chat_id: int, page: int = 0, page_size: int = 5) -> tuple[list, int]:
    async with get_session() as session:
        offset = page * page_size
        
        count_stmt = select(func.count()).select_from(UserScheduleSubscription).where(UserScheduleSubscription.chat_id == chat_id)
        total_count = (await session.execute(count_stmt)).scalar() or 0
        
        stmt = (
            select(UserScheduleSubscription)
            .where(UserScheduleSubscription.chat_id == chat_id)
            .order_by(UserScheduleSubscription.entity_name, UserScheduleSubscription.notification_time)
            .limit(page_size)
            .offset(offset)
        )
        result = await session.execute(stmt)
        subs = result.scalars().all()
        
        return [
            {
                "id": s.id, "user_id": s.user_id, "chat_id": s.chat_id, 
                "entity_type": s.entity_type, "entity_id": s.entity_id, 
                "entity_name": s.entity_name, 
                "notification_time": s.notification_time.strftime('%H:%M'), 
                "is_active": s.is_active
            } 
            for s in subs
        ], total_count

async def toggle_subscription_status(subscription_id: int, user_id: int, is_chat_admin: bool = False) -> tuple[bool, str] | None:
    async with get_session() as session:
        if not is_chat_admin:
            owner_check = await session.execute(
                select(UserScheduleSubscription.user_id).where(UserScheduleSubscription.id == subscription_id)
            )
            owner_id = owner_check.scalar()
            if owner_id != user_id:
                return None

        # Fetch the object to update
        sub = await session.get(UserScheduleSubscription, subscription_id)
        if not sub:
            return None
            
        sub.is_active = not sub.is_active
        sub.deactivated_at = func.now() if not sub.is_active else None
        
        await session.commit()
        await session.refresh(sub)
        return sub.is_active, sub.entity_name

async def remove_schedule_subscription(subscription_id: int, user_id: int, is_chat_admin: bool = False) -> str | None:
    async with get_session() as session:
        stmt = delete(UserScheduleSubscription).where(UserScheduleSubscription.id == subscription_id).returning(UserScheduleSubscription.entity_name)
        
        if not is_chat_admin:
            stmt = stmt.where(UserScheduleSubscription.user_id == user_id)
            
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar()

async def update_subscription_notification_time(subscription_id: int, new_time: datetime.time, user_id: int, is_chat_admin: bool = False) -> str | None:
    async with get_session() as session:
        stmt = update(UserScheduleSubscription).where(UserScheduleSubscription.id == subscription_id).values(notification_time=new_time).returning(UserScheduleSubscription.entity_name)
        
        if not is_chat_admin:
            stmt = stmt.where(UserScheduleSubscription.user_id == user_id)
            
        try:
            result = await session.execute(stmt)
            await session.commit()
            return result.scalar()
        except Exception:
            raise SubscriptionConflictError()

async def delete_old_inactive_subscriptions(days_inactive: int = 30):
    async with get_session() as session:
        stmt = delete(UserScheduleSubscription).where(
            and_(
                UserScheduleSubscription.is_active == False,
                UserScheduleSubscription.deactivated_at < datetime.datetime.now() - datetime.timedelta(days=days_inactive)
            )
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount

async def get_subscriptions_for_notification(notification_time: str) -> list:
    async with get_session() as session:
        # notification_time comes as "HH:MM"
        # We use PostgreSQL TO_CHAR on the Time column
        stmt = select(UserScheduleSubscription).where(
            and_(
                UserScheduleSubscription.is_active == True,
                func.to_char(UserScheduleSubscription.notification_time, 'HH24:MI') == notification_time
            )
        )
        result = await session.execute(stmt)
        subs = result.scalars().all()
        # Return list of dicts for compatibility
        return [
            {
                "id": s.id, "user_id": s.user_id, "chat_id": s.chat_id, "message_thread_id": s.message_thread_id,
                "entity_type": s.entity_type, "entity_id": s.entity_id, "entity_name": s.entity_name,
                "last_schedule_hash": s.last_schedule_hash
            } for s in subs
        ]

async def get_all_active_subscriptions() -> list:
    async with get_session() as session:
        stmt = select(UserScheduleSubscription).where(UserScheduleSubscription.is_active == True)
        result = await session.execute(stmt)
        subs = result.scalars().all()
        return [
            {
                "id": s.id, "user_id": s.user_id, "chat_id": s.chat_id, "message_thread_id": s.message_thread_id,
                "entity_type": s.entity_type, "entity_id": s.entity_id, "entity_name": s.entity_name,
                "last_schedule_hash": s.last_schedule_hash
            } for s in subs
        ]

async def get_unique_active_subscription_entities() -> list:
    async with get_session() as session:
        stmt = select(
            UserScheduleSubscription.entity_type, 
            UserScheduleSubscription.entity_id, 
            UserScheduleSubscription.entity_name
        ).where(UserScheduleSubscription.is_active == True).distinct()
        
        result = await session.execute(stmt)
        return [{"entity_type": r[0], "entity_id": r[1], "entity_name": r[2]} for r in result.all()]

async def update_subscription_hash(subscription_id: int, new_hash: str):
    async with get_session() as session:
        await session.execute(
            update(UserScheduleSubscription).where(UserScheduleSubscription.id == subscription_id).values(last_schedule_hash=new_hash)
        )
        await session.commit()

# --- Cached Schedules ---
async def upsert_cached_schedule(entity_type: str, entity_id: str, data: list | dict):
    json_data = json.loads(json.dumps(data, default=str)) # Ensure serializable
    async with get_session() as session:
        stmt = pg_insert(CachedSchedule).values(
            entity_type=entity_type,
            entity_id=str(entity_id),
            schedule_data=json_data,
            updated_at=datetime.datetime.now()
        ).on_conflict_do_update(
            constraint='uq_cached_schedule_entity',
            set_=dict(
                schedule_data=json_data,
                updated_at=datetime.datetime.now()
            )
        )
        await session.execute(stmt)
        await session.commit()

async def get_cached_schedule(entity_type: str, entity_id: str) -> list | None:
    async with get_session() as session:
        result = await session.execute(
            select(CachedSchedule.schedule_data).where(
                and_(CachedSchedule.entity_type == entity_type, CachedSchedule.entity_id == str(entity_id))
            )
        )
        return result.scalar()

# --- Short Names ---
async def add_short_name(full_name: str, short_name: str, admin_id: int):
    async with get_session() as session:
        stmt = pg_insert(DisciplineShortName).values(
            full_name=full_name, short_name=short_name, approved_by=admin_id
        ).on_conflict_do_update(
            index_elements=['full_name'],
            set_=dict(short_name=short_name, approved_by=admin_id, approved_at=datetime.datetime.now())
        )
        await session.execute(stmt)
        await session.commit()

async def get_all_short_names() -> dict[str, str]:
    async with get_session() as session:
        result = await session.execute(select(DisciplineShortName))
        rows = result.scalars().all()
        return {row.full_name: row.short_name for row in rows}

async def get_disabled_short_names_for_user(user_id: int) -> set[int]:
    async with get_session() as session:
        result = await session.execute(select(UserDisabledShortName.short_name_id).where(UserDisabledShortName.user_id == user_id))
        return set(result.scalars().all())

async def toggle_short_name_for_user(user_id: int, short_name_id: int) -> bool:
    async with get_session() as session:
        exists = await session.execute(
            select(UserDisabledShortName).where(
                and_(UserDisabledShortName.user_id == user_id, UserDisabledShortName.short_name_id == short_name_id)
            )
        )
        if exists.scalar():
            await session.execute(
                delete(UserDisabledShortName).where(
                    and_(UserDisabledShortName.user_id == user_id, UserDisabledShortName.short_name_id == short_name_id)
                )
            )
            await session.commit()
            return False
        else:
            await session.execute(
                insert(UserDisabledShortName).values(user_id=user_id, short_name_id=short_name_id)
            )
            await session.commit()
            return True

async def get_all_short_names_with_ids(page: int = 0, page_size: int = 5) -> tuple[list[dict], int]:
    async with get_session() as session:
        offset = page * page_size
        count_stmt = select(func.count()).select_from(DisciplineShortName)
        total_count = (await session.execute(count_stmt)).scalar() or 0
        
        stmt = select(DisciplineShortName).order_by(DisciplineShortName.full_name).limit(page_size).offset(offset)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [{"id": r.id, "full_name": r.full_name, "short_name": r.short_name} for r in rows], total_count

async def delete_short_name_by_id(short_name_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(delete(DisciplineShortName).where(DisciplineShortName.id == short_name_id))
        await session.commit()
        return result.rowcount > 0

# --- Admin & Stats (Complex Queries) ---
# Note: For complex aggregation queries, sometimes using `session.execute(text(...))` is simpler 
# than constructing complex SQLAlchemy expressions, but we will try to be pythonic where possible.

async def get_admin_daily_summary(db_session: AsyncSession) -> dict:
    """Fetches a summary of today's stats for the admin report. Requires passing a session."""
    # We use raw SQL with SQLAlchemy text() because of complex timezone/date logic that is cleaner in SQL
    # But we execute it via the Session.
    
    moscow_tz = 'Europe/Moscow'
    
    new_users_query = text(f"""
        WITH FirstActions AS (
            SELECT user_id, MIN(timestamp AT TIME ZONE '{moscow_tz}') as first_action_time
            FROM user_actions GROUP BY user_id
        )
        SELECT COUNT(user_id) FROM FirstActions WHERE DATE(first_action_time) = CURRENT_DATE;
    """)
    
    total_actions_query = text(f"SELECT COUNT(id) FROM user_actions WHERE DATE(timestamp AT TIME ZONE '{moscow_tz}') = CURRENT_DATE;")
    
    new_suggestions_query = text(f"SELECT COUNT(id) FROM user_actions WHERE action_type = 'suggestion' AND action_details = 'offershorter' AND DATE(timestamp AT TIME ZONE '{moscow_tz}') = CURRENT_DATE;")

    new_subs_query = text(f"SELECT COUNT(id) FROM user_schedule_subscriptions WHERE DATE(added_at AT TIME ZONE '{moscow_tz}') = CURRENT_DATE;")

    new_users = (await db_session.execute(new_users_query)).scalar()
    total_actions = (await db_session.execute(total_actions_query)).scalar()
    new_suggestions = (await db_session.execute(new_suggestions_query)).scalar()
    new_subs = (await db_session.execute(new_subs_query)).scalar()

    return {
        "new_users": new_users, "total_actions": total_actions, 
        "new_subscriptions": new_subs, "new_suggestions": new_suggestions
    }

# --- FastAPI Specific (Dependency Injected Session) ---
# These functions accept a `session` argument, not a connection object.

async def get_leaderboard_data_from_db(session: AsyncSession):
    stmt = text("""
        SELECT
            u.user_id,
            u.full_name,
            COALESCE(u.username, 'N/A') AS username,
            u.avatar_pic_url,
            COUNT(ua.id)::int AS actions_count,
            TO_CHAR(MAX(ua.timestamp AT TIME ZONE 'Europe/Moscow'), 'YYYY-MM-DD HH24:MI:SS') AS last_action_time
        FROM users u
        JOIN user_actions ua ON u.user_id = ua.user_id
        GROUP BY u.user_id, u.full_name, u.username, u.avatar_pic_url
        ORDER BY actions_count DESC LIMIT 100;
    """)
    result = await session.execute(stmt)
    return [dict(row._mapping) for row in result]

async def get_popular_commands_data_from_db(session: AsyncSession):
    stmt = text("""
        SELECT action_details as command, COUNT(id) as command_count FROM user_actions
        WHERE action_type = 'command' GROUP BY action_details ORDER BY command_count DESC LIMIT 10;
    """)
    result = await session.execute(stmt)
    return [dict(row._mapping) for row in result]

async def get_popular_messages_data_from_db(session: AsyncSession):
    stmt = text("""
        SELECT CASE WHEN LENGTH(action_details) > 30 THEN SUBSTR(action_details, 1, 27) || '...' ELSE action_details END as message_snippet,
        COUNT(id) as message_count FROM user_actions
        WHERE action_type = 'text_message' AND action_details IS NOT NULL AND action_details != ''
        GROUP BY message_snippet ORDER BY message_count DESC LIMIT 10;
    """)
    result = await session.execute(stmt)
    return [dict(row._mapping) for row in result]

async def get_action_types_distribution_from_db(session: AsyncSession):
    stmt = text("SELECT action_type, COUNT(id) as type_count FROM user_actions GROUP BY action_type ORDER BY type_count DESC;")
    result = await session.execute(stmt)
    return [dict(row._mapping) for row in result]

async def get_activity_over_time_data_from_db(session: AsyncSession, period='day'):
    date_format = {'day': 'YYYY-MM-DD', 'week': 'IYYY-IW', 'month': 'YYYY-MM'}.get(period, 'YYYY-MM-DD')
    stmt = text(f"""
        SELECT TO_CHAR(timestamp AT TIME ZONE 'Europe/Moscow', '{date_format}') as period_start, COUNT(id) as actions_count 
        FROM user_actions GROUP BY period_start ORDER BY period_start ASC;
    """)
    result = await session.execute(stmt)
    return [dict(row._mapping) for row in result]

async def get_new_users_per_day_from_db(session: AsyncSession):
    stmt = text("""
        WITH FirstActions AS (
            SELECT user_id, MIN(timestamp) as first_action_time
            FROM user_actions GROUP BY user_id
        )
        SELECT
            TO_CHAR(first_action_time AT TIME ZONE 'Europe/Moscow', 'YYYY-MM-DD') as registration_date,
            COUNT(user_id)::int as new_users_count
        FROM FirstActions
        GROUP BY registration_date
        ORDER BY registration_date ASC;
    """)
    result = await session.execute(stmt)
    return [dict(row._mapping) for row in result]

async def get_user_profile_data_from_db(session: AsyncSession, user_id: int, page: int = 1, page_size: int = 50, sort_by: str = 'timestamp', sort_order: str = 'desc'):
    # User Details
    user_stmt = select(User).where(User.user_id == user_id)
    user = (await session.execute(user_stmt)).scalar_one_or_none()
    
    if not user:
        return None

    count_stmt = select(func.count()).select_from(UserAction).where(UserAction.user_id == user_id)
    total_actions = (await session.execute(count_stmt)).scalar() or 0

    # Actions List
    valid_sort_cols = {'id': UserAction.id, 'action_type': UserAction.action_type, 'action_details': UserAction.action_details, 'timestamp': UserAction.timestamp}
    sort_col = valid_sort_cols.get(sort_by, UserAction.timestamp)
    order_clause = sort_col.desc() if sort_order.lower() == 'desc' else sort_col.asc()

    stmt = (
        select(UserAction.id, UserAction.action_type, UserAction.action_details, UserAction.timestamp)
        .where(UserAction.user_id == user_id)
        .order_by(order_clause)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    
    rows = await session.execute(stmt)
    actions = []
    for r in rows:
        actions.append({
            "id": r.id, "action_type": r.action_type, "action_details": r.action_details,
            # Formatting manually or in SQL? Let's do in Python to keep SA usage clean
            "timestamp": r.timestamp.strftime('%Y-%m-%d %H:%M:%S') # simplistic TZ handling
        })

    user_details = {
        "user_id": user.user_id,
        "full_name": user.full_name,
        "username": user.username or "Нет username",
        "avatar_pic_url": user.avatar_pic_url,
        "total_actions": total_actions
    }

    return {"user_details": user_details, "actions": actions, "total_actions": total_actions}

async def get_users_for_action(session: AsyncSession, action_type: str, action_details: str, page: int = 1, page_size: int = 15, sort_by: str = 'full_name', sort_order: str = 'asc'):
    db_action_type = 'text_message' if action_type == 'message' else action_type
    
    # Using raw SQL for complex aggregation grouping logic is often simpler/faster to write correctly
    # than debugging SA group_by logic unless using strict ORM models relationships.
    # We will stick to the previous optimized logic but execute via SA session.
    
    safe_sort = sort_by if sort_by in ['user_id', 'full_name', 'username'] else 'full_name'
    safe_order = sort_order if sort_order.lower() in ['asc', 'desc'] else 'asc'
    
    count_sql = text("SELECT COUNT(DISTINCT user_id) FROM user_actions WHERE action_type = :atype AND action_details = :adet")
    total_users = (await session.execute(count_sql, {"atype": db_action_type, "adet": action_details})).scalar()

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
    
    result = await session.execute(sql, {
        "atype": db_action_type, "adet": action_details, 
        "limit": page_size, "offset": (page - 1) * page_size
    })
    
    return {"users": [dict(r._mapping) for r in result], "total_users": total_users}

async def get_all_user_actions(session: AsyncSession, user_id: int):
    stmt = (
        select(UserAction.id, UserAction.action_type, UserAction.action_details, UserAction.timestamp)
        .where(UserAction.user_id == user_id)
        .order_by(UserAction.timestamp.desc())
    )
    result = await session.execute(stmt)
    return [
        {"id": r.id, "action_type": r.action_type, "action_details": r.action_details, "timestamp": r.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
        for r in result
    ]