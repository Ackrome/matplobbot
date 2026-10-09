"""Explicit account export and deletion scopes shared by website and Telegram."""

import asyncio
import base64
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared_lib import models
from shared_lib.redis_client import redis_client

logger = logging.getLogger(__name__)

_PRIVATE_FIELDS = {"password_hash", "credential", "checkpoint", "pending", "calendar_secret", "build_cache"}


def _export_record(record) -> dict:
    """Export database values, excluding credentials and regenerated build artifacts."""
    result = {}
    for column in record.__table__.columns:
        if column.key in _PRIVATE_FIELDS:
            continue
        value = getattr(record, column.key)
        if isinstance(value, bytes):
            value = {"encoding": "base64", "data": base64.b64encode(value).decode("ascii")}
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        result[column.key] = value
    return result


async def get_telegram_web_account(session: AsyncSession, user_id: int):
    result = await session.execute(
        select(models.WebAccount).where(models.WebAccount.telegram_id == user_id)
    )
    return result.scalar_one_or_none()


async def export_account_data(
    session: AsyncSession, *, account_id: int | None = None, telegram_user_id: int | None = None
) -> dict:
    """Export only the resolved owner's data; caller must authenticate that owner."""
    if account_id is not None:
        account = (
            await session.execute(select(models.WebAccount).where(models.WebAccount.id == account_id))
        ).scalar_one_or_none()
        if account is None:
            raise LookupError("Account not found")
        telegram_user_id = account.telegram_id
    elif telegram_user_id is not None:
        account = await get_telegram_web_account(session, telegram_user_id)
        account_id = account.id if account is not None else None
    else:
        raise ValueError("An account owner is required")

    payload = {
        "format_version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "account": _export_record(account) if account is not None else None,
        "telegram_user": None,
        "projects": [],
        "project_files": [],
        "excluded": ["password hashes", "mail credentials and mailbox message cache", "calendar bearer secrets", "generated build cache", "shared public indexes", "operational logs and backups"],
    }
    if account_id is not None:
        for key, model, condition in (
            ("projects", models.Project, models.Project.owner_id == account_id),
            ("project_files", models.ProjectFile, models.ProjectFile.project_id.in_(
                select(models.Project.id).where(models.Project.owner_id == account_id)
            )),
        ):
            rows = (await session.execute(select(model).where(condition))).scalars().all()
            payload[key] = [_export_record(row) for row in rows]

    if telegram_user_id is not None:
        user = (await session.execute(select(models.User).where(
            models.User.user_id == telegram_user_id
        ))).scalar_one_or_none()
        payload["telegram_user"] = _export_record(user) if user is not None else None
        for model in _telegram_owned_models():
            if model is getattr(models, "ProductEvent", None):
                continue
            rows = (await session.execute(select(model).where(
                model.user_id == telegram_user_id
            ))).scalars().all()
            payload[model.__tablename__] = [_export_record(row) for row in rows]

    product_event = getattr(models, "ProductEvent", None)
    if product_event is not None:
        conditions = []
        if account_id is not None:
            conditions.append(product_event.web_account_id == account_id)
        if telegram_user_id is not None:
            conditions.append(product_event.telegram_user_id == telegram_user_id)
        payload["product_events"] = [_export_record(row) for row in (
            await session.execute(select(product_event).where(or_(*conditions)))
        ).scalars().all()]
    return payload


def _telegram_owned_models() -> list:
    # Include future delivery tables with a direct users FK without deleting shared data.
    return [
        mapper.class_
        for mapper in models.Base.registry.mappers
        if mapper.class_ is not models.WebAccount
        and any(
            fk.target_fullname == "users.user_id" and fk.ondelete == "CASCADE"
            for column in mapper.local_table.columns for fk in column.foreign_keys
        )
        and hasattr(mapper.class_, "user_id")
    ]


async def delete_telegram_data(session: AsyncSession, user_id: int) -> bool:
    """Clear Telegram-owned data while retaining an existing website account link."""
    account = await get_telegram_web_account(session, user_id)
    if account is None:
        result = await session.execute(delete(models.User).where(models.User.user_id == user_id))
    else:
        for model in _telegram_owned_models():
            await session.execute(delete(model).where(model.user_id == user_id))
        product_event = getattr(models, "ProductEvent", None)
        if product_event is not None:
            await session.execute(delete(product_event).where(
                product_event.telegram_user_id == user_id
            ))
        # Keeping this minimal identity avoids orphaning Telegram-only website login.
        result = await session.execute(update(models.User).where(models.User.user_id == user_id).values(
            settings={}, onboarding_completed=False, calendar_secret=None,
            full_name="User", username=None, avatar_pic_url=None,
        ))
    await session.commit()
    await _clear_owner_cache(user_id)
    return bool(result.rowcount)


async def delete_account_data(session: AsyncSession, account_id: int) -> bool:
    """Atomically erase the website account, Studio and linked Telegram owner data."""
    account = (await session.execute(select(models.WebAccount).where(
        models.WebAccount.id == account_id
    ).with_for_update())).scalar_one_or_none()
    if account is None:
        return False
    telegram_user_id = account.telegram_id
    await session.execute(delete(models.WebAccount).where(models.WebAccount.id == account_id))
    if telegram_user_id is not None:
        await session.execute(delete(models.User).where(models.User.user_id == telegram_user_id))
    await session.commit()
    await _clear_studio_jobs(account_id)
    if telegram_user_id is not None:
        await _clear_owner_cache(telegram_user_id)
    return True


async def _clear_owner_cache(user_id: int) -> None:
    async def clear():
        async for key in redis_client.client.scan_iter(match=f"user_cache:{int(user_id)}:*"):
            await redis_client.client.delete(key)
    try:
        await asyncio.wait_for(clear(), timeout=2)
    except Exception:
        # Caches expire normally; a cache outage must not misreport a committed deletion.
        logger.warning("Owner cache cleanup deferred after deletion", exc_info=True)


async def _clear_studio_jobs(account_id: int) -> None:
    """Best-effort cleanup; live worker termination is deliberately not requested."""
    from shared_lib.celery_app import app as celery_app

    def revoke_and_forget(job_id):
        celery_app.control.revoke(job_id, terminate=False)
        celery_app.AsyncResult(job_id).forget()

    async def clear():
        async for key in redis_client.client.scan_iter(match="mpb:studio-job:*"):
            raw = await redis_client.client.get(key)
            if not raw:
                continue
            try:
                metadata = json.loads(raw)
                job_id = str(UUID(metadata["job_id"]))
            except (ValueError, KeyError, TypeError):
                continue
            if metadata.get("owner_id") != account_id or key != f"mpb:studio-job:{job_id}":
                continue
            await redis_client.client.delete(key)
            await asyncio.to_thread(revoke_and_forget, job_id)
    try:
        await asyncio.wait_for(clear(), timeout=3)
    except Exception:
        logger.warning("Studio cleanup deferred to 24-hour expiry after account deletion", exc_info=True)
