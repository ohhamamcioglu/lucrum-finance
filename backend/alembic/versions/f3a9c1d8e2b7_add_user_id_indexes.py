"""add_user_id_indexes

Revision ID: f3a9c1d8e2b7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-18 00:00:00.000000

user_id yabancı anahtar sütunlarında hiç index yoktu — kullanıcı sayısı arttıkça
pozisyon/borç/bildirim gibi user_id'ye göre filtrelenen her sorgu tam tablo taramasına
(full table scan) düşüyordu. Bu, ikinci bir bağımsız denetimde (Gemini) bulundu.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f3a9c1d8e2b7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
    'positions', 'transactions', 'portfolio_snapshots', 'asset_class_summaries',
    'performance_history', 'liabilities', 'target_allocations', 'price_alerts',
    'notifications', 'auth_tokens', 'payments',
]


def upgrade() -> None:
    """Upgrade schema."""
    for table in TABLES:
        op.create_index(f'ix_{table}_user_id', table, ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    for table in TABLES:
        op.drop_index(f'ix_{table}_user_id', table_name=table)
