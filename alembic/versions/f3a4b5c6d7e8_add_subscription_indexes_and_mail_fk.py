"""Index schedule notifications, label cached entities, and enforce mail ownership."""

import sqlalchemy as sa

from alembic import op

revision = "f3a4b5c6d7e8"
down_revision = "f2c63d4e5f60"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cached_schedules", sa.Column("entity_name", sa.String(length=255), nullable=True))
    op.create_index(
        "ix_user_schedule_subscriptions_user_id",
        "user_schedule_subscriptions",
        ["user_id"],
    )
    op.create_index(
        "ix_user_subscriptions_notification_time_active",
        "user_schedule_subscriptions",
        ["notification_time", "is_active"],
    )

    # Older installations could contain orphaned rows because the original
    # table had no FK. Remove only those impossible-to-own rows before adding
    # the database-level cascade for future user deletions.
    op.execute(
        "DELETE FROM mail_accounts AS mail "
        "WHERE NOT EXISTS (SELECT 1 FROM users WHERE users.user_id = mail.user_id)"
    )
    op.create_foreign_key(
        "fk_mail_accounts_user_id_users",
        "mail_accounts",
        "users",
        ["user_id"],
        ["user_id"],
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint("fk_mail_accounts_user_id_users", "mail_accounts", type_="foreignkey")
    op.drop_index(
        "ix_user_subscriptions_notification_time_active",
        table_name="user_schedule_subscriptions",
    )
    op.drop_index(
        "ix_user_schedule_subscriptions_user_id",
        table_name="user_schedule_subscriptions",
    )
    op.drop_column("cached_schedules", "entity_name")
