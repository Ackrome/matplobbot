"""Persist manual date matches for ambiguous, reviewed assessments."""

import sqlalchemy as sa

from alembic import op

revision = "ea1400010006"
down_revision = "ea1400010005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "curriculum_session_snapshots",
        sa.Column("date_resolutions", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade():
    op.drop_column("curriculum_session_snapshots", "date_resolutions")
