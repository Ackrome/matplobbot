#!/usr/bin/env bash
set -euo pipefail

image=${1:?Pass a proxy image reference}
container=$(docker run -d --network none --tmpfs /app/cache "$image")
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT

# The loopback target checks both the cleaner and the actual Mihomo SOCKS listener.
for _ in {1..30}; do
    if docker exec "$container" curl --fail --silent --noproxy '' --max-time 2 \
        --socks5-hostname 127.0.0.1:20170 http://127.0.0.1:8080/health >/dev/null; then
        echo 'Proxy image passed an isolated SOCKS and cleaner check.'
        exit 0
    fi
    sleep 1
done

docker logs --tail 30 "$container" >&2
exit 1
