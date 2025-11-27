# shared_lib/models.py
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, JSON, Time, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    user_id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=False)
    avatar_pic_url = Column(String, nullable=True)
    settings = Column(JSON, server_default='{}')
    onboarding_completed = Column(Boolean, server_default='false')

class UserAction(Base):
    __tablename__ = 'user_actions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    action_type = Column(String, nullable=False)
    action_details = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class UserFavorite(Base):
    __tablename__ = 'user_favorites'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    code_path = Column(String, nullable=False)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (UniqueConstraint('user_id', 'code_path', name='uq_user_favorites_path'),)

class LatexCache(Base):
    __tablename__ = 'latex_cache'

    formula_hash = Column(String, primary_key=True)
    image_url = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class UserGithubRepo(Base):
    __tablename__ = 'user_github_repos'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    repo_path = Column(String, nullable=False)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint('user_id', 'repo_path', name='uq_user_repos_path'),)

class UserScheduleSubscription(Base):
    __tablename__ = 'user_schedule_subscriptions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    entity_name = Column(String, nullable=False)
    notification_time = Column(Time, nullable=False)
    is_active = Column(Boolean, server_default='true')
    last_schedule_hash = Column(String, nullable=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)
    message_thread_id = Column(BigInteger, nullable=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('chat_id', 'entity_type', 'entity_id', 'notification_time', name='uq_schedule_subs'),
    )

class ChatSettings(Base):
    __tablename__ = 'chat_settings'

    chat_id = Column(BigInteger, primary_key=True)
    settings = Column(JSON, server_default='{}')

class DisciplineShortName(Base):
    __tablename__ = 'discipline_short_names'

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String, nullable=False, unique=True)
    short_name = Column(String, nullable=False)
    approved_by = Column(BigInteger, ForeignKey('users.user_id', ondelete='SET NULL'))
    approved_at = Column(DateTime(timezone=True), server_default=func.now())

class UserDisabledShortName(Base):
    __tablename__ = 'user_disabled_short_names'

    user_id = Column(BigInteger, ForeignKey('users.user_id', ondelete='CASCADE'), primary_key=True)
    short_name_id = Column(Integer, ForeignKey('discipline_short_names.id', ondelete='CASCADE'), primary_key=True)