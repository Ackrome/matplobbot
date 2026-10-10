"""Independent notification baselines and recent terminal delivery outcomes."""

import hashlib
import json
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "fe4e5f607182"
down_revision = "fd3d4e5f6071"
branch_labels = None
depends_on = None


def upgrade():
    snapshots = op.create_table(
        "schedule_notification_snapshots",
        sa.Column("entity_type", sa.String(32), primary_key=True),
        sa.Column("entity_id", sa.String(), primary_key=True),
        sa.Column("schedule_data", sa.JSON(), nullable=False),
        sa.Column("schedule_hash", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.add_column("schedule_change_deliveries", sa.Column("failed_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_schedule_change_deliveries_failed_at", "schedule_change_deliveries", ["failed_at"]
    )
    # Seed existing observations before interactive writers resume. Historical
    # changes whose old payload was already overwritten cannot be reconstructed.
    cache = sa.table(
        "cached_schedules",
        sa.column("entity_type", sa.String()),
        sa.column("entity_id", sa.String()),
        sa.column("schedule_data", sa.JSON()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    migrated_at = datetime.now(UTC)
    result = bind.execute(sa.select(cache))
    while rows := result.mappings().fetchmany(500):
        values = []
        for row in rows:
            payload = row["schedule_data"]
            if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
                continue
            payload = [{k: v for k, v in item.items() if k != "date_obj"} for item in payload]
            values.append(
                {
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "schedule_data": payload,
                    "schedule_hash": hashlib.sha256(
                        json.dumps(payload, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                    "revision": 1,
                    "updated_at": row["updated_at"] or migrated_at,
                }
            )
        if values:
            bind.execute(snapshots.insert(), values)


def downgrade():
    op.drop_index(
        "ix_schedule_change_deliveries_failed_at", table_name="schedule_change_deliveries"
    )
    op.drop_column("schedule_change_deliveries", "failed_at")
    op.drop_table("schedule_notification_snapshots")
