"""Add encrypted mailbox credentials and pending delivery state."""

import sqlalchemy as sa

from alembic import op

revision = "f0a41b2c3d4e"
down_revision = "a0b5a060b6fe"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mail_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("address", sa.String(320), nullable=False),
        sa.Column("host", sa.String(253), nullable=False),
        sa.Column("protocol", sa.String(8), nullable=False),
        sa.Column("credential", sa.LargeBinary(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("checkpoint", sa.LargeBinary(), nullable=False),
        sa.Column("pending", sa.LargeBinary(), nullable=True),
        sa.Column("status", sa.String(80), nullable=False),
        sa.UniqueConstraint("user_id", "address", "host", name="uq_mail_owner_address_host"),
    )
    op.create_index("ix_mail_accounts_user_id", "mail_accounts", ["user_id"])


def downgrade():
    op.drop_table("mail_accounts")
