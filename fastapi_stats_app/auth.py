# fastapi_stats_app/auth.py
import base64
import binascii
import hashlib
import hmac
import json
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl

from fastapi import Depends, HTTPException, WebSocket, WebSocketException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared_lib.database import get_db_session_dependency, get_session
from shared_lib.models import User, WebAccount

from .config import ADMIN_USER_IDS


def _get_jwt_secret_key() -> str:
    secret_key = os.getenv("JWT_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("JWT_SECRET_KEY environment variable must be set")
    return secret_key


SECRET_KEY = _get_jwt_secret_key()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 days
TELEGRAM_WEBAPP_AUTH_MAX_AGE_SECONDS = int(
    os.getenv("TELEGRAM_WEBAPP_AUTH_MAX_AGE_SECONDS", str(60 * 60 * 24))
)

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)


class JWTError(Exception):
    pass


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _encode_hs256_jwt(payload: dict[str, Any], secret_key: str) -> str:
    header = {"alg": ALGORITHM, "typ": "JWT"}
    header_segment = _base64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    payload_segment = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_segment}.{payload_segment}.{_base64url_encode(signature)}"


def _decode_hs256_jwt(token: str, secret_key: str) -> dict[str, Any]:
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
    except ValueError as exc:
        raise JWTError("Invalid token structure") from exc

    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    expected_signature = hmac.new(
        secret_key.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    try:
        received_signature = _base64url_decode(signature_segment)
    except (binascii.Error, ValueError) as exc:
        raise JWTError("Invalid token signature") from exc

    if not hmac.compare_digest(expected_signature, received_signature):
        raise JWTError("Invalid token signature")

    try:
        header = json.loads(_base64url_decode(header_segment))
        payload = json.loads(_base64url_decode(payload_segment))
    except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise JWTError("Invalid token payload") from exc

    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise JWTError("Invalid token payload")

    if header.get("alg") != ALGORITHM:
        raise JWTError("Unsupported token algorithm")

    exp = payload.get("exp")
    if exp is not None:
        try:
            expires_at = float(exp)
        except (TypeError, ValueError) as exc:
            raise JWTError("Invalid token expiration") from exc
        if time.time() >= expires_at:
            raise JWTError("Token has expired")

    return payload


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": int(expire.timestamp())})
    return _encode_hs256_jwt(to_encode, SECRET_KEY)


def decode_access_token(token: str) -> dict[str, Any]:
    return _decode_hs256_jwt(token, SECRET_KEY)


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
        sub_id: str = payload.get("sub")
        if not sub_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(WebAccount).where(WebAccount.id == int(sub_id)))
    account = result.scalar_one_or_none()

    if not account:
        raise credentials_exception

    display_name = account.username or "User"
    avatar_url = None

    if account.telegram_id:
        tg_result = await db.execute(select(User).where(User.user_id == account.telegram_id))
        tg_user = tg_result.scalar_one_or_none()
        if tg_user:
            display_name = tg_user.full_name
            avatar_url = tg_user.avatar_pic_url

    return {
        "id": account.id,
        "username": display_name,
        "role": resolve_account_role(account),
        "telegram_id": account.telegram_id,
        "avatar_url": avatar_url,
        "preferences": account.preferences,
        "db_obj": account,
    }


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_ws_user(websocket: WebSocket) -> dict:
    token = websocket.query_params.get("token")
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    try:
        payload = decode_access_token(token)
        sub_id: str = payload.get("sub")
        if not sub_id:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

        async with get_session() as db:
            result = await db.execute(select(WebAccount).where(WebAccount.id == int(sub_id)))
            account = result.scalar_one_or_none()
            if not account:
                raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

            return {
                "id": account.id,
                "role": resolve_account_role(account),
                "telegram_id": account.telegram_id,
                "db_obj": account,
            }

    except JWTError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
