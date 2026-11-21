# Session date review storage

Migration `ea1400010006` adds the `date_resolutions` JSON column to cached
group-term snapshots. Existing snapshots get an empty decision set. A decision
maps a stable RUZ event fingerprint to the reviewed candidate set fingerprint
and one selected source row fingerprint.

Use Alembic upgrade through the normal migrator. Downgrade drops only the
decisions. The source timetable cache and curriculum documents are independent.
Do not edit fingerprints manually. Use the authenticated administrative review
workflow, which validates current published rows and the stored source event.
