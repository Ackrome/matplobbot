import asyncio
import logging

from aiogram import Bot, Dispatcher, F


from app.handlers import router
# from app.database.models import async_main

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = '7916061881:AAG0k6Tsy4krx9hMNjwhofCrF8g2N7nZQ8Q'


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