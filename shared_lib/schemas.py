from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

# Базовая модель действия
class UserActionSchema(BaseModel):
    id: int
    action_type: str
    action_details: Optional[str] = None
    timestamp: str # Мы форматируем дату в строку в SQL запросе, поэтому здесь str

# Модель для профиля пользователя
class UserDetailsSchema(BaseModel):
    user_id: int
    full_name: str
    username: Optional[str] = "Нет username"
    avatar_pic_url: Optional[str] = None
    total_actions: int

class PaginationSchema(BaseModel):
    current_page: int
    total_pages: int
    page_size: int
    sort_by: str
    sort_order: str

# Ответ для эндпоинта профиля
class UserProfileResponse(BaseModel):
    user_details: UserDetailsSchema
    actions: List[UserActionSchema]
    pagination: PaginationSchema
    total_actions: int

# Модели для других эндпоинтов
class LeaderboardEntry(BaseModel):
    user_id: int
    full_name: str
    username: str
    avatar_pic_url: Optional[str]
    actions_count: int
    last_action_time: Optional[str]

class ActionTypeStat(BaseModel):
    action_type: str
    count: int