"""add_known_brands_and_unmatched_industries

Revision ID: a3f82c19e4b7
Revises: 1b90459b016f
Create Date: 2026-07-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f82c19e4b7'
down_revision: Union[str, Sequence[str], None] = '1b90459b016f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'known_brands',
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('firma', sa.String(), nullable=False),
        sa.Column('is_known', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('role', 'firma'),
    )
    op.create_table(
        'unmatched_industries',
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('industry', sa.String(), nullable=False),
        sa.Column('first_seen', sa.String(), nullable=False),
        sa.Column('notes', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('role', 'industry'),
    )


def downgrade() -> None:
    op.drop_table('unmatched_industries')
    op.drop_table('known_brands')
