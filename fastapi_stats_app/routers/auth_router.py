# fastapi_stats_app/routers/auth_router.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from shared_lib.database import get_db_session_dependency
from shared_lib.models import WebUser
from shared_lib.schemas import WebUserCreate, WebUserResponse, Token, WebUserPreferencesUpdate
from ..auth import create_access_token, verify_password, get_password_hash, get_current_user

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
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=WebUserResponse)
async def get_me(current_user: WebUser = Depends(get_current_user)):
    return current_user

@router.put("/preferences", response_model=WebUserResponse)
async def update_preferences(
    prefs: WebUserPreferencesUpdate, 
    current_user: WebUser = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db_session_dependency)
):
    # Обновляем JSON колонку
    current_user.preferences = prefs.preferences
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user