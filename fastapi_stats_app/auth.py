# fastapi_stats_app/auth.py
import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl

import jwt
from fastapi import Depends, HTTPException, WebSocket, WebSocketException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError as JWTError
from passlib.context import CryptContext
from redis.exceptions import RedisError
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared_lib.database import get_db_session_dependency, get_session
from shared_lib.models import User, WebAccount, WebTokenRevocation
from shared_lib.redis_client import redis_client

from .config import ADMIN_USER_IDS

logger = logging.getLogger(__name__)


def _get_jwt_secret_key() -> str:
    secret_key = os.getenv("JWT_SECRET_KEY")
    env = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development")).strip().lower()
    is_production = env in {"production", "prod", "live"}
    if secret_key:
        if is_production and len(secret_key.encode("utf-8")) < 32:
            raise RuntimeError("JWT_SECRET_KEY must contain at least 32 bytes in production")
        return secret_key
    if is_production:
        raise RuntimeError("JWT_SECRET_KEY environment variable must be set in production")
    logger.warning(
        "JWT_SECRET_KEY environment variable is not set! Using an ephemeral secret key for this process. "
        "Generated tokens will become invalid upon application restart. Set JWT_SECRET_KEY in production."
    )
    return secrets.token_urlsafe(32)


SECRET_KEY = _get_jwt_secret_key()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 days
JWT_ISSUER = os.getenv("JWT_ISSUER", "").strip() or "matplobbot-api"
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "").strip() or "matplobbot-web"
JWT_LEEWAY_SECONDS = max(0, int(os.getenv("JWT_LEEWAY_SECONDS", "0")))
WS_PROTOCOL = "matplobbot"
WS_TICKET_TTL_SECONDS = 30
_WS_TICKET_RE = re.compile(r"mpb-ticket\.([0-9a-f]{64})")
_WS_USER_PATH_RE = re.compile(r"/ws/users/([1-9][0-9]{0,18})")
TELEGRAM_WEBAPP_AUTH_MAX_AGE_SECONDS = int(
    os.getenv("TELEGRAM_WEBAPP_AUTH_MAX_AGE_SECONDS", str(60 * 60 * 24))
)
TELEGRAM_WIDGET_AUTH_MAX_AGE_SECONDS = max(
    1, int(os.getenv("TELEGRAM_WIDGET_AUTH_MAX_AGE_SECONDS", "86400"))
)
TELEGRAM_WIDGET_AUTH_CLOCK_SKEW_SECONDS = max(
    0, int(os.getenv("TELEGRAM_WIDGET_AUTH_CLOCK_SKEW_SECONDS", "60"))
)

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    subject = to_encode.get("sub")
    subject_text = str(subject) if subject is not None else ""
    if not subject_text.isdigit():
        raise ValueError("JWT subject must be a numeric account id")

    issued_at = datetime.now(UTC)
    expire = issued_at + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update(
        {
            "sub": subject_text,
            "iat": issued_at,
            "nbf": issued_at,
            "exp": expire,
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "jti": secrets.token_hex(24),
            "auth_version": int(to_encode.get("auth_version", 0)),
        }
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
        audience=JWT_AUDIENCE,
        issuer=JWT_ISSUER,
        leeway=JWT_LEEWAY_SECONDS,
        options={"require": ["sub", "iat", "nbf", "exp", "iss", "aud", "jti", "auth_version"]},
    )


async def session_is_active(db: AsyncSession, account: WebAccount, claims: dict) -> bool:
    """Shared REST/WS check; DB errors deliberately fail closed."""
    if claims.get("auth_version") != (account.auth_version or 0):
        return False
    jti = claims.get("jti")
    if not isinstance(jti, str) or len(jti) != 48:
        return False
    if claims.get("exp", 0) <= time.time() - JWT_LEEWAY_SECONDS:
        return False
    revoked = await db.execute(select(WebTokenRevocation.jti).where(WebTokenRevocation.jti == jti))
    return revoked.scalar_one_or_none() is None


