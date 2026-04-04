import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path  # Р”РѕР±Р°РІР»СЏРµРј РёРјРїРѕСЂС‚ pathlib

import aiohttp
from dotenv import load_dotenv  # Р”РѕР±Р°РІСЊС‚Рµ РёРјРїРѕСЂС‚
from fastapi.middleware.cors import CORSMiddleware

from fastapi_stats_app.config import (  # РРјРїРѕСЂС‚РёСЂСѓРµРј РєРѕРЅСЃС‚Р°РЅС‚С‹ РґР»СЏ Р»РѕРіРіРёСЂРѕРІР°РЅРёСЏ
    FASTAPI_LOG_FILE_NAME,
    LOG_DIR,
)

load_dotenv()  # Р—Р°РіСЂСѓР¶Р°РµРј .env

# --- РџРђРўР§ Р”Р›РЇ РџР РћРљРЎР (РєР°Рє РІ Р±РѕС‚Рµ) ---
PROXY_URL = os.getenv("PROXY_URL")
if PROXY_URL:
    # РСЃРїРѕР»СЊР·СѓРµРј socks5h РґР»СЏ СЂРµР·РѕР»РІРёРЅРіР° DNS РЅР° СЃС‚РѕСЂРѕРЅРµ РїСЂРѕРєСЃРё
    socks5h_proxy = PROXY_URL.replace("socks5://", "socks5h://")
    os.environ["HTTP_PROXY"] = socks5h_proxy
    os.environ["HTTPS_PROXY"] = socks5h_proxy
    os.environ["ALL_PROXY"] = socks5h_proxy
# ------------------------------------
# РћРїСЂРµРґРµР»СЏРµРј РїСѓС‚Рё РґР»СЏ Р»РѕРіРіРёСЂРѕРІР°РЅРёСЏ FastAPI РїСЂРёР»РѕР¶РµРЅРёСЏ
LOG_FILE_FASTAPI = os.path.join(LOG_DIR, FASTAPI_LOG_FILE_NAME)  # РСЃРїРѕР»СЊР·СѓРµРј РєРѕРЅСЃС‚Р°РЅС‚С‹ РёР· config

# РќР°СЃС‚СЂРѕР№РєР° Р»РѕРіРіРёСЂРѕРІР°РЅРёСЏ РґР»СЏ FastAPI РїСЂРёР»РѕР¶РµРЅРёСЏ
# РСЃРїРѕР»СЊР·СѓРµРј С‚РѕС‚ Р¶Рµ С„РѕСЂРјР°С‚, С‡С‚Рѕ Рё РІ bot/logger.py
# --- Р’РђР–РќРћ: Р­С‚Р° РєРѕРЅС„РёРіСѓСЂР°С†РёСЏ РґРѕР»Р¶РЅР° Р±С‹С‚СЊ РІС‹РїРѕР»РЅРµРЅР° Р”Рћ РёРјРїРѕСЂС‚Р° РґСЂСѓРіРёС… РјРѕРґСѓР»РµР№ РїСЂРёР»РѕР¶РµРЅРёСЏ ---
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE_FASTAPI, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)  # РџРѕР»СѓС‡Р°РµРј Р»РѕРіРіРµСЂ РїРѕСЃР»Рµ Р±Р°Р·РѕРІРѕР№ РєРѕРЅС„РёРіСѓСЂР°С†РёРё

# --- РўРµРїРµСЂСЊ РјРѕР¶РЅРѕ Р±РµР·РѕРїР°СЃРЅРѕ РёРјРїРѕСЂС‚РёСЂРѕРІР°С‚СЊ РѕСЃС‚Р°Р»СЊРЅС‹Рµ С‡Р°СЃС‚Рё РїСЂРёР»РѕР¶РµРЅРёСЏ ---
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from shared_lib.database import close_db_pool, init_db_pool

