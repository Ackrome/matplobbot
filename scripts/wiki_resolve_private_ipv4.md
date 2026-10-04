# `resolve_private_ipv4.sh`

## Purpose

Resolves a deployment hostname to one unambiguous RFC1918 IPv4 address. CI uses the result for
traffic between the GitHub runner, Jenkins, and the application VM on their shared Proxmox LAN,
so Tailscale SSH authorization cannot enter the unattended deployment path.

## Public interface

Run `bash scripts/resolve_private_ipv4.sh <hostname-or-ip>`. On success, stdout contains only the
validated private IPv4 address. Invalid, public, loopback, carrier-grade NAT, `*.ts.net`, unresolved,
or multiply-resolved inputs fail with a diagnostic on stderr.

Examples:

```bash
bash scripts/resolve_private_ipv4.sh app-vm.local
bash scripts/resolve_private_ipv4.sh 192.168.1.25
```

## Dependencies and side effects

- Requires Bash 4 or newer.
- Hostname resolution requires the standard Linux `getent`, `awk`, and `sort` utilities.
- Performs read-only name-service lookups and does not modify networking or DNS.

## Maintenance notes

Keep the accepted ranges limited to RFC1918 (`10/8`, `172.16/12`, and `192.168/16`). In
particular, do not add Tailscale's `100.64/10` range: doing so would restore the interactive SSH
authorization dependency this helper is intended to remove.
