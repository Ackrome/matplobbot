# shared_lib/schemas.py
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any

# --- Конфигурация Pydantic V2 ---
# extra='ignore': Если база вернет лишние поля, Pydantic их просто проигнорирует, а не упадет с ошибкой.
# from_attributes=True: Позволяет создавать модели из объектов (ORM-style), если это понадобится в будущем.
BASE_CONFIG = ConfigDict(extra='ignore', from_attributes=True)

# --- Вспомогательные модели ---

class PaginationSchema(BaseModel):
    """Схема пагинации для списков."""
    current_page: int = Field(..., description="Текущий номер страницы (начиная с 1)", ge=1, example=1)
    total_pages: int = Field(..., description="Общее количество страниц", ge=0, example=10)
    page_size: int = Field(..., description="Количество элементов на странице", ge=1, example=50)
    sort_by: str = Field(..., description="Поле, по которому выполнена сортировка", example="timestamp")
    sort_order: str = Field(..., description="Порядок сортировки (asc/desc)", pattern="^(asc|desc|ASC|DESC)$", example="desc")
    
    model_config = BASE_CONFIG



class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Текст сообщения для отправки пользователю")
# --- Модели Пользователей ---

class UserSummarySchema(BaseModel):
    """Краткая информация о пользователе (для списков)."""
    user_id: int = Field(..., description="Уникальный ID пользователя в Telegram", example=123456789)
    full_name: str = Field(..., description="Полное имя пользователя из Telegram", example="Иван Иванов")
    username: Optional[str] = Field("Нет username", description="Никнейм пользователя (без @)", example="ivan_dev")
    
    model_config = BASE_CONFIG

class UserDetailsSchema(UserSummarySchema):
    """Полная информация о пользователе для профиля."""
    avatar_pic_url: Optional[str] = Field(None, description="URL аватара пользователя (проксированный через Telegram API)", example="https://api.telegram.org/file/...")
    total_actions: int = Field(..., description="Общее количество действий, совершенных пользователем", ge=0, example=1500)

# --- Модели Действий ---

class UserActionSchema(BaseModel):
    """Модель одного действия пользователя."""
    id: int = Field(..., description="Уникальный ID действия в БД", example=42)
    action_type: str = Field(..., description="Тип действия", example="command")
    action_details: Optional[str] = Field(None, description="Детали действия (например, текст команды или сообщения)", example="/start")
    timestamp: str = Field(..., description="Время действия (форматированная строка)", example="2023-10-27 14:30:00")

    model_config = BASE_CONFIG

# --- Модели Ответов API (Response Models) ---

class UserProfileResponse(BaseModel):
    """Ответ эндпоинта профиля пользователя."""
    user_details: UserDetailsSchema = Field(..., description="Основная информация о пользователе")
    actions: List[UserActionSchema] = Field(..., description="Список последних действий пользователя на текущей странице")
    pagination: PaginationSchema = Field(..., description="Метаданные пагинации")
    
    # Дублируем total_actions на верхний уровень для удобства фронтенда (опционально, но часто полезно)
    total_actions: int = Field(..., description="Дубликат общего количества действий для быстрого доступа")

    model_config = BASE_CONFIG

class ActionUsersResponse(BaseModel):
    """Ответ эндпоинта списка пользователей по действию."""
    users: List[UserSummarySchema] = Field(..., description="Список пользователей, совершивших действие")
    pagination: PaginationSchema = Field(..., description="Метаданные пагинации")

    model_config = BASE_CONFIG

class ExportActionsResponse(BaseModel):
    """Ответ эндпоинта экспорта всех действий."""
    actions: List[UserActionSchema] = Field(..., description="Полный список действий пользователя")

    model_config = BASE_CONFIG

# --- Модели для Статистики (Dashboard) ---

class LeaderboardEntry(BaseModel):
    """Запись в таблице лидеров."""
    user_id: int
    full_name: str
    username: str
    avatar_pic_url: Optional[str] = None
    actions_count: int
    last_action_time: Optional[str] = None
    
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