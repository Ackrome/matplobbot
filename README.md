# Matplobbot: Telegram-бот и FastAPI-приложение для статистики

## Обзор проекта

Этот проект включает в себя два основных компонента:

1. **Matplobbot (Telegram-бот)**: Бот, предоставляющий пользователям структуры кода из библиотеки `matplotlib`.
2. **FastAPI Stats App**: Веб-приложение на FastAPI, предназначенное для отображения статистики работы Telegram-бота.

Проект использует `aiogram` для Telegram-бота и `FastAPI` для веб-приложения.

## Компоненты проекта

### 1. Matplobbot (Telegram-бот)

#### Обзор бота

Matplobbot — это Telegram-бот, разработанный для быстрого доступа к примерам кода (структурам) из различных модулей библиотеки `matplotlib`.
Он поможет вам легко находить нужные фрагменты кода для визуализации данных.

* Создан с использованием `aiogram`.
* Предназначен для работы с библиотекой `matplotlib`. Актуальные версии зависимостей указаны в `requirements.txt` (или в специфичном файле для бота, например, `bot/requirements.txt`).

#### Необходимые переменные окружения (для бота)

Для работы бота необходимо создать файл `.env` (например, в корне проекта или в директории `bot/`) и указать в нем следующие переменные:
```
    BOT_TOKEN=ВАШ_ТЕЛЕГРАМ_БОТ_ТОКЕН
    ADMIN_USER_ID=ВАШ_ТЕЛЕГРАМ_USER_ID_АДМИНИСТРАТОРА
```
#### Установка и локальный запуск (бота)

1. Клонируйте репозиторий:
```
   git clone https://github.com/Ackrome/matplobbot.git
   cd matplobbot
```
2. Перейдите в директорию бота (если она существует, например, `cd bot`).
3. Создайте и активируйте виртуальное окружение:
```
   python -m venv venv_bot
   source venv_bot/bin/activate  # для Linux/macOS
   # venv_bot\Scripts\activate    # для Windows
```
4. Установите зависимости:

   pip install -r requirements.txt # или requirements-bot.txt
5. Создайте файл `.env` с переменными окружения (см. выше).
6. Запустите бота (например, если главный файл `main.py`):
```
   python main.py
```
#### Функционал бота

* Пользователь запускает бота в Telegram (например, `@matplobbot`) и получает приветственное сообщение.
* Предлагается команда `/ask` для начала работы.
* Пользователь выбирает подмодуль `matplotlib`, затем тему и конкретную структуру кода.
* Бот выводит информацию о запросе и соответствующий фрагмент кода:

  > Ваш запрос:
  > {подмодуль}
  > {тема}
  > {структура кода}
  >
  > {Код}
  >

### 2. FastAPI Stats App (Веб-приложение для статистики)

#### Обзор FastAPI-приложения

`fastapi_stats_app` — это веб-приложение, созданное с использованием FastAPI. Его основная задача — сбор и отображение статистики использования Telegram-бота `Matplobbot`. Это может включать количество запросов, активных пользователей, наиболее популярные темы и другую релевантную информацию.

#### Необходимые переменные окружения (для FastAPI-приложения)

В зависимости от реализации, могут потребоваться переменные окружения, например, для подключения к базе данных, где хранятся логи и статистика. Создайте файл `.env` (например, в директории `fastapi_stats_app/`).
```
    # Пример:
    # DATABASE_URL=postgresql://user:password@host:port/dbname
    # STATS_APP_PORT=8000
```
#### Установка и локальный запуск (FastAPI-приложения)

1. Перейдите в директорию FastAPI-приложения (например, `cd fastapi_stats_app`).
2. Создайте и активируйте виртуальное окружение:
```
   python -m venv venv_stats
   source venv_stats/bin/activate  # для Linux/macOS
   # venv_stats\Scripts\activate    # для Windows
```
3. Установите зависимости (например, из файла `requirements-stats.txt`):
```
   pip install -r requirements-stats.txt
```
4. Создайте файл `.env` с необходимыми переменными окружения.
5. Запустите FastAPI-приложение с помощью Uvicorn (например, если главный файл `main.py` и экземпляр FastAPI называется `app`):
```
   uvicorn main:app --reload --port 8000
```
#### Функционал FastAPI-приложения

* Предоставление веб-интерфейса для просмотра агрегированной статистики работы бота.
* Отображение ключевых метрик: количество пользователей, запросов, ошибок и т.д.
* (Возможно) API эндпоинты для получения статистических данных в формате JSON.

## Запуск с помощью Docker (для всего проекта)

Если проект настроен для запуска с использованием Docker и Docker Compose (через файл `docker-compose.yml`), вы можете запустить оба компонента следующими командами:

1. Убедитесь, что Docker и Docker Compose установлены.
2. Создайте необходимые файлы `.env` для каждого компонента (бота и FastAPI-приложения) в соответствующих директориях или в корне проекта, если `docker-compose.yml` настроен на их чтение оттуда.
3. Соберите и запустите контейнеры:
```
   docker-compose up --build
```
   Для запуска в фоновом режиме:
```
   docker-compose up -d --build
```