from .auth import get_current_user  # РРјРїРѕСЂС‚РёСЂСѓРµРј РЅР°С€Сѓ С„СѓРЅРєС†РёСЋ
from .routers import (
    auth_router,
    calendar_router,
    schedule_router,
    stats_router,
    studio_router,
    ws_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup
    logger.info("Application startup: Initializing database pool...")
    await init_db_pool()
    app.state.shared_http_session = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30)
    )
    yield
    # On shutdown
    shared_http_session = getattr(app.state, "shared_http_session", None)
    if shared_http_session and not shared_http_session.closed:
        await shared_http_session.close()
    logger.info("Application shutdown: Closing database pool...")
    await close_db_pool()


app = FastAPI(title="Bot Stats API", version="0.1.0", lifespan=lifespan)

# РќР°СЃС‚СЂРѕР№РєР° CORS РґР»СЏ С„СЂРѕРЅС‚РµРЅРґР°
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
# РћРїСЂРµРґРµР»СЏРµРј Р±Р°Р·РѕРІСѓСЋ РґРёСЂРµРєС‚РѕСЂРёСЋ РїСЂРёР»РѕР¶РµРЅРёСЏ (РіРґРµ РЅР°С…РѕРґРёС‚СЃСЏ main.py)
APP_BASE_DIR = Path(__file__).resolve().parent

# РќР°СЃС‚СЂРѕР№РєР° Jinja2 РґР»СЏ С€Р°Р±Р»РѕРЅРѕРІ
templates = Jinja2Templates(directory=str(APP_BASE_DIR / "templates"))

# РЎРѕР·РґР°РµРј РґРёСЂРµРєС‚РѕСЂРёСЋ РґР»СЏ СЃС‚Р°С‚РёРєРё, РµСЃР»Рё РµРµ РЅРµС‚
STATIC_DIR = APP_BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "css").mkdir(exist_ok=True)
(STATIC_DIR / "js").mkdir(exist_ok=True)

# РњРѕРЅС‚РёСЂСѓРµРј СЃС‚Р°С‚РёС‡РµСЃРєРёРµ С„Р°Р№Р»С‹
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# РР·РјРµРЅСЏРµРј РєРѕСЂРЅРµРІРѕР№ СЌРЅРґРїРѕРёРЅС‚ РґР»СЏ РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ HTML СЃС‚СЂР°РЅРёС†С‹
@app.get(
    "/",
    response_class=HTMLResponse,
    summary="Р“Р»Р°РІРЅР°СЏ СЃС‚СЂР°РЅРёС†Р° СЃС‚Р°С‚РёСЃС‚РёРєРё",
    description="РћС‚РѕР±СЂР°Р¶Р°РµС‚ HTML СЃС‚СЂР°РЅРёС†Сѓ СЃРѕ СЃС‚Р°С‚РёСЃС‚РёРєРѕР№ Р±РѕС‚Р°.",
    dependencies=[Depends(get_current_user)],
)
async def read_root_html(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get(
    "/users/{user_id}",
    response_class=HTMLResponse,
    summary="РЎС‚СЂР°РЅРёС†Р° РїСЂРѕС„РёР»СЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ",
    description="РћС‚РѕР±СЂР°Р¶Р°РµС‚ СЃС‚СЂР°РЅРёС†Сѓ СЃ РґРµС‚Р°Р»СЊРЅРѕР№ РёРЅС„РѕСЂРјР°С†РёРµР№ Рѕ РґРµР№СЃС‚РІРёСЏС… РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ.",
    dependencies=[Depends(get_current_user)],
)
async def read_user_details_html(request: Request, user_id: int):
    # user_id РїРµСЂРµРґР°РµС‚СЃСЏ РІ С€Р°Р±Р»РѕРЅ, РЅРѕ РјС‹ Р±СѓРґРµРј Р·Р°РіСЂСѓР¶Р°С‚СЊ РґР°РЅРЅС‹Рµ С‡РµСЂРµР· JS/API
    return templates.TemplateResponse("user_details.html", {"request": request, "user_id": user_id})


app.include_router(auth_router.router, prefix="/api")
app.include_router(schedule_router.router, prefix="/api")
app.include_router(studio_router.router, prefix="/api")
app.include_router(stats_router.router, prefix="/api")
app.include_router(ws_router.router, tags=["websockets"])
app.include_router(calendar_router.router, prefix="/api", tags=["calendar"])
