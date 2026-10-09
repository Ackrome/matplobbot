"""Link separately reviewed official sources to one curriculum without merging provenance."""

import sqlalchemy as sa

from alembic import op

revision = "fc2c3d4e5f60"
down_revision = "fb1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("curriculum_documents") as batch:
        batch.add_column(sa.Column("parent_document_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_curriculum_documents_parent_document_id",
            "curriculum_documents",
            ["parent_document_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_curriculum_documents_parent_document_id", ["parent_document_id"])


def downgrade():
    with op.batch_alter_table("curriculum_documents") as batch:
        batch.drop_index("ix_curriculum_documents_parent_document_id")
        batch.drop_constraint("fk_curriculum_documents_parent_document_id", type_="foreignkey")
        batch.drop_column("parent_document_id")
