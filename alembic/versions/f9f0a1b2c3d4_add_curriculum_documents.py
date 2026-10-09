"""Store official curriculum candidates, reviewed snapshots and group bindings."""

import sqlalchemy as sa

from alembic import op

revision = "f9f0a1b2c3d4"
down_revision = "f8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "curriculum_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("program", sa.String(500), nullable=False),
        sa.Column("profile", sa.String(500), nullable=False),
        sa.Column("campus", sa.String(255), nullable=False),
        sa.Column("admission_year", sa.Integer(), nullable=False),
        sa.Column("study_form", sa.String(100), nullable=False),
        sa.Column("source_pdf", sa.LargeBinary(), nullable=True),
        sa.Column("source_page_count", sa.Integer(), nullable=True),
        sa.Column("pending_hash", sa.String(64), nullable=True),
        sa.Column("pending_assessments", sa.JSON(), nullable=False),
        sa.Column("pending_warnings", sa.JSON(), nullable=False),
        sa.Column("pending_status", sa.String(30), nullable=True),
        sa.Column("published_hash", sa.String(64), nullable=True),
        sa.Column("published_pdf", sa.LargeBinary(), nullable=True),
        sa.Column("published_assessments", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(80), nullable=True),
        sa.Column("refresh_token", sa.String(36), nullable=True),
        sa.Column("refresh_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_curriculum_documents_next_check_at", "curriculum_documents", ["next_check_at"]
    )
    op.create_table(
        "curriculum_groups",
        sa.Column("group_id", sa.String(128), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("curriculum_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("group_name", sa.String(255), nullable=False),
        sa.Column("terms", sa.JSON(), nullable=False),
    )
    op.create_index("ix_curriculum_groups_document_id", "curriculum_groups", ["document_id"])


def downgrade():
    op.drop_table("curriculum_groups")
    op.drop_table("curriculum_documents")
