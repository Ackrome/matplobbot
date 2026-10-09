"""Add optional bounded duration for content-free UX outcomes."""

import sqlalchemy as sa
from alembic import op

revision = "f8e9f0a1b2c3"
down_revision = "f7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("product_events", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_product_event_duration",
        "product_events",
        "duration_ms IS NULL OR (duration_ms >= 0 AND duration_ms <= 3600000)",
    )


def downgrade():
    op.drop_constraint("ck_product_event_duration", "product_events", type_="check")
    op.drop_column("product_events", "duration_ms")
