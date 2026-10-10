"""Durable session revocation and account-wide token generation."""

import sqlalchemy as sa

from alembic import op

revision = "fd3d4e5f6071"
down_revision = "fc2c3d4e5f60"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "web_accounts", sa.Column("auth_version", sa.Integer(), server_default="0", nullable=False)
    )
    op.create_table(
        "web_token_revocations",
        sa.Column("jti", sa.String(64), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("web_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_web_token_revocations_account_id", "web_token_revocations", ["account_id"])
    op.create_index("ix_web_token_revocations_expires_at", "web_token_revocations", ["expires_at"])


def downgrade():
    op.drop_table("web_token_revocations")
    op.drop_column("web_accounts", "auth_version")
