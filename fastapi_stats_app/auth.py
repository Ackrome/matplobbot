# fastapi_stats_app/auth.py
import os
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, WebSocket, WebSocketException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from shared_lib.database import get_db_session_dependency, get_session
from shared_lib.models import WebAccount, User

def _get_jwt_secret_key() -> str:
    secret_key = os.getenv("JWT_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("JWT_SECRET_KEY environment variable must be set")
    return secret_key


SECRET_KEY = _get_jwt_secret_key()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30 # 30 дней сессии

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_telegram_authorization(data: dict) -> bool:
    if not BOT_TOKEN:
        return False
        
    received_hash = data.get('hash')
    if not received_hash:
        return False
        
    data_check_arr =[]
    for key, value in data.items():
        if key != 'hash' and value is not None:
            data_check_arr.append(f"{key}={value}")
    
    data_check_arr.sort()
    data_check_string = "\n".join(data_check_arr)
    
    secret_key = hashlib.sha256(BOT_TOKEN.encode('utf-8')).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode('utf-8'), hashlib.sha256).hexdigest()
    
    return hmac.compare_digest(expected_hash, received_hash)

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db_session_dependency)) -> dict:
    """Возвращает единый формат пользователя (словарь), собирая данные из WebAccount и User(Tg)."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Недействительные учетные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub_id: str = payload.get("sub") # В payload всегда лежит ID из WebAccount
        if not sub_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    # Ищем WebAccount
    result = await db.execute(select(WebAccount).where(WebAccount.id == int(sub_id)))
    account = result.scalar_one_or_none()
    
    if not account:
        raise credentials_exception
        
    # По умолчанию для админа
    display_name = account.username or "Пользователь"
    avatar_url = None
    
    # Если привязан Telegram, берем красивые данные оттуда
    if account.telegram_id:
        tg_result = await db.execute(select(User).where(User.user_id == account.telegram_id))
        tg_user = tg_result.scalar_one_or_none()
        if tg_user:
            display_name = tg_user.full_name
            avatar_url = tg_user.avatar_pic_url
            
    return {
        "id": account.id,
        "username": display_name,
        "role": account.role,
        "telegram_id": account.telegram_id,
        "avatar_url": avatar_url,
        "preferences": account.preferences,
        "db_obj": account # Ссылка на ORM объект для обновления preferences
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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
                "role": account.role,
                "telegram_id": account.telegram_id,
                "db_obj": account,
            }
            
    except JWTError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
