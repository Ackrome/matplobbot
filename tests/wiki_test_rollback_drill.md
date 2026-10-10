# Rollback drill safety tests

The fixture's PostgreSQL readiness check must address TCP loopback so initial
migration cannot race the image's temporary Unix-only setup server.

`RollbackDrillSafetyTests` checks that generated fixture services use only the
internal network, publish no host ports, mount only the named disposable DB volume
or read-only frontend fixture, and cannot start real provider-capable workers.
It also verifies synthetic connection settings do not inherit operator secrets.

Run `.venv/Scripts/python.exe -m unittest tests.test_rollback_drill`. Dependencies
are standard-library unittest and the rollback harness; there are no Docker,
database or network side effects. Actual rollback/finalize evidence comes from
running `scripts/rollback_drill.py`, not these structural safety checks.
