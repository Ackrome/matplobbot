# Rehearse a database-schema rollback boundary

`compatibility()` compares the schema heads in the candidate and the latest
successfully deployed manifest. For different heads, `test_transition()`
provisions an isolated Docker network, PostgreSQL and Redis and runs the exact
previous images. It validates the previous source's worker policy, seeds user
sessions, a Studio project and a pending schedule delivery, then stops the
previous services. The candidate migrator upgrades the same database. The
candidate API creates a Studio project and a calendar profile through their
ordinary authenticated HTTP endpoints. The previous services restart on that
schema, preserve revoked sessions, edit and render the candidate's Studio project,
update and replay creation of the candidate's profile, and confirm one canonical
subscription row. The pending event goes through a local fake Telegram endpoint
with retry and deduplication. Every report binds both SHAs,
both schema heads and image digests. Docker cleanup removes only the generated
Compose project and its volumes.

```sh
python3 scripts/rc_rollback_compat.py --manifest release-manifest-accepted.json \
  --previous previous-accepted-release.json --output rc-rollback-compat.json
```

The runner needs Git ancestry, Docker Compose, PyYAML, access to the GHCR digests
and the previous worker's installed AppArmor policy if required by the daemon.
The result is advisory evidence and carries no authorization to override
production rollback rules. When maintaining probes, target the API contracts
available in the previous accepted release and retain closed stdin, no external
delivery and immutable source checks.
