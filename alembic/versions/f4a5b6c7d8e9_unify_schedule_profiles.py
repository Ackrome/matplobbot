"""Store Web and Telegram schedule profiles in one canonical table."""

import sqlalchemy as sa

from alembic import op

revision = "f4a5b6c7d8e9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_schedule_subscriptions",
        sa.Column("profile_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "user_schedule_subscriptions",
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="Europe/Moscow",
        ),
    )
    op.add_column(
        "user_schedule_subscriptions",
        sa.Column(
            "delivery_mode",
            sa.String(length=16),
            nullable=False,
            server_default="telegram",
        ),
    )
    op.add_column(
        "user_schedule_subscriptions",
        sa.Column(
            "lesson_mode",
            sa.String(length=16),
            nullable=False,
            server_default="all",
        ),
    )
    op.add_column(
        "user_schedule_subscriptions",
        sa.Column("calendar_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute(
        "UPDATE user_schedule_subscriptions "
        "SET profile_id = 'telegram-' || id::text "
        "WHERE profile_id IS NULL"
    )
    op.create_index(
        "ix_user_schedule_subscriptions_profile_id",
        "user_schedule_subscriptions",
        ["profile_id"],
    )


def downgrade():
    op.drop_index(
        "ix_user_schedule_subscriptions_profile_id",
        table_name="user_schedule_subscriptions",
    )
    op.drop_column("user_schedule_subscriptions", "calendar_enabled")
    op.drop_column("user_schedule_subscriptions", "lesson_mode")
    op.drop_column("user_schedule_subscriptions", "delivery_mode")
    op.drop_column("user_schedule_subscriptions", "timezone")
    op.drop_column("user_schedule_subscriptions", "profile_id")
