import asyncio
from logging.config import fileConfig
import os
import sys
from dotenv import load_dotenv # <--- Добавлено

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# 1. Загружаем переменные окружения из .env файла
load_dotenv()

# 2. Добавляем путь к проекту, чтобы видеть shared_lib
sys.path.append(os.getcwd())

# 3. Импортируем модели
from shared_lib.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def get_url():
    """
    Умное получение URL базы данных.
    1. Читает из ENV.
    2. Меняет драйвер на asyncpg.
    3. Если запуск локальный (Windows/Mac), меняет 'postgres' на 'localhost'.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        # Fallback для тестов, но лучше чтобы падало, если нет URL
        return "postgresql+asyncpg://user:pass@localhost/dbname"

    # Fix 1: Sync -> Async driver
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    # Fix 2: Localhost fix for Windows development
    # Если мы запускаем скрипт не в Докере (например, на Windows),
    # то хост 'postgres' (имя контейнера) недоступен. Меняем на localhost.
    # Проверяем по наличию специфичных для Win переменных или отсутствию Docker-файлов
    is_running_in_docker = os.path.exists('/.dockerenv')
    
    if not is_running_in_docker and "@postgres" in url:
        print("Detected local run: switching DB host from 'postgres' to 'localhost'")
        url = url.replace("@postgres", "@localhost")
        
    return url

def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section)
    
    # Подменяем URL в конфиге на наш "умный" URL
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())