# Teacher rating cache migration

`ff5f60718293_teacher_rating_cache.py` extends `fe4e5f607182` with the independent
`teacher_rating_cache` table. `upgrade()` creates the canonical university/name
identity, nullable public aggregate/provenance fields, freshness/failure times,
and token/started-at refresh lease. A unique university/name constraint prevents
duplicate identities; a status check excludes unsupported persisted states.
The primary key is the service's 64-character identity digest.

Use through normal reviewed Alembic deployment: `alembic upgrade head`.
`downgrade()` removes only this rebuildable cache table and its contents; it does
not rewrite users, subscriptions, notifications or credentials. Production
rollback still follows the release runbook's schema compatibility checks.

Dependencies: Alembic and SQLAlchemy. No external network, source lookup, account
data scan, or Telegram delivery occurs in either migration direction. The model
and migration must stay aligned. Tests execute upgrade/downgrade and uniqueness/
status constraints on a real SQLite database; an isolated PostgreSQL 15 check also
verified both migration directions and concurrent cache/lease behavior.
