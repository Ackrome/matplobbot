# fastapi_stats_app/routers/auth_router.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared_lib.database import get_db_session_dependency
from shared_lib.models import WebUser, User
from shared_lib.schemas import WebUserCreate, WebUserResponse, Token, WebUserPreferencesUpdate, TelegramAuthData, CurrentUserResponse
from ..auth import create_access_token, verify_password, get_password_hash, get_current_user, verify_telegram_authorization

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=WebUserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: WebUserCreate, db: AsyncSession = Depends(get_db_session_dependency)):
    result = await db.execute(select(WebUser).where(WebUser.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким именем уже существует"
        )
    
    hashed_password = get_password_hash(user_data.password)
    new_user = WebUser(username=user_data.username, password_hash=hashed_password, preferences={})
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    return new_user

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db_session_dependency)):
    result = await db.execute(select(WebUser).where(WebUser.username == form_data.username))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Добавляем роль в токен
    access_token = create_access_token(data={"sub": user.username, "role": "admin"})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/telegram", response_model=Token)
async def telegram_login(tg_data: TelegramAuthData, db: AsyncSession = Depends(get_db_session_dependency)):
    # 1. Проверяем криптографическую подпись Telegram
    if not verify_telegram_authorization(tg_data.model_dump()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недействительная подпись Telegram"
        )
    
    # 2. Сохраняем или обновляем пользователя в таблице бота (User)
    full_name = tg_data.first_name
    if tg_data.last_name:
        full_name += f" {tg_data.last_name}"
        
    stmt = pg_insert(User).values(
        user_id=tg_data.id,
        username=tg_data.username,
        full_name=full_name,
        avatar_pic_url=tg_data.photo_url
    ).on_conflict_do_update(
        index_elements=['user_id'],
        set_=dict(
            username=tg_data.username,
            full_name=full_name,
            avatar_pic_url=tg_data.photo_url
        )
    )
    await db.execute(stmt)
    await db.commit()
    
    # 3. Генерируем токен для ТГ пользователя
    access_token = create_access_token(data={"sub": f"tg_{tg_data.id}", "role": "telegram"})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=CurrentUserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    # Возвращаем подготовленный словарь (уже содержит нужные поля)
    return current_user

@router.put("/preferences", response_model=CurrentUserResponse)
async def update_preferences(
    prefs: WebUserPreferencesUpdate, 
    current_user: dict = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db_session_dependency)
):
    db_obj = current_user["db_obj"]
    
    if current_user["role"] == "admin":
        db_obj.preferences = prefs.preferences
    elif current_user["role"] == "telegram":
        db_obj.settings = prefs.preferences
        
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    
    # Обновляем текущий объект для ответа
    current_user["preferences"] = prefs.preferences
    return current_user