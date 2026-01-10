"""add_vector_search

Revision ID: 92ad2bbdb3e6
Revises: 3145f2fc0295
Create Date: 2025-12-24 13:50:44.945774

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = '92ad2bbdb3e6'
down_revision: Union[str, Sequence[str], None] = '3145f2fc0295'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Включаем расширение (нужны права superuser, обычно в docker они есть)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Таблица документов
    op.create_table(
        'search_documents',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('source_type', sa.String(), nullable=False), # 'lib' (код) или 'doc' (лекции)
        sa.Column('source_path', sa.String(), nullable=False), # Путь (ключ)
        sa.Column('content', sa.Text(), nullable=False),       # Что ищем
        sa.Column('metadata', sa.JSON(), nullable=True),       # Доп данные
        # 384 - это размерность модели all-MiniLM-L6-v2. Если сменишь модель, меняй и тут.
        sa.Column('embedding', Vector(384), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        # Уникальность пути, чтобы не дублировать при перезапуске
        sa.UniqueConstraint('source_type', 'source_path', name='uq_search_doc_path')
    )

    # 3. Индекс HNSW для быстрого поиска (cosine distance)
    # op.execute работает надежнее для специфичных индексов pgvector через alembic
    op.execute("""
        CREATE INDEX ON search_documents USING hnsw (embedding vector_cosine_ops)
    """)


def downgrade() -> None:
    op.drop_table('search_documents')
    op.execute("DROP EXTENSION vector")
