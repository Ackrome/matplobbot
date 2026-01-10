"""add_hybrid_search

Revision ID: hybrid_search_001
Revises: 92ad2bbdb3e6
Create Date: 2026-01-09 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR


# revision identifiers, used by Alembic.
revision = 'hybrid_search_001'
down_revision = '92ad2bbdb3e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add language column
    op.add_column('search_documents', sa.Column('language', sa.String(), server_default='russian', nullable=False))

    # 2. Add TSVECTOR column for full-text search
    op.add_column('search_documents', sa.Column('content_ts', TSVECTOR, nullable=True))

    # 3. Create GIN index for fast keyword search
    op.create_index(
        'ix_search_documents_content_ts',
        'search_documents',
        ['content_ts'],
        postgresql_using='gin'
    )

    # 4. Data Migration: Populate the new column
    op.execute("""
        UPDATE search_documents
        SET content_ts = to_tsvector('russian', content)
    """)


def downgrade() -> None:
    op.drop_index('ix_search_documents_content_ts', table_name='search_documents')
    op.drop_column('search_documents', 'content_ts')
    op.drop_column('search_documents', 'language')