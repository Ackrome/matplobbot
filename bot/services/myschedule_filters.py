from bot import database
from shared_lib.redis_client import redis_client

ALLOWED_LESSON_TYPES = {"Lecture", "Seminar", "Exam", "Consultation", "Other"}
FILTER_CACHE_KEY = "mysch_filters"
FILTER_CACHE_TTL_SECONDS = 3600


class MyScheduleFilterService:
    """Persist and cache the filters used by the aggregated schedule view."""

    async def get(self, user_id: int) -> dict:
        db_filters = await database.get_user_myschedule_filters(user_id)
        redis_filters = await redis_client.get_user_cache(user_id, FILTER_CACHE_KEY)

        if redis_filters:
            normalized_redis = {
                "excluded_subs": [
                    int(item)
                    for item in redis_filters.get("excluded_subs", [])
                    if str(item).strip().isdigit()
                ],
                "excluded_types": [
                    str(item)
                    for item in redis_filters.get("excluded_types", [])
                    if str(item) in ALLOWED_LESSON_TYPES
                ],
            }
            if (
                db_filters == {"excluded_subs": [], "excluded_types": []}
                and normalized_redis != db_filters
            ):
                db_filters = await database.save_user_myschedule_filters(
                    user_id,
                    normalized_redis,
                )

        await redis_client.set_user_cache(
            user_id,
            FILTER_CACHE_KEY,
            db_filters,
            ttl=FILTER_CACHE_TTL_SECONDS,
        )
        return db_filters

    async def save(self, user_id: int, filters: dict) -> dict:
        normalized = await database.save_user_myschedule_filters(user_id, filters)
        await redis_client.set_user_cache(
            user_id,
            FILTER_CACHE_KEY,
            normalized,
            ttl=FILTER_CACHE_TTL_SECONDS,
        )
        return normalized

    async def get_active_subscriptions(self, user_id: int) -> list[dict]:
        subscriptions, _ = await database.get_user_subscriptions(user_id, page=0, page_size=100)
        return [subscription for subscription in subscriptions if subscription["is_active"]]

    @staticmethod
    def build_builtin(preset_id: str, active_subscriptions: list[dict]) -> dict | None:
        if preset_id == "all":
            return {"excluded_subs": [], "excluded_types": []}
        if preset_id == "only_exams":
            return {
                "excluded_subs": [],
                "excluded_types": ["Lecture", "Seminar", "Other"],
            }
        if preset_id == "hide_auditoriums":
            excluded = [
                int(subscription["id"])
                for subscription in active_subscriptions
                if subscription.get("entity_type") == "auditorium"
            ]
            return {"excluded_subs": excluded, "excluded_types": []}
        return None
