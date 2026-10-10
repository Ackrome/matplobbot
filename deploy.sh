#!/bin/bash
set -Eeuo pipefail

write_env_atomically() {
  local target_path="${1:-.env}"
  shift || true
  local target_dir
  local target_name
  local temp_path
  local required_key

  target_dir="$(dirname -- "$target_path")"
  target_name="$(basename -- "$target_path")"
  umask 077
  temp_path="$(mktemp "${target_dir}/${target_name}.tmp.XXXXXX")"
  trap 'rm -f -- "$temp_path"' EXIT

  cat > "$temp_path"
  for required_key in "$@"; do
    if [[ ! "$required_key" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
      echo "ERROR: invalid required environment key name: $required_key" >&2
      exit 1
    fi
    if ! grep -q "^${required_key}=" "$temp_path"; then
      echo "ERROR: remote .env payload is missing $required_key" >&2
      exit 1
    fi
  done
  chmod 600 "$temp_path"
  mv -f -- "$temp_path" "$target_path"
  trap - EXIT
  echo "Remote .env keys verified without exposing values."
}

if [[ "${1:-}" == "--write-env" && "${2:-}" == ".env" ]]; then
  shift 2
  write_env_atomically ".env" "$@"
  exit 0
fi

# Production never resolves mutable latest tags. The accepted manifest supplies
# all four image digests and the exact source/config/schema contract.
if [[ "${1:-}" == "--manifest" && -n "${2:-}" ]]; then
  exec python3 scripts/release_deploy.py deploy "$2"
elif [[ "${1:-}" == "--finalize" ]]; then
  exec python3 scripts/release_deploy.py finalize
elif [[ "${1:-}" == "--rollback" ]]; then
  shift
  exec python3 scripts/release_deploy.py rollback "$@"
fi
echo "Usage: deploy.sh --manifest accepted-manifest.json | --finalize | --rollback" >&2
exit 2
