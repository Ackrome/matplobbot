# ea1400010004_studio_project_versions.py

Adds `project_versions` and `project_version_files` after `ea1400010003`.
`upgrade()` creates owner-inherited version history linked to `projects` and
stores version content using native SQL text/binary fields. The composite file
key distinguishes paths inside each version. Foreign key cascades free the
version storage when the project or version is deleted.

Deploy through `alembic upgrade head`. No backfill is required for previous
projects. They initially have no saved versions. `downgrade()` removes version
tables and their data. Existing live projects and restored copies remain usable.
Keep this schema consistent with `ProjectVersion` and `ProjectVersionFile`.
