"""Persist public schedule changes without recipient identities."""

import sqlalchemy as sa

from alembic import op

revision = "ea1400010001"
down_revision = "ff5f60718293"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "schedule_history_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_key", sa.String(64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("before_lesson", sa.JSON()),
        sa.Column("after_lesson", sa.JSON()),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.UniqueConstraint("event_key", "position", name="uq_schedule_history_event_position"),
    )
    op.create_index(
        "ix_schedule_history_entity_time",
        "schedule_history_entries",
        ["entity_type", "entity_id", "observed_at"],
    )
    op.create_index("ix_schedule_history_time", "schedule_history_entries", ["observed_at"])


def downgrade():
    op.drop_table("schedule_history_entries")
