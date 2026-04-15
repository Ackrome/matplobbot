# shared_lib/schemas.py
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# --- Конфигурация Pydantic V2 ---
# extra='ignore': Если база вернет лишние поля, Pydantic их просто проигнорирует, а не упадет с ошибкой.
# from_attributes=True: Позволяет создавать модели из объектов (ORM-style), если это понадобится в будущем.
BASE_CONFIG = ConfigDict(extra="ignore", from_attributes=True)
ALLOW_EXTRA_CONFIG = ConfigDict(extra="allow", from_attributes=True)

# --- Вспомогательные модели ---


class PaginationSchema(BaseModel):
    """Схема пагинации для списков."""

    current_page: int = Field(
        ..., description="Текущий номер страницы (начиная с 1)", ge=1, example=1
    )
    total_pages: int = Field(..., description="Общее количество страниц", ge=0, example=10)
    page_size: int = Field(..., description="Количество элементов на странице", ge=1, example=50)
    sort_by: str = Field(
        ..., description="Поле, по которому выполнена сортировка", example="timestamp"
    )
    sort_order: str = Field(
        ...,
        description="Порядок сортировки (asc/desc)",
        pattern="^(asc|desc|ASC|DESC)$",
        example="desc",
    )

    model_config = BASE_CONFIG


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Текст сообщения для отправки пользователю")


# --- Модели Пользователей ---


class UserSummarySchema(BaseModel):
    """Краткая информация о пользователе (для списков)."""

    user_id: int = Field(
        ..., description="Уникальный ID пользователя в Telegram", example=123456789
    )
    full_name: str = Field(
        ..., description="Полное имя пользователя из Telegram", example="Иван Иванов"
    )
    username: str | None = Field(
        "Нет username", description="Никнейм пользователя (без @)", example="ivan_dev"
    )

    model_config = BASE_CONFIG


class UserDetailsSchema(UserSummarySchema):
    """Полная информация о пользователе для профиля."""

    avatar_pic_url: str | None = Field(
        None,
        description="URL аватара пользователя (проксированный через Telegram API)",
        example="https://api.telegram.org/file/...",
    )
    total_actions: int = Field(
        ..., description="Общее количество действий, совершенных пользователем", ge=0, example=1500
    )


# --- Модели Действий ---


class UserActionSchema(BaseModel):
    """Модель одного действия пользователя."""

    id: int = Field(..., description="Уникальный ID действия в БД", example=42)
    action_type: str = Field(..., description="Тип действия", example="command")
    action_details: str | None = Field(
        None,
        description="Детали действия (например, текст команды или сообщения)",
        example="/start",
    )
    timestamp: str = Field(
        ..., description="Время действия (форматированная строка)", example="2023-10-27 14:30:00"
    )

    model_config = BASE_CONFIG


# --- Модели Ответов API (Response Models) ---


class UserProfileResponse(BaseModel):
    """Ответ эндпоинта профиля пользователя."""

    user_details: UserDetailsSchema = Field(..., description="Основная информация о пользователе")
    actions: list[UserActionSchema] = Field(
        ..., description="Список последних действий пользователя на текущей странице"
    )
    pagination: PaginationSchema = Field(..., description="Метаданные пагинации")

    # Дублируем total_actions на верхний уровень для удобства фронтенда (опционально, но часто полезно)
    total_actions: int = Field(
        ..., description="Дубликат общего количества действий для быстрого доступа"
    )

    model_config = BASE_CONFIG


class ActionUsersResponse(BaseModel):
    """Ответ эндпоинта списка пользователей по действию."""

    users: list[UserSummarySchema] = Field(
        ..., description="Список пользователей, совершивших действие"
    )
    pagination: PaginationSchema = Field(..., description="Метаданные пагинации")

    model_config = BASE_CONFIG


class ExportActionsResponse(BaseModel):
    """Ответ эндпоинта экспорта всех действий."""

    actions: list[UserActionSchema] = Field(..., description="Полный список действий пользователя")

    model_config = BASE_CONFIG


# --- Модели для Статистики (Dashboard) ---


class LeaderboardEntry(BaseModel):
    """Запись в таблице лидеров."""

    user_id: int
    full_name: str
    username: str
    avatar_pic_url: str | None = None
    actions_count: int
    last_action_time: str | None = None

    model_config = BASE_CONFIG


