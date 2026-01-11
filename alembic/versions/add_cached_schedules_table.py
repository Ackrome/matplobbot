"""add_cached_schedules_table

Revision ID: add_cached_schedules_table
Revises: hybrid_search_001
Create Date: 2026-01-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = 'add_cached_schedules_table'
down_revision = 'hybrid_search_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'cached_schedules',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('schedule_data', JSONB, nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.UniqueConstraint('entity_type', 'entity_id', name='uq_cached_schedule_entity')
    )


def downgrade() -> None:
    op.drop_table('cached_schedules')