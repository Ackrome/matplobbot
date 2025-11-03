import redis.asyncio as redis
import json
import logging

logger = logging.getLogger(__name__)

# TTL для кэша в секундах (например, 1 час)
CACHE_TTL = 3600

class RedisClient:
    def __init__(self, host='localhost', port=6379):
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

    async def clear_all_user_cache(self):
        """Очищает весь пользовательский кэш (ключи, начинающиеся с 'user_cache:')."""
        try:
            async for key in self.client.scan_iter("user_cache:*"):
                await self.client.delete(key)
            logger.info("Весь пользовательский кэш в Redis очищен.")
        except Exception as e:
            logger.error(f"Ошибка при очистке кэша Redis: {e}")

# Создаем единственный экземпляр клиента
redis_client = RedisClient(host='redis')
