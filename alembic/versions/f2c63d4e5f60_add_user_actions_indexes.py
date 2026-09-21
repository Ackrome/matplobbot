"""Add indexes to user_actions table.

Revision ID: f2c63d4e5f60
Revises: f1b52c3d4e5f
"""

from alembic import op

revision = "f2c63d4e5f60"
down_revision = "f1b52c3d4e5f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_user_actions_user_id", "user_actions", ["user_id"])
    op.create_index("ix_user_actions_action_type", "user_actions", ["action_type"])
    op.create_index("ix_user_actions_timestamp", "user_actions", ["timestamp"])
    op.create_index(
        "ix_user_actions_user_id_timestamp",
        "user_actions",
        ["user_id", "timestamp"],
    )


def downgrade():
    op.drop_index("ix_user_actions_user_id_timestamp", table_name="user_actions")
    op.drop_index("ix_user_actions_timestamp", table_name="user_actions")
    op.drop_index("ix_user_actions_action_type", table_name="user_actions")
    op.drop_index("ix_user_actions_user_id", table_name="user_actions")
