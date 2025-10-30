#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

# Default to 'latest' if tags are not provided
BOT_TAG=${1:-latest}
API_TAG=${2:-latest}
SCHEDULER_TAG=${3:-latest}


export BOT_IMAGE="ghcr.io/Ackrome/matplobbot-bot:${BOT_TAG}"
export API_IMAGE="ghcr.io/Ackrome/matplobbot-api:${API_TAG}"
export SCHEDULER_IMAGE="ghcr.io/Ackrome/matplobbot-scheduler:${SCHEDULER_TAG}"

echo "--- Pulling new images from ghcr.io ---"
docker compose -f docker-compose.prod.yml pull

echo "--- Restarting services with new images ---"
# Use the new command here as well
BOT_TAG=${BOT_TAG} API_TAG=${API_TAG} SCHEDULER_TAG=${SCHEDULER_TAG} docker compose -f 'docker-compose.prod.yml' up -d --remove-orphans


echo "--- Cleaning up old images ---"
docker image prune -f

echo "--- Deployment successful! ---"