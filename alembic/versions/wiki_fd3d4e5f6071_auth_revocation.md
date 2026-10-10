# Session revocation migration

Adds `WebAccount.auth_version` and `web_token_revocations` for durable individual
logout and logout on all devices. `upgrade()` runs through `alembic upgrade head`;
`downgrade()` removes the revocation state and version column. Requires SQLAlchemy,
Alembic and the preceding curriculum supplements migration. Revocations cascade
with account deletion and have an expiry index for cleanup. Existing JWTs lack
the required session claims and require one new login after this release.
Do not roll back authentication code alone after issuing new sessions: restore a
compatible release and rotate the JWT signing secret if revocation data was lost.
