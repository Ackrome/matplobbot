# fastapi_stats_app/routers/auth_router.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared_lib.database import get_db_session_dependency
from shared_lib.models import User, WebAccount
from shared_lib.schemas import (
    CurrentUserResponse,
    StatusResponse,
    TelegramAuthData,
    Token,
    WebAccountCreate,
    WebAccountPreferencesUpdate,
)

from ..auth import (
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
    verify_telegram_authorization,
)
from ..config import ADMIN_USER_IDS

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=StatusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a website account",
    description="Creates a password-based website account for Swagger UI and the website login flow.",
)
async def register(
    user_data: WebAccountCreate, db: AsyncSession = Depends(get_db_session_dependency)
):
    result = await db.execute(select(WebAccount).where(WebAccount.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this username already exists",
        )

    hashed_password = get_password_hash(user_data.password)
    new_account = WebAccount(
        username=user_data.username,
        password_hash=hashed_password,
        role="user",
        preferences={},
    )

    db.add(new_account)
    await db.commit()

    return {"status": "success"}


@router.post(
    "/login",
    response_model=Token,
    summary="Login with username and password",
    description="Password grant endpoint used by the website and Swagger UI Authorize dialog.",
)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db_session_dependency),
):
    result = await db.execute(select(WebAccount).where(WebAccount.username == form_data.username))
    account = result.scalar_one_or_none()

    if not account or not verify_password(form_data.password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(account.id), "role": account.role})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post(
    "/telegram",
    response_model=Token,
    summary="Exchange Telegram login payload for a bearer token",
    description="Validates Telegram Login Widget data and returns a JWT for the linked website account.",
)
async def telegram_login(
    tg_data: TelegramAuthData, db: AsyncSession = Depends(get_db_session_dependency)
):
    if not verify_telegram_authorization(tg_data.model_dump()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Telegram signature",
        )

    full_name = tg_data.first_name
    if tg_data.last_name:
        full_name += f" {tg_data.last_name}"

    stmt = (
        pg_insert(User)
        .values(
            user_id=tg_data.id,
            username=tg_data.username,
            full_name=full_name,
            avatar_pic_url=tg_data.photo_url,
        )
        .on_conflict_do_update(
            index_elements=["user_id"],
            set_=dict(
                username=tg_data.username,
                full_name=full_name,
                avatar_pic_url=tg_data.photo_url,
            ),
        )
    )
    await db.execute(stmt)

    result = await db.execute(select(WebAccount).where(WebAccount.telegram_id == tg_data.id))
    account = result.scalar_one_or_none()

    if not account:
        role = "admin" if tg_data.id in ADMIN_USER_IDS else "user"
        account = WebAccount(role=role, preferences={}, telegram_id=tg_data.id)
        db.add(account)
        await db.flush()
    elif tg_data.id in ADMIN_USER_IDS and account.role != "admin":
        account.role = "admin"
        db.add(account)

    await db.commit()

    access_token = create_access_token(data={"sub": str(account.id), "role": account.role})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Get the current authenticated user",
)
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.post(
    "/logout",
    response_model=StatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Logout the current user",
    description="Stateless JWT logout endpoint for explicit client workflows.",
)
async def logout(_current_user: dict = Depends(get_current_user)):
    # JWT auth is stateless: client-side token disposal is sufficient for logout.
    # Endpoint exists for explicit UX flow and API contract symmetry.
    return {"status": "success"}


@router.put(
    "/preferences",
    response_model=CurrentUserResponse,
    summary="Update website preferences for the current user",
)
async def update_preferences(
    prefs: WebAccountPreferencesUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session_dependency),
):
    db_obj = current_user["db_obj"]
    db_obj.preferences = prefs.preferences
    db.add(db_obj)
    await db.commit()

    current_user["preferences"] = prefs.preferences
    return current_user
