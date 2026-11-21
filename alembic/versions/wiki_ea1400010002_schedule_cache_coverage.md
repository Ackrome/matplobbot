# Proven schedule cache dates

Migration `ea1400010002` adds nullable inclusive `covered_start` and `covered_end`
dates to the canonical entity cache. `upgrade()` adds the two SQLAlchemy date
columns and `downgrade()` removes them. It depends on revision `ea1400010001`.

Run with the normal Alembic upgrade, for example `alembic upgrade head`. Existing
cache payloads are preserved. Existing rows have unknown coverage until the next
successful university fetch. A nonempty payload and an empty payload follow the
same rule, since the first and last returned lesson cannot establish the range
actually queried. Keep date updates atomic with the associated payload.
