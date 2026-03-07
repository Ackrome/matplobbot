import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# Конфигурация из окружения
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 1 день

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Учетные данные админа
ADMIN_USER = os.getenv("STATS_USER", "admin")
raw_pass = os.getenv("STATS_PASS", "admin")

# На всякий случай обрезаем, если пароль гигантский (для некоторых хэшеров это критично)
if len(raw_pass) > 72:
    raw_pass = raw_pass[:72]

ADMIN_PASS_HASH = pwd_context.hash(raw_pass)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except JWTError:
        raise credentials_exception