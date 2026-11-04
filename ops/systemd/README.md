# Host disk guard installation

Install the guard on a Docker host as root after checking the target checkout and Docker data root.

```bash
install -D -m 0755 scripts/docker_disk_guard.py /usr/local/libexec/matplobbot-docker-disk-guard.py
install -D -m 0644 ops/systemd/matplobbot-docker-disk-guard.service /etc/systemd/system/matplobbot-docker-disk-guard.service
install -D -m 0644 ops/systemd/matplobbot-docker-disk-guard.timer /etc/systemd/system/matplobbot-docker-disk-guard.timer
systemctl daemon-reload
systemctl enable --now matplobbot-docker-disk-guard.timer
systemctl start matplobbot-docker-disk-guard.service
systemctl status matplobbot-docker-disk-guard.timer --no-pager
journalctl -u matplobbot-docker-disk-guard.service -n 20 --no-pager
```

The unit is intended for the production Docker host. The self-hosted GitHub runner uses the `runner` profile from the workflow before and after image builds. Keep the production unit on the application host and do not use the runner profile there.

Install `matplobbot-docker-disk-guard-runner.service` and its timer on the self-hosted runner with the same commands, replacing the two production unit filenames. The runner unit uses the more aggressive `runner` profile, removes inactive Buildx builders and image/cache data older than 72 hours, and keeps the warning threshold at 20 GiB with 8 GiB critical headroom.

The service writes JSON status to the systemd journal. A critical result exits nonzero, which makes the failed service visible to the host's normal monitoring. Do not add `docker volume prune` or direct `ctr` deletion to the unit.

If the deployment account has Docker access but no passwordless `sudo`, use a user cron entry as the persistent fallback. Keep the existing crontab entries and add one line for the matching profile:

```cron
*/15 * * * * /usr/bin/python3 /home/deploy/bin/matplobbot-docker-disk-guard.py monitor --profile production --warn-gib 30 --critical-gib 15 --warn-percent 20 --critical-percent 10 --lock-file /tmp/matplobbot-docker-disk-guard.lock 2>&1 | /usr/bin/logger -t matplobbot-disk-guard
```

Use `/home/github-runner-vm/bin/matplobbot-docker-disk-guard.py`, `--profile runner`, and `--image-age 72h` on the self-hosted runner. The cron command requires the account to be in the Docker group.
