"""add_ars_try_rate

Revision ID: c2d8e5f7a4b6
Revises: b7e4a2c9f1d3
Create Date: 2026-07-19 00:00:00.000000

Arjantin Blue Dollar entegrasyonu (Faz 2) — exchange_rates tablosuna
ars_try_rate kolonu (Bluelytics'in blue.value_avg değerinden türetilir:
ars_try_rate = usd_try_rate / ars_per_usd_blue). Mevcut usd/eur/gbp_try_rate
kolonlarıyla aynı desende, tek para birimi = tek kolon.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c2d8e5f7a4b6'
down_revision: Union[str, Sequence[str], None] = 'b7e4a2c9f1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('exchange_rates', sa.Column('ars_try_rate', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('exchange_rates', 'ars_try_rate')
