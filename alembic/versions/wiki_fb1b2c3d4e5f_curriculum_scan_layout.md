# Explicit curriculum scan layouts

`fb1b2c3d4e5f_curriculum_scan_layout.py` adds nullable `scan_layout VARCHAR(50)`
to `curriculum_documents`, following `fa0a1b2c3d4e`. `upgrade()` adds the column;
`downgrade()` removes it without changing PDF bytes, assessments or group bindings.
Run through `alembic upgrade head`; downgrade to `fa0a1b2c3d4e` to remove only this
setting. Requires Alembic/SQLAlchemy and the preceding curriculum migrations.
Null keeps automatic recognition for known document hashes; the service validates
supported explicit layout names. Keep the ORM field and service/API enum aligned
when adding another reviewed table profile.
