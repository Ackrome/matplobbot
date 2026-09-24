import json
import logging
import os

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# TTL для кэша в секундах (например, 1 час)
CACHE_TTL = 3600
CALLBACK_PATH_KEY_PREFIX = "callback_path:"
SUGGESTION_MESSAGE_KEY_PREFIX = "suggestion_messages:"
SUGGESTION_DECISION_LOCK_PREFIX = "suggestion_decision_lock:"
DEFAULT_REDIS_HOST = "redis"
DEFAULT_REDIS_PORT = 6379
DEFAULT_REDIS_DB = 0


def get_redis_url() -> str:
    """Return the shared Redis URL, preserving host/port compatibility."""
    configured_url = os.getenv("REDIS_URL", "").strip()
    if configured_url:
        return configured_url

    host = os.getenv("REDIS_HOST", DEFAULT_REDIS_HOST).strip() or DEFAULT_REDIS_HOST
    port = int(os.getenv("REDIS_PORT", str(DEFAULT_REDIS_PORT)))
    database = int(os.getenv("REDIS_DB", str(DEFAULT_REDIS_DB)))
    return f"redis://{host}:{port}/{database}"


def _is_callback_path_hash(value: str) -> bool:
    return len(value) == 16 and all(char in "0123456789abcdef" for char in value)


def _is_suggestion_hash(value: str) -> bool:
    return len(value) == 24 and all(char in "0123456789abcdef" for char in value)


class RedisClient:
    def __init__(
        self,
        host: str = "localhost",
        port: int = DEFAULT_REDIS_PORT,
        *,
        url: str | None = None,
        database: int = DEFAULT_REDIS_DB,
    ):
        # Используем connection_pool для более эффективного управления соединениями
        if url:
            self.pool = redis.ConnectionPool.from_url(url, decode_responses=True)
        else:
            self.pool = redis.ConnectionPool(
                host=host,
                port=port,
                db=database,
                decode_responses=True,
            )
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

    async def add_suggestion_message(
        self,
        data_hash: str,
        *,
        chat_id: int,
        message_id: int,
        ttl: int,
    ) -> None:
        """Atomically add one admin message reference to a suggestion set."""
        if not _is_suggestion_hash(data_hash):
            raise ValueError("invalid suggestion hash")
        if ttl <= 0:
            raise ValueError("suggestion message TTL must be positive")

        redis_key = f"{SUGGESTION_MESSAGE_KEY_PREFIX}{data_hash}"
        member = json.dumps(
            {"chat_id": int(chat_id), "message_id": int(message_id)},
            sort_keys=True,
            separators=(",", ":"),
        )
        async with self.client.pipeline(transaction=True) as pipeline:
            pipeline.sadd(redis_key, member)
            pipeline.expire(redis_key, ttl)
            await pipeline.execute()

    async def get_suggestion_messages(self, data_hash: str) -> list[dict[str, int]]:
        """Load all unique admin message references for a suggestion."""
        if not _is_suggestion_hash(data_hash):
            return []
        redis_key = f"{SUGGESTION_MESSAGE_KEY_PREFIX}{data_hash}"
        members = await self.client.smembers(redis_key)
        messages: list[dict[str, int]] = []
        for member in members:
            try:
                parsed = json.loads(member)
                messages.append(
                    {
                        "chat_id": int(parsed["chat_id"]),
                        "message_id": int(parsed["message_id"]),
                    }
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                logger.warning("Ignoring malformed suggestion message reference")
        return sorted(messages, key=lambda item: (item["chat_id"], item["message_id"]))

    async def acquire_suggestion_decision_lock(self, data_hash: str, ttl: int = 30) -> bool:
        """Allow only one administrator to decide a suggestion at a time."""
        if not _is_suggestion_hash(data_hash):
            return False
        return bool(
            await self.client.set(
                f"{SUGGESTION_DECISION_LOCK_PREFIX}{data_hash}",
                "1",
                ex=ttl,
                nx=True,
            )
        )

    async def clear_suggestion_state(self, data_hash: str) -> None:
        """Delete decision metadata, message references, and the short-lived lock."""
        if not _is_suggestion_hash(data_hash):
            return
        await self.client.delete(
            f"cache:suggestion_cache:{data_hash}",
            f"{SUGGESTION_MESSAGE_KEY_PREFIX}{data_hash}",
            f"{SUGGESTION_DECISION_LOCK_PREFIX}{data_hash}",
        )


# Создаем единственный экземпляр клиента
redis_client = RedisClient(url=get_redis_url())
