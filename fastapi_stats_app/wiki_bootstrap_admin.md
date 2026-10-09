# Deployment admin provisioning

`bootstrap_admin.py` reconciles the dedicated password administrator used by Jenkins
authentication smoke checks with the effective `STATS_USER` / `STATS_PASS` settings
inside the deployed API container. `/api/auth/login` continues to authenticate against
`web_accounts`; setting environment variables alone does not create that row.

## Public entry points

- `provision_admin(db, username, password)` creates an unlinked `admin` account or
  synchronizes an existing unlinked administrator's password. It returns `created`,
  `unchanged`, or `password synchronized`; the caller owns the transaction.
- `bootstrap_admin()` reads explicit environment values, initializes the shared
  database pool, commits provisioning in one transaction and always closes the pool.
- `main()` provides the command-line exit status and credential-free diagnostics.
- `AdminProvisioningError` reports invalid configuration or an unsafe account collision.

## Usage

After migrations and API container startup, `deploy.sh` runs:

```bash
docker compose -f docker-compose.prod.yml exec -T mpb-fastapi-stats \
  python -m fastapi_stats_app.bootstrap_admin
```

Configure a dedicated username and a strong password through the existing Jenkins
`PROD_STATS_USER` / `PROD_STATS_PASS` credentials. Password rotation becomes effective
on the next deployment. A direct invocation of this command also changes the database;
it is not a read-only diagnostic. No credentials are accepted as command-line arguments.

## Dependencies, side effects, and maintenance

Uses SQLAlchemy sessions from `shared_lib.database`, the existing `WebAccount` model,
and the same password hashing functions as the login endpoint. The API image already
copies this package, so rebuilding that image includes the command.

Only a missing username or an existing administrator without a Telegram link can be
managed. An existing ordinary or Telegram-linked account is rejected unchanged; choose
a different deployment username rather than promoting or unlinking that account.
Changing `STATS_USER` creates a separate account and does not delete the previous one;
retire old administrators explicitly when needed. Existing IDs and preferences survive
password changes. Previously issued JWTs follow the normal token expiration policy.

Matching hashes are retained. Missing hashes on eligible admins can be initialized;
unrecognized stored hash formats require explicit repair. Default/blank credentials
are rejected. Existing rows are locked during synchronization. The username unique
constraint prevents simultaneous bootstraps from creating duplicate accounts; the
losing transaction fails closed and can be retried.

The CLI suppresses raw database exception text because SQL parameters can contain
password hashes or connection secrets. Keep smoke login strict: after provisioning,
Jenkins must still obtain a token from `/api/auth/login`, check protected HTTP access,
check the WebSocket upgrade, and reject anonymous access. Tests live in
`tests/test_auth_flow.py` and `tests/test_compose_configuration.py`.
