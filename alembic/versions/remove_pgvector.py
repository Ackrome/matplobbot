"""remove_pgvector

Revision ID: remove_pgvector
Revises: add_cached_schedules_table
Create Date: 2026-01-14 ...

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'remove_pgvector'
down_revision: Union[str, Sequence[str], None] = 'add_cached_schedules_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Удаляем индекс HNSW (если он был создан)
    # Имя индекса может отличаться, alembic обычно генерирует их сам, 
    # но так как мы создавали его через op.execute, удалим так же.
    op.execute("DROP INDEX IF EXISTS search_documents_embedding_idx")
    
    # 2. Удаляем колонку с векторами
    op.drop_column('search_documents', 'embedding')

    # 3. Удаляем расширение vector
    op.execute("DROP EXTENSION IF EXISTS vector")


def downgrade() -> None:
    # Возврат обратно (если вдруг понадобится)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column('search_documents', sa.Column('embedding', sa.NullType(), nullable=True)) 
    # Примечание: sa.NullType() потому что Vector требует импорта pgvector, которого может не быть