from fastapi import APIRouter, Depends
from shared_lib.services.university_api import create_ruz_api_client
from shared_lib.services.schedule_service import get_unique_modules_hybrid, get_module_name
from shared_lib.database import get_all_short_names
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
        
        # 1. Получаем маппинг коротких имен из БД
        short_names = await get_all_short_names()
        
        # 2. Обрабатываем каждое занятие перед отправкой
        for lesson in schedule:
            # Подставляем короткое имя, если оно есть
            full_name = lesson.get('discipline', '')
            lesson['discipline_display'] = short_names.get(full_name, full_name)
            
            # Сразу извлекаем модуль на бэкенде для надежности
            lesson['module'] = get_module_name(lesson.get('group')) 

        modules = await get_unique_modules_hybrid(schedule)
        
        return {
            "schedule": schedule,
            "available_modules": modules
        }