class ActionTypeStat(BaseModel):
    """Статистика по типам действий."""

    action_type: str
    count: int

    model_config = BASE_CONFIG


class ActivityOverTimeEntry(BaseModel):
    """Запись активности за период."""

    period: str
    count: int

    model_config = BASE_CONFIG


class NewUserStatEntry(BaseModel):
    """Статистика новых пользователей по дням."""

    date: str
    count: int

    model_config = BASE_CONFIG


class WebUserResponse(BaseModel):
    id: int
    username: str | None
    telegram_id: int | None
    role: str
    preferences: dict[str, Any] = Field(default_factory=dict)
    created_at: Any
    model_config = BASE_CONFIG


# --- СХЕМЫ ДЛЯ WEB ACCOUNTS & TELEGRAM LOGIN ---
class WebAccountCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)


class WebAccountPreferencesUpdate(BaseModel):
    preferences: dict[str, Any] = Field(
        default_factory=dict, description="Любые настройки фронтенда"
    )


class Token(BaseModel):
    access_token: str
    token_type: str


class TelegramAuthData(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


class CurrentUserResponse(BaseModel):
    id: int
    username: str
    role: str
    avatar_url: str | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)

    model_config = BASE_CONFIG


class CalendarSubscriptionEligibility(BaseModel):
    available: bool = False
    has_telegram_link: bool = False
    has_active_subscriptions: bool = False
    reasons: list[str] = Field(default_factory=list)
    detail: str | None = None

    model_config = BASE_CONFIG


class CalendarSubscriptionSourceSummary(BaseModel):
    total_subscriptions: int = 0
    active_subscriptions: int = 0
    active_entities: int = 0

    model_config = BASE_CONFIG


class CalendarSubscriptionLinks(BaseModel):
    http_url: str | None = None
    webcal_url: str | None = None
    download_url: str | None = None
    preview_url: str | None = None
    masked_http_url: str | None = None

    model_config = BASE_CONFIG


class CalendarSubscriptionHealth(BaseModel):
    event_count: int = 0
    next_event_at: str | None = None
    next_event_label: str | None = None
    last_generated_at: str | None = None
    source_updated_at: str | None = None
    cache_status: str = "empty"
    used_cached_sources: int = 0
    total_sources: int = 0
    last_accessed_at: str | None = None

    model_config = BASE_CONFIG


class CalendarSubscriptionProfile(BaseModel):
    id: str
    name: str
    kind: Literal["built_in", "custom"] = "built_in"
    lesson_mode: Literal["all", "exams_only"] = "all"
    selected: bool = False
    can_delete: bool = False
    entity_type: str | None = None
    entity_id: str | None = None
    entity_name: str | None = None
    modules: list[str] = Field(default_factory=list)
    module_count: int = 0
    subscription_count: int = 0
    scope_label: str | None = None
    links: CalendarSubscriptionLinks = Field(default_factory=CalendarSubscriptionLinks)
    health: CalendarSubscriptionHealth = Field(default_factory=CalendarSubscriptionHealth)

    model_config = BASE_CONFIG


class CalendarSubscriptionResponse(BaseModel):
    enabled: bool = False
    sync_enabled: bool = True
    selected_profile_id: str | None = None
    profile_limit: int = 0
    http_url: str | None = None
    webcal_url: str | None = None
    download_url: str | None = None
    preview_url: str | None = None
    masked_http_url: str | None = None
    eligibility: CalendarSubscriptionEligibility = Field(
        default_factory=CalendarSubscriptionEligibility
    )
    source_summary: CalendarSubscriptionSourceSummary = Field(
        default_factory=CalendarSubscriptionSourceSummary
    )
    profiles: list[CalendarSubscriptionProfile] = Field(default_factory=list)

    model_config = BASE_CONFIG


class CalendarSubscriptionToggleRequest(BaseModel):
    enabled: bool


class CalendarSubscriptionProfileCreateRequest(BaseModel):
    entity_type: str = Field(..., min_length=1, max_length=32)
    entity_id: str = Field(..., min_length=1, max_length=128)
    entity_name: str = Field(..., min_length=1, max_length=255)
    lesson_mode: Literal["all", "exams_only"] = "all"
    modules: list[str] = Field(default_factory=list)


class CalendarSubscriptionProfileSelectRequest(BaseModel):
    profile_id: str = Field(..., min_length=1, max_length=64)


