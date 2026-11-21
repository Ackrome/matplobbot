"""Persist private Studio project versions and their files."""

import sqlalchemy as sa

from alembic import op

revision = "ea1400010004"
down_revision = "ea1400010003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("project_name", sa.String(), nullable=False),
        sa.Column("project_type", sa.String(), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("project_id", "name", name="uq_project_version_name"),
    )
    op.create_table(
        "project_version_files",
        sa.Column(
            "version_id",
            sa.Integer(),
            sa.ForeignKey("project_versions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("file_path", sa.String(), primary_key=True),
        sa.Column("content_text", sa.String()),
        sa.Column("content_binary", sa.LargeBinary()),
        sa.Column("is_main", sa.Boolean()),
    )


def downgrade():
    op.drop_table("project_version_files")
    op.drop_table("project_versions")
