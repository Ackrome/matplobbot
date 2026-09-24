import logging
from contextlib import asynccontextmanager
from pathlib import Path  # Добавляем импорт pathlib

import aiohttp
from dotenv import load_dotenv  # Добавьте импорт
from fastapi.middleware.cors import CORSMiddleware

from shared_lib.egress import configure_process_http_proxy_env, get_global_http_proxy_url
from shared_lib.logging_config import configure_logging

load_dotenv()  # Загружаем .env

configure_process_http_proxy_env(
    get_global_http_proxy_url(),
    no_proxy_hosts=("ruz.fa.ru",),
)
configure_logging("matplobbot-api")
logger = logging.getLogger(__name__)  # Получаем логгер после базовой конфигурации

# --- Теперь можно безопасно импортировать остальные части приложения ---
from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from shared_lib.database import close_db_pool, init_db_pool
from shared_lib.services.schedule_freshness import shutdown_schedule_refresh_tasks

from .auth import get_current_user, require_admin  # Import auth dependencies
from .config import CORS_ALLOWED_ORIGINS, PUBLIC_SITE_URL
from .middleware import CorrelationIdMiddleware
from .openapi_docs import configure_openapi
from .routers import (
    auth_router,
    schedule_router,
    stats_router,
    studio_router,
    ws_router,
)
from .routers import (
    calendar_router_v2 as calendar_router,
)
from .telemetry import configure_fastapi_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup
    logger.info("Application startup: Initializing database pool...")
    await init_db_pool()
    app.state.shared_http_session = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30),
        trust_env=False,
    )
    yield
    # On shutdown
    shared_http_session = getattr(app.state, "shared_http_session", None)
    await shutdown_schedule_refresh_tasks()
    if shared_http_session and not shared_http_session.closed:
        await shared_http_session.close()
    logger.info("Application shutdown: Closing database pool...")
    await close_db_pool()


app = FastAPI(
    title="Matplobbot API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)
app.add_middleware(CorrelationIdMiddleware)
configure_fastapi_telemetry(app)

# Настройка CORS для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Определяем базовую директорию приложения (где находится main.py)
APP_BASE_DIR = Path(__file__).resolve().parent

# Создаем директорию для статики, если ее нет
STATIC_DIR = APP_BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "css").mkdir(exist_ok=True)
(STATIC_DIR / "js").mkdir(exist_ok=True)
(STATIC_DIR / "img").mkdir(exist_ok=True)

# Монтируем статические файлы
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
configure_openapi(app)


# Compatibility redirects keep old dashboard URLs working while the static
# frontend remains the only rendered user interface.
@app.get(
    "/",
    response_class=RedirectResponse,
    summary="Переход к панели статистики",
    description="Перенаправляет в единый статический интерфейс статистики.",
    dependencies=[Depends(get_current_user)],
    include_in_schema=False,
)
async def read_root_html():
    return RedirectResponse(f"{PUBLIC_SITE_URL}/stats", status_code=307)


@app.get(
    "/users/{user_id}",
    response_class=RedirectResponse,
    summary="Переход к профилю пользователя",
    description="Перенаправляет в admin-only страницу единого статического интерфейса.",
    dependencies=[Depends(require_admin)],
    include_in_schema=False,
)
async def read_user_details_html(user_id: int):
    return RedirectResponse(
        f"{PUBLIC_SITE_URL}/admin-user.html?user_id={user_id}",
        status_code=307,
    )


app.include_router(auth_router.router, prefix="/api")
app.include_router(schedule_router.router, prefix="/api")
app.include_router(studio_router.router, prefix="/api")
app.include_router(stats_router.router, prefix="/api")
app.include_router(ws_router.router, tags=["websockets"])
app.include_router(calendar_router.router, prefix="/api", tags=["calendar"])


@app.get("/api/users/{user_id}/avatar", include_in_schema=False)
async def get_user_avatar_alias(user_id: int):
    return await stats_router.get_user_avatar(user_id)
