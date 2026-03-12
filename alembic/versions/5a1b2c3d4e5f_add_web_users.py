# alembic/versions/5a1b2c3d4e5f_add_web_users.py
"""add web_users

Revision ID: 5a1b2c3d4e5f
Revises: 2fbd4aaae764
Create Date: 2026-03-12 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5a1b2c3d4e5f'
down_revision: Union[str, Sequence[str], None] = '2fbd4aaae764'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table('web_users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('username', sa.String(), nullable=False),
    sa.Column('password_hash', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_web_users_username'), 'web_users', ['username'], unique=True)

def downgrade() -> None:
    op.drop_index(op.f('ix_web_users_username'), table_name='web_users')
    op.drop_table('web_users')