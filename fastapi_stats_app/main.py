from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import logging
import os
from pathlib import Path # Добавляем импорт pathlib

from .routers import stats_router, ws_router
from .config import LOG_DIR, FASTAPI_LOG_FILE_NAME # Импортируем константы для логгирования


# Определяем пути для логгирования FastAPI приложения
LOG_FILE_FASTAPI = os.path.join(LOG_DIR, FASTAPI_LOG_FILE_NAME) # Используем константы из config

# Убедимся, что директория для логов существует
os.makedirs(LOG_DIR, exist_ok=True) # Используем LOG_DIR из config

# Настройка логгирования для FastAPI приложения
# Используем тот же формат, что и в bot/logger.py
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s",
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE_FASTAPI, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__) # Получаем логгер после базовой конфигурации


app = FastAPI(title="Bot Stats API", version="0.1.0")

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


# Изменяем корневой эндпоинт для отображения HTML страницы
@app.get("/", response_class=HTMLResponse, summary="Главная страница статистики", description="Отображает HTML страницу со статистикой бота.")
async def read_root_html(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/users/{user_id}", response_class=HTMLResponse, summary="Страница профиля пользователя", description="Отображает страницу с детальной информацией о действиях пользователя.")
async def read_user_details_html(request: Request, user_id: int):
    # user_id передается в шаблон, но мы будем загружать данные через JS/API
    return templates.TemplateResponse("user_details.html", {"request": request, "user_id": user_id})


app.include_router(stats_router.router, prefix="/api", tags=["statistics"])
app.include_router(ws_router.router, tags=["websockets"])