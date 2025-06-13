import logging
from aiogram import BaseMiddleware
from aiogram.types import Update
import os # Добавлено

# Импортируем функцию для логирования в БД
from database import log_user_action

# Директория и файл для логов
LOG_DIR = "/app/logs" # Директория для логов внутри контейнера
LOG_FILE = os.path.join(LOG_DIR, "bot.log")

# Убедимся, что директория для логов существует
os.makedirs(LOG_DIR, exist_ok=True) # Добавлено

# Настройка логгирования
logging.getLogger("aiogram.event").setLevel(logging.WARNING)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s",
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[ # Добавлено/изменено
        logging.FileHandler(LOG_FILE, encoding='utf-8'), # Логирование в файл
        logging.StreamHandler() # Логирование в консоль (stderr) для обратной совместимости или отладки
    ]
)


class UserLoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Update, data):
        bot = data.get('bot') # Получаем экземпляр бота из данных события
        user_id = None
        tg_username = None
        full_name = "Unknown User"
        avatar_pic_url = None # Добавляем переменную для URL аватара
        action_type = "unknown_event"
        action_details = None # Изначально None, будет заполнено конкретными данными

        console_log_message = "Получено неизвестное обновление."

        if event.message:
            user = event.message.from_user
            user_id = user.id
            tg_username = user.username
            full_name = user.full_name

            if bot and user: # Пытаемся получить URL аватара
                try:
                    user_photos = await bot.get_user_profile_photos(user.id, limit=1)
                    if user_photos and user_photos.photos and user_photos.photos[0]:
                        # Берем самую маленькую фотографию из первого набора (обычно достаточно)
                        file_id = user_photos.photos[0][0].file_id
                        file_info = await bot.get_file(file_id)
                        avatar_pic_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
                except Exception as e:
                    logging.warning(f"Не удалось получить аватар для пользователя {user_id}: {e}")

            if event.message.text and event.message.text.startswith('/'):
                action_type = "command"
                action_details = event.message.text
            elif event.message.text:
                action_type = "text_message"
                action_details = event.message.text
            elif event.message.photo:
                action_type = "photo_message"
                action_details = f"Photo ID: {event.message.photo[-1].file_id}. Caption: {event.message.caption or ''}"
            elif event.message.document:
                action_type = "document_message"
                action_details = f"Document: {event.message.document.file_name or 'N/A'}. Caption: {event.message.caption or ''}"
            # Можно добавить другие типы сообщений (audio, video, voice, etc.)
            else:
                action_type = "other_message"
                action_details = f"Message type: {event.message.content_type}"
            
            console_log_message = f"User: {full_name} (@{tg_username or 'no_username'}), Action: {action_type}, Details: {str(action_details)[:100] if action_details else ''}"

        elif event.callback_query:
            user = event.callback_query.from_user
            user_id = user.id
            tg_username = user.username
            full_name = user.full_name
            if bot and user: # Пытаемся получить URL аватара для callback
                try:
                    user_photos = await bot.get_user_profile_photos(user.id, limit=1)
                    if user_photos and user_photos.photos and user_photos.photos[0]:
                        file_id = user_photos.photos[0][0].file_id
                        file_info = await bot.get_file(file_id)
                        avatar_pic_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
                except Exception as e:
                    logging.warning(f"Не удалось получить аватар для пользователя {user_id} (callback): {e}")

            action_type = "callback_query"
            action_details = event.callback_query.data
            console_log_message = f"User: {full_name} (@{tg_username or 'no_username'}), Action: {action_type}, Details: {action_details}"
        
        logging.info(console_log_message)

        if user_id:  # Логируем в БД, только если есть информация о пользователе
            await log_user_action(user_id, tg_username, full_name, avatar_pic_url, action_type, action_details)
            
        return await handler(event, data)