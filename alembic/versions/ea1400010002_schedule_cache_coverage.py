"""Store inclusive source-fetch bounds with the canonical entity schedule cache."""

import sqlalchemy as sa

from alembic import op

revision = "ea1400010002"
down_revision = "ea1400010001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cached_schedules", sa.Column("covered_start", sa.Date()))
    op.add_column("cached_schedules", sa.Column("covered_end", sa.Date()))


def downgrade():
    op.drop_column("cached_schedules", "covered_end")
    op.drop_column("cached_schedules", "covered_start")
