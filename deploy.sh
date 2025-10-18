#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

# Default to 'latest' if tags are not provided
BOT_TAG=${1:-latest}
API_TAG=${2:-latest}


export BOT_IMAGE="ghcr.io/Ackrome/matplobbot-bot:${BOT_TAG}"
export API_IMAGE="ghcr.io/Ackrome/matplobbot-api:${API_TAG}"

echo "--- Pulling new images ---"
docker-compose -f docker-compose.prod.yml pull

echo "--- Restarting services with new images ---"
# Use the exported variables in the compose file by specifying them in the command
BOT_IMAGE=$BOT_IMAGE API_IMAGE=$API_IMAGE docker-compose -f docker-compose.prod.yml up -d --remove-orphans

echo "--- Cleaning up old images ---"
docker image prune -f

echo "--- Deployment successful! ---"