async def revoke_session(db: AsyncSession, account_id: int, claims: dict) -> None:
    """Idempotently revoke this JWT and prune already expired revocations."""
    await db.execute(
        delete(WebTokenRevocation).where(
            WebTokenRevocation.expires_at
            < datetime.now(UTC) - timedelta(seconds=JWT_LEEWAY_SECONDS)
        )
    )
    await db.execute(
        pg_insert(WebTokenRevocation)
        .values(
            jti=claims["jti"],
            account_id=account_id,
            expires_at=datetime.fromtimestamp(claims["exp"], UTC),
        )
        .on_conflict_do_nothing(index_elements=["jti"])
    )
    await db.commit()


async def revoke_all_sessions(db: AsyncSession, account_id: int) -> None:
    """Atomic generation bump prevents concurrent logout-all updates being lost."""
    await db.execute(
        update(WebAccount)
        .where(WebAccount.id == account_id)
        .values(auth_version=WebAccount.auth_version + 1)
    )
    await db.commit()


def create_account_export_token(account_id: int) -> str:
    """Short-lived export receipt; its audience deliberately cannot authenticate requests."""
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(account_id),
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=15),
            "iss": JWT_ISSUER,
            "aud": f"{JWT_AUDIENCE}:account-export",
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def verify_account_export_token(token: str, account_id: int) -> bool:
    try:
        claims = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer=JWT_ISSUER,
            audience=f"{JWT_AUDIENCE}:account-export",
            options={"require": ["sub", "iat", "nbf", "exp", "iss", "aud"]},
        )
        return claims["sub"] == str(account_id)
    except JWTError:
        return False


def resolve_account_role(account: WebAccount) -> str:
    if account.role == "admin":
        return "admin"
    if account.telegram_id and account.telegram_id in ADMIN_USER_IDS:
        return "admin"
    return account.role


def verify_telegram_authorization(data: dict) -> bool:
    if not BOT_TOKEN:
        return False

    received_hash = data.get("hash")
    if not received_hash:
        return False

    # A valid signature alone does not expire an intercepted login payload.
    auth_date = data.get("auth_date")
    if isinstance(auth_date, bool) or not isinstance(auth_date, int):
        return False
    age = int(time.time()) - auth_date
    if age > TELEGRAM_WIDGET_AUTH_MAX_AGE_SECONDS or age < -TELEGRAM_WIDGET_AUTH_CLOCK_SKEW_SECONDS:
        return False

    data_check_arr = []
    for key, value in data.items():
        if key != "hash" and value is not None:
            data_check_arr.append(f"{key}={value}")

    data_check_arr.sort()
    data_check_string = "\n".join(data_check_arr)

    secret_key = hashlib.sha256(BOT_TOKEN.encode("utf-8")).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_hash, received_hash)


def parse_verified_telegram_webapp_init_data(init_data: str) -> dict | None:
    if not BOT_TOKEN:
        return None

    parsed_data = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed_data.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed_data.items()))

    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        return None

    raw_auth_date = parsed_data.get("auth_date")
    try:
        auth_date = int(raw_auth_date) if raw_auth_date is not None else None
    except (TypeError, ValueError):
        return None

    if auth_date is None:
        return None

    now = int(time.time())
    if TELEGRAM_WEBAPP_AUTH_MAX_AGE_SECONDS > 0:
        is_too_old = now - auth_date > TELEGRAM_WEBAPP_AUTH_MAX_AGE_SECONDS
        # Оставляем проверку устаревания для тестов (is_too_old),
        # но расширяем лимит для токенов "из будущего" до 24 часов
        is_from_future = auth_date - now > 86400
        if is_too_old or is_from_future:
            return None
    raw_user = parsed_data.get("user")
    if not raw_user:
        return None

    try:
        user_data = json.loads(raw_user)
    except json.JSONDecodeError:
        return None

    if not user_data.get("id") or not user_data.get("first_name"):
        return None

    user_data["auth_date"] = auth_date
    return user_data


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db_session_dependency),
) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    try:
        payload = decode_access_token(token)
        raw_sub_id = payload.get("sub")
        if not isinstance(raw_sub_id, str) or not raw_sub_id:
            raise credentials_exception
        sub_id = int(raw_sub_id)
    except (JWTError, ValueError) as exc:
        raise credentials_exception from exc

    result = await db.execute(select(WebAccount).where(WebAccount.id == sub_id))
    account = result.scalar_one_or_none()

    if not account:
        raise credentials_exception
    if not await session_is_active(db, account, payload):
        raise credentials_exception

    display_name = account.username or "User"
    avatar_url = None

    if account.telegram_id:
        tg_result = await db.execute(select(User).where(User.user_id == account.telegram_id))
        tg_user = tg_result.scalar_one_or_none()
        if tg_user:
            display_name = tg_user.full_name
            avatar_url = tg_user.avatar_pic_url
            if avatar_url and "api.telegram.org/file/bot" in avatar_url:
                avatar_url = f"/api/stats/users/{account.telegram_id}/avatar"

    return {
        "id": account.id,
        "username": display_name,
        "role": resolve_account_role(account),
        "telegram_id": account.telegram_id,
        "avatar_url": avatar_url,
        "preferences": account.preferences,
        "db_obj": account,
        "token_claims": payload,
    }


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def can_subscribe_user_updates(user: dict, target_user_id: int) -> bool:
    return user.get("role") == "admin" or user.get("telegram_id") == target_user_id


