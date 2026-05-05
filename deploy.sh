#!/bin/bash
set -Eeuo pipefail

# Tags passed from Jenkins (defaults to latest)
BOT_TAG=${1:-latest}
API_TAG=${2:-latest}
SCHEDULER_TAG=${3:-latest}
WORKER_TAG=${4:-latest}
COMPOSE_FILE="docker-compose.prod.yml"

# Export image references for compose interpolation
export BOT_IMAGE="ghcr.io/Ackrome/matplobbot-bot:${BOT_TAG}"
export API_IMAGE="ghcr.io/Ackrome/matplobbot-api:${API_TAG}"
export SCHEDULER_IMAGE="ghcr.io/Ackrome/matplobbot-scheduler:${SCHEDULER_TAG}"
export WORKER_IMAGE="ghcr.io/Ackrome/matplobbot-worker:${WORKER_TAG}"

is_lease_error() {
  grep -Eqi 'lease .* not found|lease does not exist|failed commit on ref'
}

is_retryable_pull_error() {
  grep -Eqi 'lease .* not found|lease does not exist|failed commit on ref|connection reset by peer|TLS handshake timeout|i/o timeout|context deadline exceeded|unexpected EOF|EOF$|net/http: request canceled|temporary failure in name resolution|no such host|server misbehaving|too many requests|toomanyrequests|502 Bad Gateway|503 Service Unavailable|504 Gateway Timeout|failed to fetch .* token'
}

repair_docker_pull_state() {
  echo "Detected Docker/containerd lease pull error. Running safe cleanup before retry..."
  docker builder prune -af || true
  docker image prune -af --filter 'dangling=true' || true
  sleep 3
}

pull_service_with_retry() {
  local service="$1"
  local max_attempts=3
  local attempt=1
  local output=""

  while [ "$attempt" -le "$max_attempts" ]; do
    echo "Pulling service '$service' (attempt ${attempt}/${max_attempts})..."

    if output="$(COMPOSE_PARALLEL_LIMIT=1 docker compose -f "$COMPOSE_FILE" pull "$service" 2>&1)"; then
      echo "$output"
      return 0
    fi

    echo "$output"

    if printf '%s' "$output" | is_retryable_pull_error; then
      if printf '%s' "$output" | is_lease_error; then
        repair_docker_pull_state
      else
        local backoff_seconds=$((attempt * 5))
        echo "Transient pull failure for '$service'. Retrying in ${backoff_seconds}s..."
        sleep "$backoff_seconds"
      fi
      attempt=$((attempt + 1))
      continue
    fi

    echo "Pull failed for '$service' due to non-retryable error."
    return 1
  done

  echo "Pull failed for '$service' after ${max_attempts} attempts."
  return 1
}

pull_images_resiliently() {
  local services=(
    mpb-telegram-bot
    mpb-scheduler
    migrator
    mpb-worker
    mpb-fastapi-stats
  )

  for service in "${services[@]}"; do
    pull_service_with_retry "$service"
  done
}

echo "--- Pulling application images from ghcr.io ---"
pull_images_resiliently

echo "--- Restarting services with new images ---"
BOT_TAG=${BOT_TAG} API_TAG=${API_TAG} SCHEDULER_TAG=${SCHEDULER_TAG} WORKER_TAG=${WORKER_TAG} \
  docker compose -f "$COMPOSE_FILE" up -d --build --remove-orphans

echo "--- Reloading services that consume repo-mounted config files ---"
docker compose -f "$COMPOSE_FILE" restart main-site-frontend caddy

echo "--- Cleaning up old images ---"
docker image prune -f

echo "--- Deployment successful! ---"
