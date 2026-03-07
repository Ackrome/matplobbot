from fastapi import APIRouter, Depends
from shared_lib.services.university_api import create_ruz_api_client
from shared_lib.services.schedule_service import get_unique_modules_hybrid
import aiohttp
from datetime import date, timedelta

router = APIRouter(prefix="/schedule", tags=["schedule"])

@router.get("/search")
async def search_entity(term: str, type: str = "group"):
    async with aiohttp.ClientSession() as session:
        client = create_ruz_api_client(session)
        return await client.search(term, type)

@router.get("/data/{type}/{id}")
async def get_schedule_data(type: str, id: str):
    # Берем расписание на неделю
    start = date.today().strftime("%Y.%m.%d")
    finish = (date.today() + timedelta(days=7)).strftime("%Y.%m.%d")
    
    async with aiohttp.ClientSession() as session:
        client = create_ruz_api_client(session)
        schedule = await client.get_schedule(type, id, start, finish)
        
        # Получаем модули для фронтенда
        modules = await get_unique_modules_hybrid(schedule)
        
        return {
            "schedule": schedule,
            "available_modules": modules
        }