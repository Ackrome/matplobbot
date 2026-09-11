"""Persist explicit TLS mailbox ports."""

import sqlalchemy as sa
from alembic import op

revision = "f1b52c3d4e5f"
down_revision = "f0a41b2c3d4e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mail_accounts", sa.Column("port", sa.Integer(), nullable=True))
    op.execute("UPDATE mail_accounts SET port = CASE WHEN protocol = 'pop3' THEN 995 ELSE 993 END")
    op.alter_column("mail_accounts", "port", nullable=False)


def downgrade():
    op.drop_column("mail_accounts", "port")
