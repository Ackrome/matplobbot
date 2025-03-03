import asyncio
import logging
import os
import threading
from dotenv import load_dotenv
from flask import Flask
from aiogram import Bot, Dispatcher

from app.handlers import router

logging.basicConfig(level=logging.INFO)
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
PORT = int(os.getenv("PORT", 5000))

# Создаем Flask-приложение
fl = Flask(__name__)

@fl.route('/')
def index():
    return "Hello, Render.com!"

# Асинхронная функция для запуска бота
async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)

# Функция для запуска Flask-сервера
def run_flask():
    fl.run(host="0.0.0.0", port=PORT)

if __name__ == '__main__':
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    try:
        # Запускаем асинхронного бота в основном потоке
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error('Bot stopped!')