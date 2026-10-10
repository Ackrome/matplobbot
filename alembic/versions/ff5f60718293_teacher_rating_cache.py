"""Persist exact-university/full-name MyPrepod associations and public aggregates."""

import sqlalchemy as sa

from alembic import op

revision = "ff5f60718293"
down_revision = "fe4e5f607182"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "teacher_rating_cache",
        sa.Column("identity_key", sa.String(64), primary_key=True),
        sa.Column("university_key", sa.String(32), nullable=False),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="unavailable"),
        sa.Column("profile", sa.JSON(), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(48), nullable=True),
        sa.Column("refresh_token", sa.String(36), nullable=True),
        sa.Column("refresh_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "university_key", "canonical_name", name="uq_teacher_rating_identity"
        ),
        sa.CheckConstraint(
            "status IN ('matched', 'not_found', 'ambiguous', 'unavailable')",
            name="ck_teacher_rating_status",
        ),
    )


def downgrade():
    op.drop_table("teacher_rating_cache")
