"""add_eur_gbp_to_exchange_rates

Revision ID: a1b2c3d4e5f6
Revises: 79f7c3781ae4
Create Date: 2026-07-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '79f7c3781ae4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('exchange_rates', sa.Column('eur_try_rate', sa.Float(), nullable=True))
    op.add_column('exchange_rates', sa.Column('gbp_try_rate', sa.Float(), nullable=True))
    op.alter_column('exchange_rates', 'usd_try_rate', existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('exchange_rates', 'usd_try_rate', existing_type=sa.Float(), nullable=False)
    op.drop_column('exchange_rates', 'gbp_try_rate')
    op.drop_column('exchange_rates', 'eur_try_rate')
