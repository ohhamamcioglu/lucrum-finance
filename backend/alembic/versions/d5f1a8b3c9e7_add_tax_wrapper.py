"""add_tax_wrapper

Revision ID: d5f1a8b3c9e7
Revises: c2d8e5f7a4b6
Create Date: 2026-07-19 00:00:00.000000

Almanya & UK vergi modülleri (Faz 3, task #58) — positions tablosuna tax_wrapper
kolonu (GIA/ISA/SIPP). Sadece UK vergi hesaplayıcısı (ISA yıllık limit takibi,
Bed-and-ISA analizi) için anlamlı; diğer ülke kullanıcıları için NULL kalır.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd5f1a8b3c9e7'
down_revision: Union[str, Sequence[str], None] = 'c2d8e5f7a4b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('positions', sa.Column('tax_wrapper', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('positions', 'tax_wrapper')
