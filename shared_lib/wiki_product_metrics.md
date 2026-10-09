# Product outcome metrics

`product_metrics.py` records allowlisted outcomes for global search, first recorded schedule subscriptions and Studio jobs. It does not store queries, document contents, names, IP addresses or arbitrary event payloads.

## Public functions and usage

`await record_product_event("search_succeeded", telegram_user_id=user_id)` records an event. Pass exactly one of `telegram_user_id` and `web_account_id`; linked web accounts resolve to the Telegram identity. `dedupe_key` supports idempotent recording of job results. Subscription activation is deduplicated per account within retained history.

`await get_product_snapshot(session, days=30)` returns aggregate outcomes, daily active identities and accounts active on at least two UTC dates. This measures instrumented workflows, not all website visits or a cohort retention rate. Studio completion counts a result retrieved by its owner, not every worker completion.

Aggregation joins historical web events to the account's current Telegram link.
A web-only first visit followed by a later Telegram visit remains one returning
identity after linking. Subscription activation counts distinct canonical actors
in the selected period, so pre-link and post-link activation records cannot
double-count that person. Unlinked web accounts remain distinct. This normalization
does not rewrite or duplicate event rows.

`await purge_expired_product_events()` deletes events older than 90 days. The scheduler invokes it daily. Account deletion cascades through the model's foreign keys.

## Dependencies and side effects

Uses SQLAlchemy, PostgreSQL, `ProductEvent`, `WebAccount` and the shared async session factory. Requires migration `f7d8e9f0a1b2`. Recording has a two-second timeout and is best effort, so telemetry failures do not prevent user work; aggregation and maintenance surface errors to their callers. Each record is a short independent transaction.

## Maintenance

Add event names to the allowlist and document their meaning before instrumenting new workflows. Do not interpret pre-instrumentation periods as zero adoption. Test actor normalization, SQL aggregation, deduplication and deletion when changing the model. Never add arbitrary client-provided analytics payloads.
