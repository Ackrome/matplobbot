import asyncio
import logging
from dotenv import load_dotenv
import os

from aiogram import Bot, Dispatcher, F


from app.handlers import router
# from app.database.models import async_main

logging.basicConfig(level=logging.INFO)
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')



async def main():
    # async_main()
    
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)
    
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error('Bot stopped!')