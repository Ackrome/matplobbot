"""Store the result of the last failed Session date refresh."""

import sqlalchemy as sa

from alembic import op

revision = "ea1400010005"
down_revision = "ea1400010004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("curriculum_session_snapshots", sa.Column("last_error", sa.String(32)))


def downgrade():
    op.drop_column("curriculum_session_snapshots", "last_error")
