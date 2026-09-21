import json
import logging
import os

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# TTL для кэша в секундах (например, 1 час)
CACHE_TTL = 3600
CALLBACK_PATH_KEY_PREFIX = "callback_path:"


def _is_callback_path_hash(value: str) -> bool:
    return len(value) == 16 and all(char in "0123456789abcdef" for char in value)


class RedisClient:
    def __init__(self, host="localhost", port=6379):
        # Используем connection_pool для более эффективного управления соединениями
        self.pool = redis.ConnectionPool(host=host, port=port, db=0, decode_responses=True)
        self.client = redis.Redis(connection_pool=self.pool)

    async def set_user_cache(self, user_id: int, key: str, data: dict, ttl: int = CACHE_TTL):
        """Сохраняет данные в кэш для конкретного пользователя."""
        try:
            redis_key = f"user_cache:{user_id}:{key}"
            await self.client.set(redis_key, json.dumps(data), ex=ttl)
        except Exception as e:
            logger.error(f"Ошибка при записи в Redis для user_id={user_id}, key={key}: {e}")

    async def get_user_cache(self, user_id: int, key: str) -> dict | None:
        """Получает данные из кэша для конкретного пользователя."""
        try:
            redis_key = f"user_cache:{user_id}:{key}"
            data = await self.client.get(redis_key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Ошибка при чтении из Redis для user_id={user_id}, key={key}: {e}")
            return None

    async def set_cache(self, key: str, data: dict, ttl: int = CACHE_TTL):
        """Сохраняет данные в кэш по общему ключу."""
        try:
            # Используем префикс 'cache:' для общих данных
            redis_key = f"cache:{key}"
            await self.client.set(redis_key, json.dumps(data), ex=ttl)
        except Exception as e:
            logger.error(f"Ошибка при записи в Redis для ключа={key}: {e}")

    async def get_cache(self, key: str) -> dict | None:
        """Получает данные из кэша по общему ключу."""
        try:
            redis_key = f"cache:{key}"
            data = await self.client.get(redis_key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Ошибка при чтении из Redis для ключа={key}: {e}")
            return None

    async def clear_all_user_cache(self):
        """Очищает весь пользовательский кэш (ключи, начинающиеся с 'user_cache:')."""
        try:
            async for key in self.client.scan_iter("user_cache:*"):
                await self.client.delete(key)
            logger.info("Весь пользовательский кэш в Redis очищен.")
        except Exception as e:
            logger.error(f"Ошибка при очистке кэша Redis: {e}")

    async def set_callback_path(self, path_hash: str, path: str, ttl: int):
        """Persist a Telegram callback hash mapping without serializing secrets."""
        if not _is_callback_path_hash(path_hash):
            raise ValueError("invalid callback path hash")
        if ttl <= 0:
            raise ValueError("callback path TTL must be positive")
        try:
            await self.client.set(
                f"{CALLBACK_PATH_KEY_PREFIX}{path_hash}",
                path,
                ex=ttl,
            )
        except Exception as e:
            logger.error("Ошибка при записи callback path в Redis для hash=%s: %s", path_hash, e)

    async def get_callback_path(self, path_hash: str) -> str | None:
        """Load a callback mapping created by this application."""
        if not _is_callback_path_hash(path_hash):
            return None
        try:
            return await self.client.get(f"{CALLBACK_PATH_KEY_PREFIX}{path_hash}")
        except Exception as e:
            logger.error("Ошибка при чтении callback path из Redis для hash=%s: %s", path_hash, e)
            return None

    async def clear_callback_paths(self):
        """Remove persistent callback mappings during an explicit admin cache clear."""
        try:
            async for key in self.client.scan_iter(f"{CALLBACK_PATH_KEY_PREFIX}*"):
                await self.client.delete(key)
            logger.info("Все callback path mappings в Redis очищены.")
        except Exception as e:
            logger.error("Ошибка при очистке callback path mappings в Redis: %s", e)


# Создаем единственный экземпляр клиента
redis_client = RedisClient(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", "6379")),
)
