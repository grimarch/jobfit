"""add_starred_at_to_classifications

Revision ID: c8a3f91e7b52
Revises: a3f82c19e4b7
Create Date: 2026-07-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8a3f91e7b52'
down_revision: Union[str, Sequence[str], None] = 'a3f82c19e4b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('classifications', sa.Column('starred_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('classifications', 'starred_at')
