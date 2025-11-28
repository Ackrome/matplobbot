#!/bin/bash
set -e # Выход при любой ошибке

# Читаем аргументы (теги), переданные из Jenkins
# Если аргумент не передан, используем 'latest'
BOT_TAG=${1:-latest}
API_TAG=${2:-latest}
SCHEDULER_TAG=${3:-latest}
WORKER_TAG=${4:-latest}

# Экспортируем переменные, чтобы docker compose мог их подхватить
export BOT_IMAGE="ghcr.io/Ackrome/matplobbot-bot:${BOT_TAG}"
export API_IMAGE="ghcr.io/Ackrome/matplobbot-api:${API_TAG}"
export SCHEDULER_IMAGE="ghcr.io/Ackrome/matplobbot-scheduler:${SCHEDULER_TAG}"
export WORKER_IMAGE="ghcr.io/Ackrome/matplobbot-worker:${WORKER_TAG}"

echo "--- Pulling new images from ghcr.io ---"
# Подтягиваем новые образы
docker compose -f docker-compose.prod.yml pull

echo "--- Restarting services with new images ---"
# Перезапускаем контейнеры. 
# Передаем переменные окружения прямо перед командой для надежности (хотя export выше тоже работает)
BOT_TAG=${BOT_TAG} API_TAG=${API_TAG} SCHEDULER_TAG=${SCHEDULER_TAG} WORKER_TAG=${WORKER_TAG} docker compose -f 'docker-compose.prod.yml' up -d --remove-orphans

echo "--- Cleaning up old images ---"
# Удаляем старые неиспользуемые образы, чтобы не забивать диск
docker image prune -f

echo "--- Deployment successful! ---"