class StatusResponse(BaseModel):
    status: Literal["success"] = "success"

    model_config = BASE_CONFIG


class CorrelationStatusResponse(StatusResponse):
    correlation_id: str = Field(..., description="Correlation id for tracing and audit log lookup.")

    model_config = BASE_CONFIG


class HealthStatusResponse(BaseModel):
    status: Literal["ok"] = "ok"
    database: Literal["connected"] = "connected"

    model_config = BASE_CONFIG


class ScheduleSearchResultSchema(BaseModel):
    id: str = Field(..., description="Entity identifier used by the schedule API.")
    label: str = Field(..., description="Display label for the entity.")
    description: str = Field(..., description="Human-friendly entity description.")
    type: Literal["group", "person", "auditorium"] = Field(
        ..., description="Normalized entity type."
    )
    is_offline: bool = Field(
        False,
        description="True when the result came from local cache instead of the live university API.",
    )

    model_config = BASE_CONFIG


class CachedScheduleEntitySchema(BaseModel):
    id: str = Field(..., description="Cached entity identifier.")
    type: str = Field(..., description="Entity type represented in cache.")
    label: str = Field(..., description="Display label for the cached entity.")

    model_config = BASE_CONFIG


class ScheduleFallbackCountersResponse(BaseModel):
    ruz_api_success: int = Field(0, ge=0)
    cache_fallback: int = Field(0, ge=0)
    no_cache: int = Field(0, ge=0)

    model_config = ALLOW_EXTRA_CONFIG


class ScheduleLessonSchema(BaseModel):
    date: str | None = None
    discipline: str | None = None
    discipline_short: str | None = None
    discipline_full: str | None = None
    group: str | None = None
    beginLesson: str | None = None
    endLesson: str | None = None
    auditorium: str | None = None
    kindOfWork: str | None = None
    lecturer: str | None = None
    lecturer_title: str | None = None
    simple_type: str | None = None
    module: str | None = None
    source_entity_type: str | None = None
    source_entity_id: str | None = None

    model_config = ALLOW_EXTRA_CONFIG


class LoadedBoundsSchema(BaseModel):
    start: str = Field(..., description="Start date of the loaded schedule window in YYYY-MM-DD.")
    end: str = Field(..., description="End date of the loaded schedule window in YYYY-MM-DD.")

    model_config = BASE_CONFIG


class ScheduleDataResponse(BaseModel):
    schedule: list[ScheduleLessonSchema] = Field(default_factory=list)
    available_modules: list[str] = Field(default_factory=list)
    is_offline: bool = False
    source_updated_at: str | None = None
    loaded_bounds: LoadedBoundsSchema

    model_config = BASE_CONFIG


class ActivitySeriesEntry(BaseModel):
    period_start: str = Field(..., description="Bucket label for the selected aggregation period.")
    actions_count: int = Field(..., ge=0, description="Number of actions in the bucket.")

    model_config = BASE_CONFIG


class StudioProjectSummary(BaseModel):
    id: int
    name: str
    type: str

    model_config = BASE_CONFIG


class StudioProjectFileSchema(BaseModel):
    id: int
    path: str
    is_main: bool
    is_binary: bool
    content: str | None = None

    model_config = BASE_CONFIG


class StudioUploadAssetResponse(StatusResponse):
    filename: str = Field(..., description="Stored asset filename inside the project.")

    model_config = BASE_CONFIG


class StudioTelegramSendResponse(StatusResponse):
    message: str = Field(..., description="User-facing result message after Telegram delivery.")

    model_config = BASE_CONFIG


class StudioCompileErrorSchema(BaseModel):
    line: int = Field(..., ge=1)
    message: str

    model_config = BASE_CONFIG


class StudioCompileResponse(BaseModel):
    status: str = Field(..., description="Compile task status reported by the worker.")
    pdf: str | None = Field(None, description="Base64-encoded PDF output when compilation succeeds.")
    image: str | None = Field(
        None,
        description="Base64-encoded PNG output for Mermaid or LaTeX image rendering flows.",
    )
    html: str | None = Field(None, description="Rendered HTML payload for Markdown preview flows.")
    build_cache: str | None = Field(
        None,
        description="Base64-encoded incremental build cache returned by project compilation.",
    )
    message: str | None = None
    error: str | None = None
    errors: list[StudioCompileErrorSchema] = Field(default_factory=list)

    model_config = ALLOW_EXTRA_CONFIG
