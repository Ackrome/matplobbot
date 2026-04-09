import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path  # Добавляем импорт pathlib

import aiohttp
from dotenv import load_dotenv  # Добавьте импорт
from fastapi.middleware.cors import CORSMiddleware

from fastapi_stats_app.config import (  # Import logging constants
    FASTAPI_LOG_FILE_NAME,
    LOG_DIR,
)
from shared_lib.request_context import configure_correlation_logging

load_dotenv()  # Загружаем .env

# --- PROXY PATCH (same behavior as bot) ---
PROXY_URL = os.getenv("PROXY_URL")
if PROXY_URL:
    # Use socks5h so DNS resolution happens on the proxy side
    socks5h_proxy = PROXY_URL.replace("socks5://", "socks5h://")
    os.environ["HTTP_PROXY"] = socks5h_proxy
    os.environ["HTTPS_PROXY"] = socks5h_proxy
    os.environ["ALL_PROXY"] = socks5h_proxy
# ------------------------------------
# Определяем пути для логгирования FastAPI приложения
LOG_FILE_FASTAPI = os.path.join(
    LOG_DIR, FASTAPI_LOG_FILE_NAME
)  # Use constants from config

# Настройка логгирования для FastAPI приложения
# Reuse the same logging format as in bot/logger.py
# --- ВАЖНО: Эта конфигурация должна быть выполнена ДО импорта других модулей приложения ---
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [cid=%(correlation_id)s] - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE_FASTAPI, encoding="utf-8"), logging.StreamHandler()],
)
configure_correlation_logging()
logger = logging.getLogger(
    __name__
)  # Получаем логгер после базовой конфигурации

# --- Теперь можно безопасно импортировать остальные части приложения ---
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from shared_lib.database import close_db_pool, init_db_pool

from .auth import get_current_user  # Import auth dependency
from .middleware import CorrelationIdMiddleware
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup
    logger.info("Application startup: Initializing database pool...")
    await init_db_pool()
    app.state.shared_http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    yield
    # On shutdown
    shared_http_session = getattr(app.state, "shared_http_session", None)
    if shared_http_session and not shared_http_session.closed:
        await shared_http_session.close()
    logger.info("Application shutdown: Closing database pool...")
    await close_db_pool()


app = FastAPI(title="Bot Stats API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)

# Настройка CORS для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ivantishchenko.ru",
        "http://ivantishchenko.ru",
        "https://api.ivantishchenko.ru",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Определяем базовую директорию приложения (где находится main.py)
APP_BASE_DIR = Path(__file__).resolve().parent

# Настройка Jinja2 для шаблонов
templates = Jinja2Templates(directory=str(APP_BASE_DIR / "templates"))

# Создаем директорию для статики, если ее нет
STATIC_DIR = APP_BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "css").mkdir(exist_ok=True)
(STATIC_DIR / "js").mkdir(exist_ok=True)

# Монтируем статические файлы
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Root HTML endpoint for stats page
@app.get(
    "/",
    response_class=HTMLResponse,
    summary="Главная страница статистики",
    description="Отображает HTML страницу со статистикой бота.",
    dependencies=[Depends(get_current_user)],
)
async def read_root_html(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get(
    "/users/{user_id}",
    response_class=HTMLResponse,
    summary="Страница профиля пользователя",
    description="Отображает страницу с детальной информацией о действиях пользователя.",
    dependencies=[Depends(get_current_user)],
)
async def read_user_details_html(request: Request, user_id: int):
    # user_id передается в шаблон, но мы будем загружать данные через JS/API
    return templates.TemplateResponse("user_details.html", {"request": request, "user_id": user_id})


app.include_router(auth_router.router, prefix="/api")
app.include_router(schedule_router.router, prefix="/api")
app.include_router(studio_router.router, prefix="/api")
app.include_router(stats_router.router, prefix="/api")
app.include_router(ws_router.router, tags=["websockets"])
app.include_router(calendar_router.router, prefix="/api", tags=["calendar"])
