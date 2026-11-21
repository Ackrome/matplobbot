"""Keep the last successful RUZ verification independently for each reviewed term."""

import sqlalchemy as sa

from alembic import op

revision = "ea1400010003"
down_revision = "ea1400010002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "curriculum_session_snapshots",
        sa.Column("group_id", sa.String(length=128), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lessons", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["curriculum_groups.group_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("group_id", "semester", "start_date", "end_date"),
    )


def downgrade():
    op.drop_table("curriculum_session_snapshots")
