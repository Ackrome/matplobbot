# `f3a4b5c6d7e8_add_subscription_indexes_and_mail_fk.py`

Adds the `(notification_time, is_active)` and `user_id` indexes used by schedule
notification queries and adds `cached_schedules.entity_name` so the offline
entity list does not expand each schedule JSON document. It also removes orphaned mailbox rows from legacy
installations and adds a cascading foreign key from `mail_accounts.user_id` to
`users.user_id`.

The migration is applied by Alembic after `f2c63d4e5f60`. It changes database
state only; application code should continue using `MailAccount` from
`shared_lib.models`. The orphan cleanup is intentionally limited to rows that
cannot belong to an existing user. Keep the constraint name stable for safe
downgrades and future migrations.
