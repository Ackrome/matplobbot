"""Persist bounded background curriculum parsing work and versioned cache keys."""

import sqlalchemy as sa

from alembic import op

revision = "fa0a1b2c3d4e"
down_revision = "f9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("source_hash", sa.String(64)),
        sa.Column("parsed_hash", sa.String(64)),
        sa.Column("parser_version", sa.String(100)),
        sa.Column("parse_method", sa.String(20)),
        sa.Column("engine_version", sa.String(200)),
        sa.Column("processing_state", sa.String(20), nullable=False, server_default="ready"),
        sa.Column("processing_token", sa.String(36)),
        sa.Column("processing_started_at", sa.DateTime(timezone=True)),
        sa.Column("processing_error", sa.String(80)),
    ):
        op.add_column("curriculum_documents", column)
    op.create_index(
        "ix_curriculum_documents_processing_state", "curriculum_documents", ["processing_state"]
    )
    op.execute(
        "UPDATE curriculum_documents SET source_hash = COALESCE(pending_hash, published_hash), "
        "processing_state = CASE WHEN source_pdf IS NOT NULL THEN 'queued' ELSE 'ready' END"
    )


def downgrade():
    op.drop_index("ix_curriculum_documents_processing_state", table_name="curriculum_documents")
    for name in (
        "processing_error",
        "processing_started_at",
        "processing_token",
        "processing_state",
        "engine_version",
        "parse_method",
        "parser_version",
        "parsed_hash",
        "source_hash",
    ):
        op.drop_column("curriculum_documents", name)
