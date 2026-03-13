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
from shared_lib.models import WebUser, User

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super-secret-key-12345")
BOT_TOKEN = os.getenv("BOT_TOKEN") # Нужно для валидации Telegram
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30 # 30 дней для Telegram

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
    """Проверяет подлинность данных, пришедших от виджета Telegram."""
    if not BOT_TOKEN:
        return False
        
    received_hash = data.get('hash')
    if not received_hash:
        return False
        
    # Формируем строку data_check_string
    data_check_arr =[]
    for key, value in data.items():
        if key != 'hash' and value is not None:
            data_check_arr.append(f"{key}={value}")
    
    data_check_arr.sort()
    data_check_string = "\n".join(data_check_arr)
    
    # Хэшируем
    secret_key = hashlib.sha256(BOT_TOKEN.encode('utf-8')).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode('utf-8'), hashlib.sha256).hexdigest()
    
    return hmac.compare_digest(expected_hash, received_hash)

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db_session_dependency)) -> dict:
    """Возвращает единый формат пользователя (словарь) независимо от способа входа."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Недействительные учетные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub: str = payload.get("sub")
        role: str = payload.get("role", "admin") # По умолчанию старые токены считаем админскими
        
        if sub is None:
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
        
    if role == "telegram":
        # Ищем пользователя в таблице телеграм-бота
        tg_id = int(sub.replace("tg_", ""))
        result = await db.execute(select(User).where(User.user_id == tg_id))
        user = result.scalar_one_or_none()
        if not user:
            raise credentials_exception
            
        return {
            "id": user.user_id,
            "username": user.full_name, # Для UI используем Имя из ТГ
            "role": "telegram",
            "avatar_url": user.avatar_pic_url,
            "preferences": user.settings,
            "db_obj": user # Ссылка на ORM объект, если понадобится
        }
    else:
        # Ищем пользователя в веб-админке
        result = await db.execute(select(WebUser).where(WebUser.username == sub))
        user = result.scalar_one_or_none()
        if not user:
            raise credentials_exception
            
        return {
            "id": user.id,
            "username": user.username,
            "role": "admin",
            "avatar_url": None,
            "preferences": user.preferences,
            "db_obj": user
        }

async def get_ws_user(websocket: WebSocket) -> dict:
    """Адаптация для вебсокетов (токен в query params)."""
    token = websocket.query_params.get("token")
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub: str = payload.get("sub")
        role: str = payload.get("role", "admin")
        if not sub:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
            
        async with get_session() as db:
            if role == "telegram":
                tg_id = int(sub.replace("tg_", ""))
                result = await db.execute(select(User).where(User.user_id == tg_id))
                user = result.scalar_one_or_none()
            else:
                result = await db.execute(select(WebUser).where(WebUser.username == sub))
                user = result.scalar_one_or_none()
                
            if not user:
                raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
            
            # Для WS нам обычно нужен просто факт валидности, но вернем тот же формат
            return {"id": sub, "role": role, "db_obj": user}
            
    except JWTError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)