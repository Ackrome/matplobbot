"""Add bounded, content-free product outcome events.

Revision ID: f7d8e9f0a1b2
Revises: f6c7d8e9f0a1
"""

import sqlalchemy as sa

from alembic import op

revision = "f7d8e9f0a1b2"
down_revision = "f6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_name", sa.String(48), nullable=False),
        sa.Column(
            "web_account_id", sa.Integer(), sa.ForeignKey("web_accounts.id", ondelete="CASCADE")
        ),
        sa.Column(
            "telegram_user_id", sa.BigInteger(), sa.ForeignKey("users.user_id", ondelete="CASCADE")
        ),
        sa.Column("dedupe_key", sa.String(160), unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "(web_account_id IS NULL) <> (telegram_user_id IS NULL)",
            name="ck_product_event_one_actor",
        ),
    )
    op.create_index(
        "ix_product_events_created_event", "product_events", ["created_at", "event_name"]
    )
    op.create_index("ix_product_events_web_account", "product_events", ["web_account_id"])
    op.create_index("ix_product_events_telegram_user", "product_events", ["telegram_user_id"])


def downgrade():
    op.drop_table("product_events")
