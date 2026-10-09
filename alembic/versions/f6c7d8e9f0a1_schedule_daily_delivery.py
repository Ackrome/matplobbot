"""Reuse the schedule outbox for bounded daily schedule delivery."""

import sqlalchemy as sa

from alembic import op

revision = "f6c7d8e9f0a1"
down_revision = "f5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "schedule_change_deliveries",
        sa.Column("delivery_kind", sa.String(16), nullable=False, server_default="change"),
    )
    op.add_column(
        "schedule_change_deliveries",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("schedule_change_deliveries", "expires_at")
    op.drop_column("schedule_change_deliveries", "delivery_kind")
