#!/usr/bin/env bash
# Check the live host with the reviewed candidate code before Jenkins validation.
set -euo pipefail

deploy_host="$(bash scripts/resolve_private_ipv4.sh "${DEPLOY_HOST:-192.168.1.40}")"
fingerprint="${DEPLOY_HOST_FINGERPRINT:-${DEFAULT_DEPLOY_HOST_FINGERPRINT:-}}"
chmod 600 "$SSH_KEY_FILE"
known_hosts="$(mktemp)"
trap 'rm -f -- "$known_hosts"' EXIT

if [[ -z "$fingerprint" ]] || ! ssh-keyscan -T 5 -t ed25519 "$deploy_host" > "$known_hosts" 2>/dev/null; then
    echo 'ERROR: Could not establish the production SSH host fingerprint.' >&2
    exit 27
fi
scanned_fingerprint="$(ssh-keygen -lf "$known_hosts" -E sha256 | awk '{print $2}')"
if [[ "$scanned_fingerprint" != "$fingerprint" ]]; then
    echo 'ERROR: Production SSH host fingerprint does not match the pin.' >&2
    exit 27
fi

remote_command=$(cat <<'REMOTE'
set -eu
candidate=$(mktemp -d)
trap 'rm -rf -- "$candidate"' EXIT
tar -xf - -C "$candidate"
case "$DEPLOY_PATH" in
    '~/'*) DEPLOY_PATH="$HOME/${DEPLOY_PATH#\~/}" ;;
esac
cd "$DEPLOY_PATH" || exit 26
python3 -B "$candidate/scripts/release_deploy.py" preflight --candidate "$candidate"
REMOTE
)
printf -v remote_path '%q' "$DEPLOY_PATH"

git archive --format=tar "$SOURCE_COMMIT" \
    scripts/release_deploy.py scripts/release_manifest.py scripts/release_backup.py \
    scripts/docker_disk_guard.py scripts/worker_security.py security/worker-apparmor.template |
    timeout --kill-after=5s 90s ssh -T -i "$SSH_KEY_FILE" \
        -o BatchMode=yes -o ConnectTimeout=10 -o IdentitiesOnly=yes \
        -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519 \
        -o GlobalKnownHostsFile=/dev/null -o UserKnownHostsFile="$known_hosts" \
        "$SSH_USER@$deploy_host" "DEPLOY_PATH=$remote_path
$remote_command"
