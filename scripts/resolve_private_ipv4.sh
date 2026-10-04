#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ] || [ -z "${1:-}" ]; then
  echo "Usage: $0 <LAN hostname or private IPv4>" >&2
  exit 2
fi

requested_host="${1%.}"
lower_host="${requested_host,,}"

case "$lower_host" in
  *.ts.net)
    echo "ERROR: Tailscale MagicDNS hosts are not allowed for unattended deployment: $requested_host" >&2
    exit 1
    ;;
esac

is_ipv4() {
  local value="$1"
  local first second third fourth extra octet

  IFS=. read -r first second third fourth extra <<<"$value"
  [ -z "${extra:-}" ] || return 1

  for octet in "$first" "$second" "$third" "$fourth"; do
    [[ "$octet" =~ ^[0-9]{1,3}$ ]] || return 1
    ((10#$octet <= 255)) || return 1
  done
}

is_private_ipv4() {
  local value="$1"

  is_ipv4 "$value" || return 1
  case "$value" in
    10.*|192.168.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*) return 0 ;;
    *) return 1 ;;
  esac
}

if is_ipv4 "$requested_host"; then
  if ! is_private_ipv4 "$requested_host"; then
    echo "ERROR: deployment endpoint must be an RFC1918 LAN address: $requested_host" >&2
    exit 1
  fi
  printf '%s\n' "$requested_host"
  exit 0
fi

if ! command -v getent >/dev/null 2>&1; then
  echo "ERROR: getent is required to resolve LAN hostname $requested_host" >&2
  exit 1
fi

mapfile -t resolved_ips < <(
  getent ahostsv4 "$requested_host" 2>/dev/null \
    | awk '{print $1}' \
    | sort -u
)

private_ips=()
for resolved_ip in "${resolved_ips[@]}"; do
  if is_private_ipv4 "$resolved_ip"; then
    private_ips+=("$resolved_ip")
  fi
done

if [ "${#private_ips[@]}" -eq 0 ]; then
  echo "ERROR: $requested_host did not resolve to an RFC1918 LAN address" >&2
  exit 1
fi

if [ "${#private_ips[@]}" -ne 1 ]; then
  echo "ERROR: $requested_host resolved to multiple LAN addresses; configure one explicit private IPv4" >&2
  exit 1
fi

printf '%s\n' "${private_ips[0]}"