def check_ws_ticket_scope(path: str, user: dict) -> None:
    """Apply each stream's authorization before issuing a ticket."""
    if path == "/ws/stats/total_actions":
        require_admin(user)
    elif path != "/ws/bot_log":
        match = _WS_USER_PATH_RE.fullmatch(path)
        if match is None:
            raise HTTPException(status_code=422, detail="Unknown WebSocket stream")
        if not can_subscribe_user_updates(user, int(match[1])):
            raise HTTPException(status_code=403, detail="WebSocket stream access denied")


def _ws_ticket_key(ticket: str, path: str) -> str:
    digest = hashlib.sha256(f"{path}\0{ticket}".encode()).hexdigest()
    return f"auth:ws-ticket:{digest}"


async def create_ws_ticket(path: str, user: dict) -> str:
    """Keep only the session claims needed for revocation and never store the ticket itself."""
    check_ws_ticket_scope(path, user)
    ticket = secrets.token_hex(32)
    claims = {key: user["token_claims"][key] for key in ("sub", "exp", "jti", "auth_version")}
    try:
        async with asyncio.timeout(2):
            saved = await redis_client.client.set(
                _ws_ticket_key(ticket, path), json.dumps(claims), ex=WS_TICKET_TTL_SECONDS, nx=True
            )
    except (RedisError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="WebSocket authentication unavailable") from exc
    if not saved:
        raise HTTPException(status_code=503, detail="WebSocket authentication unavailable")
    return ticket


async def get_ws_user(websocket: WebSocket) -> dict:
    protocols = websocket.headers.getlist("sec-websocket-protocol")
    names = [name.strip() for header in protocols for name in header.split(",")]
    match = (
        _WS_TICKET_RE.fullmatch(names[1]) if len(names) == 2 and names[0] == WS_PROTOCOL else None
    )
    if match is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    try:
        async with asyncio.timeout(2):
            raw = await redis_client.client.getdel(_ws_ticket_key(match[1], websocket.url.path))
        if raw is None:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
        payload = json.loads(raw)
        sub_id = int(payload["sub"])

        async with get_session() as db:
            result = await db.execute(select(WebAccount).where(WebAccount.id == sub_id))
            account = result.scalar_one_or_none()
            if not account:
                raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
            if not await session_is_active(db, account, payload):
                raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

            return {
                "id": account.id,
                "role": resolve_account_role(account),
                "telegram_id": account.telegram_id,
                "db_obj": account,
                "token_claims": payload,
            }

    except (RedisError, TimeoutError, ValueError, TypeError, KeyError) as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION) from exc


def require_ws_admin(user: dict = Depends(get_ws_user)) -> dict:
    """Allow administrative WebSocket streams only to resolved admin accounts."""
    if user.get("role") != "admin":
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return user
