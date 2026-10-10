# Offline schedule delivery benchmark

`benchmark()` builds disposable SQLite tables and synthetic users/subscriptions,
then executes the actual daily grouping, event dedupe, outbox insert/claim/finalize
and repeat-tick code. RUZ, formatting and Telegram are controlled doubles. It does
not initialize the configured production database or perform network requests.

`main()` exposes bounded CLI scenarios and optional UTF-8 JSON output. Example:

```powershell
$env:PYTHONUTF8='1'
.venv/Scripts/python.exe scripts/benchmark_schedule_delivery.py --users 1000 --entities 20 --source-delay-ms 100 --send-delay-ms 1 --fail-every 2 --output "$env:TEMP/delivery-load.json"
```

Dependencies: project SQLAlchemy, scheduler helpers and standard-library mocks.
Side effects: an in-memory database, simulated waits and the explicitly named
output file. Runs are capped at ten minutes, 10,000 users and 500 source entities.
The JSON records profile deduplication, source requests, cached fallback, queue
drain time and repeat-tick idempotency. These are local algorithm/SQL measurements;
the caller continuously drains batches, so measured elapsed time excludes the
production scheduler's minute cadence and is not end-to-end delivery latency.
They do not establish PostgreSQL locks, Telegram rate limits, real RUZ latency or
host memory/CPU capacity. Before declaring a supported production scale, replay a
representative workload against disposable PostgreSQL and the deployment hardware
with provider calls still isolated. Preserve the explicit scope label in reports.
