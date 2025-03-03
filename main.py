import asyncio
import logging
import os
import threading
from dotenv import load_dotenv
from flask import Flask
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Update
import time
import requests

from app.handlers import router

logging.basicConfig(level=logging.INFO)
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')

# Middleware для логгирования информации о пользователе
class UserLoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Update, data):
        user_info = "Unknown user"
        if event.message:
            user = event.message.from_user
            user_info = f"{user.full_name} (@{user.username})" if user.username else user.full_name
        elif event.callback_query:
            user = event.callback_query.from_user
            user_info = f"{user.full_name} (@{user.username})" if user.username else user.full_name
        logging.info(f"Получено обновление от пользователя: {user_info}")
        return await handler(event, data)


PORT = int(os.getenv("PORT", 5000))
# URL для keep-alive пинга, можно указать публичный URL вашего сервиса
KEEP_ALIVE_URL = os.getenv("KEEP_ALIVE_URL", f"http://localhost:{PORT}")

# Создаем Flask-приложение
fl = Flask(__name__)

@fl.route('/')
def index():
    return "Hello, Render.com!"

# Функция, которая периодически отправляет GET-запросы на указанный URL
def keep_alive():
    while True:
        try:
            response = requests.get(KEEP_ALIVE_URL)
            logging.info(f"Keep-alive ping sent. Status: {response.status_code}")
        except Exception as e:
            logging.error(f"Keep-alive ping failed: {e}")
        # Пингуем каждые 4 минуты (240 секунд)
        time.sleep(240)


# Асинхронная функция для запуска бота
async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    dp.update.middleware(UserLoggingMiddleware())
    dp.include_router(router)
    await dp.start_polling(bot)

# Функция для запуска Flask-сервера
def run_flask():
    fl.run(host="0.0.0.0", port=PORT)

if __name__ == '__main__':
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Запускаем keep-alive пинги в отдельном потоке
    keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
    keep_alive_thread.start()
    
    try:
        # Запускаем асинхронного бота в основном потоке
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error('Bot stopped!')