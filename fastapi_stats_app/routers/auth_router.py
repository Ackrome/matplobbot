# fastapi_stats_app/routers/auth_router.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared_lib.database import get_db_session_dependency
from shared_lib.models import WebAccount, User
from shared_lib.schemas import WebAccountCreate, Token, WebAccountPreferencesUpdate, TelegramAuthData, CurrentUserResponse
from ..auth import create_access_token, verify_password, get_password_hash, get_current_user, verify_telegram_authorization

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user_data: WebAccountCreate, db: AsyncSession = Depends(get_db_session_dependency)):
    result = await db.execute(select(WebAccount).where(WebAccount.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким именем уже существует"
        )
    
    hashed_password = get_password_hash(user_data.password)
    # Регистрация по паролю по умолчанию дает роль админа
    new_account = WebAccount(username=user_data.username, password_hash=hashed_password, role='admin', preferences={})
    
    db.add(new_account)
    await db.commit()
    
    return {"status": "success"}

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db_session_dependency)):
    result = await db.execute(select(WebAccount).where(WebAccount.username == form_data.username))
    account = result.scalar_one_or_none()
    
    if not account or not verify_password(form_data.password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": str(account.id), "role": account.role})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/telegram", response_model=Token)
async def telegram_login(tg_data: TelegramAuthData, db: AsyncSession = Depends(get_db_session_dependency)):
    if not verify_telegram_authorization(tg_data.model_dump()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недействительная подпись Telegram"
        )
    
    # 1. Обновляем/создаем профиль в боте (users)
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
        set_=dict(username=tg_data.username, full_name=full_name, avatar_pic_url=tg_data.photo_url)
    )
    await db.execute(stmt)
    
    # 2. Ищем связующий WebAccount по telegram_id
    result = await db.execute(select(WebAccount).where(WebAccount.telegram_id == tg_data.id))
    account = result.scalar_one_or_none()
    
    if not account:
        # Если нет, прозрачно создаем новый WebAccount для этого пользователя
        account = WebAccount(role='user', preferences={}, telegram_id=tg_data.id)
        db.add(account)
        await db.flush() # Получаем ID
        
    await db.commit()
    
    access_token = create_access_token(data={"sub": str(account.id), "role": account.role})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=CurrentUserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user

@router.put("/preferences", response_model=CurrentUserResponse)
async def update_preferences(
    prefs: WebAccountPreferencesUpdate, 
    current_user: dict = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db_session_dependency)
):
    db_obj = current_user["db_obj"]
    db_obj.preferences = prefs.preferences
    db.add(db_obj)
    await db.commit()
    
    current_user["preferences"] = prefs.preferences
    return current_user