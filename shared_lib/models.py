# shared_lib/models.py
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=False)
    avatar_pic_url = Column(String, nullable=True)
    settings = Column(JSON, server_default="{}")
    onboarding_completed = Column(Boolean, server_default="false")
    calendar_secret = Column(String, unique=True, nullable=True)


class UserAction(Base):
    __tablename__ = "user_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    action_type = Column(String, nullable=False)
    action_details = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())


class UserFavorite(Base):
    __tablename__ = "user_favorites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    code_path = Column(String, nullable=False)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "code_path", name="uq_user_favorites_path"),)


class LatexCache(Base):
    __tablename__ = "latex_cache"

    formula_hash = Column(String, primary_key=True)
    image_url = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserGithubRepo(Base):
    __tablename__ = "user_github_repos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    repo_path = Column(String, nullable=False)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "repo_path", name="uq_user_repos_path"),)


class UserScheduleSubscription(Base):
    __tablename__ = "user_schedule_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    entity_name = Column(String, nullable=False)
    notification_time = Column(Time, nullable=False)
    is_active = Column(Boolean, server_default="true")
    last_schedule_hash = Column(String, nullable=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)
    message_thread_id = Column(BigInteger, nullable=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    selected_modules = Column(JSON, server_default="[]", nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "chat_id", "entity_type", "entity_id", "notification_time", name="uq_schedule_subs"
        ),
    )


class ChatSettings(Base):
    __tablename__ = "chat_settings"

    chat_id = Column(BigInteger, primary_key=True)
    settings = Column(JSON, server_default="{}")


class DisciplineShortName(Base):
    __tablename__ = "discipline_short_names"

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String, nullable=False, unique=True)
    short_name = Column(String, nullable=False)
    approved_by = Column(BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"))
    approved_at = Column(DateTime(timezone=True), server_default=func.now())


class UserDisabledShortName(Base):
    __tablename__ = "user_disabled_short_names"

    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    short_name_id = Column(
        Integer, ForeignKey("discipline_short_names.id", ondelete="CASCADE"), primary_key=True
    )


class CachedSchedule(Base):
    """Stores the raw schedule JSON for entities to avoid repeated API calls."""

    __tablename__ = "cached_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    schedule_data = Column(JSONB, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_cached_schedule_entity"),
    )


class SearchDocument(Base):
    __tablename__ = "search_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(String, nullable=False)
    source_path = Column(String, nullable=False)
    content = Column(String, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=True)
    content_ts = Column(TSVECTOR)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("source_type", "source_path", name="uq_search_doc_path"),)


class DisciplineModule(Base):
    __tablename__ = "discipline_modules"

    discipline_name = Column(String, primary_key=True)
    module_name = Column(String, nullable=False)


class WebAccount(Base):
    __tablename__ = "web_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(String, nullable=False, server_default="user")  # 'admin' или 'user'
    preferences = Column(JSON, server_default="{}", nullable=False)  # Настройки сайта

    # Для входа по логину/паролю
    username = Column(String, unique=True, nullable=True, index=True)
    password_hash = Column(String, nullable=True)

    # Для входа через Telegram
    telegram_id = Column(
        BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"), unique=True, nullable=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("web_accounts.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    project_type = Column(String, nullable=False, server_default="latex")
    build_cache = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProjectFile(Base):
    __tablename__ = "project_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String, nullable=False)  # e.g. 'main.tex', 'images/logo.png'
    content_text = Column(String, nullable=True)  # Для кода
    content_binary = Column(LargeBinary, nullable=True)  # Для картинок
    is_main = Column(Boolean, server_default="false")

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("project_id", "file_path", name="uq_project_file_path"),)
