# f4a5b6c7d8e9_unify_schedule_profiles

Adds the canonical schedule-profile fields to
`user_schedule_subscriptions`: stable profile ID, timezone, delivery mode,
lesson mode, and calendar visibility. Existing rows are assigned a stable
`telegram-<id>` profile ID and Moscow timezone defaults.

The migration is reversible and uses only PostgreSQL-safe column/index
operations. Keep `Europe/Moscow` as the default when adding future fields.
