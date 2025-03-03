import asyncio
import logging
import os
import threading
from dotenv import load_dotenv
from flask import Flask
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Update

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

# Создаем Flask-приложение
fl = Flask(__name__)

@fl.route('/')
def index():
    return "Hello, Render.com!"

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
    
    try:
        # Запускаем асинхронного бота в основном потоке
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error('Bot stopped!')