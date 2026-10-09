"""Persist explicit scan table profiles independently of PDF publication."""

import sqlalchemy as sa

from alembic import op

revision = "fb1b2c3d4e5f"
down_revision = "fa0a1b2c3d4e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("curriculum_documents", sa.Column("scan_layout", sa.String(50), nullable=True))


def downgrade():
    op.drop_column("curriculum_documents", "scan_layout")
