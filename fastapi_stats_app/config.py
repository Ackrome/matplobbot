import os
from dataclasses import dataclass

DEFAULT_CORS_ALLOWED_ORIGINS = (
    "https://ivantishchenko.ru",
    "http://ivantishchenko.ru",
    "https://api.ivantishchenko.ru",
)


def _parse_csv_env_value(raw_value: str) -> list[str]:
    return [
        item.strip()
        for item in raw_value.replace("\n", ",").replace(";", ",").split(",")
        if item.strip()
    ]


def _read_csv_env(
    primary_name: str,
    *,
    fallback_name: str | None = None,
    default: tuple[str, ...] = (),
) -> list[str]:
    raw_value = os.getenv(primary_name)
    if raw_value is None and fallback_name:
        raw_value = os.getenv(fallback_name)
    if raw_value is None:
        return list(default)
    return _parse_csv_env_value(raw_value)


def _read_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _read_int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    return max(minimum, parsed)


def _read_float_env(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed = float(raw_value)
    except ValueError:
        return default
    return max(minimum, parsed)


@dataclass(frozen=True)
class RateLimitSettings:
    limit: int
    window_seconds: int


# --- PostgreSQL Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Admin Panel Auth ---
STATS_USER = os.getenv("STATS_USER", "admin")
STATS_PASS = os.getenv("STATS_PASS", "admin")


def _parse_admin_user_ids() -> set[int]:
    raw_ids = os.getenv("ADMIN_USER_IDS", "")
    if not raw_ids:
        return set()

    parsed_ids: set[int] = set()
    for raw_id in raw_ids.split(","):
        raw_id = raw_id.strip()
        if raw_id.isdigit():
            parsed_ids.add(int(raw_id))
    return parsed_ids


ADMIN_USER_IDS = _parse_admin_user_ids()
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "").rstrip("/")

# --- FastAPI CORS ---
CORS_ALLOWED_ORIGINS = _read_csv_env(
    "FASTAPI_CORS_ALLOWED_ORIGINS",
    fallback_name="CORS_ALLOWED_ORIGINS",
    default=DEFAULT_CORS_ALLOWED_ORIGINS,
)

# --- Redis-backed API rate limits ---
FASTAPI_RATE_LIMIT_ENABLED = _read_bool_env("FASTAPI_RATE_LIMIT_ENABLED", True)
FASTAPI_RATE_LIMIT_FAIL_OPEN = _read_bool_env("FASTAPI_RATE_LIMIT_FAIL_OPEN", True)
FASTAPI_RATE_LIMIT_REDIS_TIMEOUT_SECONDS = _read_float_env(
    "FASTAPI_RATE_LIMIT_REDIS_TIMEOUT_SECONDS",
    0.25,
    minimum=0.05,
)
FASTAPI_RATE_LIMIT_BACKEND_COOLDOWN_SECONDS = _read_float_env(
    "FASTAPI_RATE_LIMIT_BACKEND_COOLDOWN_SECONDS",
    30.0,
    minimum=0.0,
)

RATE_LIMIT_SCHEDULE_SEARCH = RateLimitSettings(
    limit=_read_int_env("FASTAPI_RATE_LIMIT_SCHEDULE_SEARCH_LIMIT", 60, minimum=0),
    window_seconds=_read_int_env("FASTAPI_RATE_LIMIT_SCHEDULE_SEARCH_WINDOW_SECONDS", 60),
)
RATE_LIMIT_STUDIO_COMPILE = RateLimitSettings(
    limit=_read_int_env("FASTAPI_RATE_LIMIT_STUDIO_COMPILE_LIMIT", 10, minimum=0),
    window_seconds=_read_int_env("FASTAPI_RATE_LIMIT_STUDIO_COMPILE_WINDOW_SECONDS", 60),
)
RATE_LIMIT_STATS_PDF_EXPORT = RateLimitSettings(
    limit=_read_int_env("FASTAPI_RATE_LIMIT_STATS_PDF_EXPORT_LIMIT", 6, minimum=0),
    window_seconds=_read_int_env("FASTAPI_RATE_LIMIT_STATS_PDF_EXPORT_WINDOW_SECONDS", 60),
)
