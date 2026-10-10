#!/usr/bin/env bash
set -euo pipefail
SOURCE_COMMIT="${1:?Expected accepted source commit is required}"
printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'

# Use the same effective credentials as the API. Dotenv is not a shell script:
# sourcing it can expand special characters in passwords or execute substitutions.
SMOKE_ENV="$(docker compose -f docker-compose.prod.yml exec -T mpb-fastapi-stats python -c '
import os
import shlex
for name in ("STATS_USER", "STATS_PASS", "PUBLIC_SITE_URL"):
    print(name + "=" + shlex.quote(os.environ.get(name, "")))
' </dev/null)"
eval "$SMOKE_ENV"
unset SMOKE_ENV

retry_http() {
  url="$1"
  attempts="${2:-30}"
  sleep_seconds="${3:-2}"
  i=1
  while [ "$i" -le "$attempts" ]; do
    if curl -fsS "$url" >/dev/null; then
      echo "Smoke check OK: $url"
      return 0
    fi
    echo "Waiting for $url ($i/$attempts)..."
    sleep "$sleep_seconds"
    i=$((i + 1))
  done
  echo "Smoke check FAILED: $url"
  return 1
}

check_ws_upgrade() {
  url="$1"
  token="$2"
  status="$(curl --http1.1 -sS -o /dev/null -w '%{http_code}' --max-time 5 \
    -H 'Connection: Upgrade' \
    -H 'Upgrade: websocket' \
    -H 'Sec-WebSocket-Version: 13' \
    -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
    "${url}?token=${token}" || true)"
  if [ "$status" != "101" ]; then
    echo "Smoke check FAILED: WebSocket upgrade returned HTTP $status for $url"
    return 1
  fi
  echo "Smoke check OK: WebSocket upgrade through $url"
}

# Service health endpoints
retry_http "http://127.0.0.1:9583/api/stats/health" 40 3
retry_http "http://127.0.0.1:9584/health" 40 3

# Both positive authentication and anonymous access protection must pass.
if [ -n "${STATS_USER:-}" ] && [ -n "${STATS_PASS:-}" ]; then
  LOGIN_RESP_FILE="$(mktemp)"
  trap 'rm -f "$LOGIN_RESP_FILE"' EXIT
  LOGIN_STATUS="$(curl -sS -o "$LOGIN_RESP_FILE" -w '%{http_code}' -X POST "http://127.0.0.1:9583/api/auth/login" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode "username=${STATS_USER}" \
    --data-urlencode "password=${STATS_PASS}" || true)"

  if [ "$LOGIN_STATUS" = "200" ]; then
    TOKEN="$(sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p' "$LOGIN_RESP_FILE")"
    if [ -z "$TOKEN" ]; then
      echo "Smoke check FAILED: could not parse access_token from login response"
      rm -f "$LOGIN_RESP_FILE"
      exit 1
    fi

    LEADERBOARD_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' \
      -H "Authorization: Bearer ${TOKEN}" \
      "http://127.0.0.1:9583/api/stats/leaderboard" || true)"

    if [ "$LEADERBOARD_STATUS" = "200" ]; then
      echo "Smoke check OK: leaderboard endpoint (authenticated)"
      check_ws_upgrade "http://127.0.0.1:8080/ws/stats/total_actions" "$TOKEN"
      if [ -n "${PUBLIC_SITE_URL:-}" ]; then
        check_ws_upgrade "${PUBLIC_SITE_URL%/}/ws/stats/total_actions" "$TOKEN"
      fi
    else
      echo "Smoke check FAILED: authenticated leaderboard returned HTTP $LEADERBOARD_STATUS"
      rm -f "$LOGIN_RESP_FILE"
      exit 1
    fi
  else
    echo "Smoke check FAILED: expected admin login returned HTTP $LOGIN_STATUS"
    rm -f "$LOGIN_RESP_FILE"
    exit 1
  fi

  rm -f "$LOGIN_RESP_FILE"
else
  echo "Smoke check FAILED: expected admin credentials are missing in the API container"
  exit 1
fi

PROTECTED_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:9583/api/stats/leaderboard" || true)"
if [ "$PROTECTED_STATUS" = "401" ] || [ "$PROTECTED_STATUS" = "403" ]; then
  echo "Smoke check OK: leaderboard endpoint is protected (HTTP $PROTECTED_STATUS)"
else
  echo "Smoke check FAILED: leaderboard endpoint returned unexpected HTTP $PROTECTED_STATUS without auth"
  exit 1
fi
bash ./deploy.sh --finalize </dev/null
RELEASE_SOURCE_COMMIT="$SOURCE_COMMIT" python3 - <<'PY'
import json
import os
from pathlib import Path

state = Path(".release-state")
record = json.loads((state / "current.json").read_text(encoding="utf-8"))
if record.get("status") != "successful" or record.get("manifest", {}).get("commit") != os.environ["RELEASE_SOURCE_COMMIT"]:
    raise SystemExit("Smoke check FAILED: accepted release pointer does not match the expected commit")
if any((state / name).exists() for name in ("attempt.json", "pending.json", "rollback-pending.json")):
    raise SystemExit("Smoke check FAILED: release still has pending state")
PY
printf 'Release smoke and finalization completed: %s\n' "$SOURCE_COMMIT"
