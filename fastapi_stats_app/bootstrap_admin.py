"""Provision the deployment-managed password admin before authentication smoke checks."""

import asyncio
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared_lib.database import close_db_pool, get_session, init_db_pool
from shared_lib.models import WebAccount

from .auth import get_password_hash, verify_password


class AdminProvisioningError(Exception):
    """A safe, credential-free explanation of a rejected admin configuration."""


async def provision_admin(db: AsyncSession, username: str, password: str) -> str:
    """Create or synchronize an unlinked admin; never promote another account.

    The caller owns the transaction. Concurrent inserts are protected by the
    username unique constraint; a conflict fails closed and can be retried.
    """
    if not username.strip() or not password.strip():
        raise AdminProvisioningError("STATS_USER and STATS_PASS must be explicitly configured.")
    if password.lower() in {"admin", "password", "123456"}:
        raise AdminProvisioningError("STATS_PASS must not be a default password.")

    result = await db.execute(
        select(WebAccount).where(WebAccount.username == username).with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        db.add(
            WebAccount(username=username, password_hash=get_password_hash(password), role="admin")
        )
        await db.flush()
        return "created"

    if account.role != "admin" or account.telegram_id is not None:
        raise AdminProvisioningError(
            "STATS_USER is already owned by a non-admin or Telegram-linked account. "
            "Choose a dedicated deployment admin username "
            "(Jenkins parameter: DEPLOY_ADMIN_USERNAME). The existing account was not changed."
        )

    if account.password_hash:
        try:
            if verify_password(password, account.password_hash):
                return "unchanged"
        except (ValueError, TypeError) as exc:
            raise AdminProvisioningError(
                "The existing admin password hash is invalid; repair the account explicitly."
            ) from exc

    account.password_hash = get_password_hash(password)
    account.auth_version = (getattr(account, "auth_version", 0) or 0) + 1
    await db.flush()
    return "password synchronized"


async def bootstrap_admin() -> str:
    """Read effective container settings and commit admin provisioning atomically."""
    # Do not use config.py's development defaults for a command granting admin rights.
    username = os.environ.get("STATS_USER", "")
    password = os.environ.get("STATS_PASS", "")
    try:
        await init_db_pool()
        async with get_session() as db, db.begin():
            return await provision_admin(db, username, password)
    finally:
        await close_db_pool()


def main() -> int:
    """CLI exit status; never print credentials, password hashes, or SQL parameters."""
    try:
        result = asyncio.run(bootstrap_admin())
    except AdminProvisioningError as exc:
        print(f"Admin provisioning FAILED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # SQLAlchemy exception strings can include password hashes and connection data.
        print(f"Admin provisioning FAILED ({type(exc).__name__}).", file=sys.stderr)
        return 1
    print(f"Deployment admin: {result}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
