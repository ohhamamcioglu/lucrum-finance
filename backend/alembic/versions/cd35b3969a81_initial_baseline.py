"""Initial baseline

Revision ID: cd35b3969a81
Revises:
Create Date: 2026-07-01 19:27:40.634473

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd35b3969a81'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    db_models.py'deki tabloları, sonraki iki migration'ın eklediği kolonlar/tablo
    (users.subscription_*, users.email_verified, auth_tokens) HARİÇ olacak şekilde
    oluşturur. SQLite geliştirme ortamında bu tablolar Base.metadata.create_all()
    ile zaten var olduğundan bu migration orada boştu (pass); taze Postgres
    kurulumlarında ise gerçek şemayı kurması gerekiyor.
    """
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=True),
        sa.Column('currency', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table(
        'positions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(), nullable=False),
        sa.Column('asset_class', sa.String(), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('buy_price', sa.Float(), nullable=False),
        sa.Column('buy_date', sa.Date(), nullable=False),
        sa.Column('buy_currency', sa.String(), nullable=False),
        sa.Column('cost_basis_tly', sa.Float(), nullable=True),
        sa.Column('asset_type', sa.String(), nullable=True),
        sa.Column('interest_rate', sa.Float(), nullable=True),
        sa.Column('maturity_date', sa.String(), nullable=True),
        sa.Column('commodity_type', sa.String(), nullable=True),
        sa.Column('unit', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'ticker', name='uq_user_ticker'),
    )
    op.create_index('idx_positions_user', 'positions', ['user_id'], unique=False)

    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('position_id', sa.Integer(), nullable=True),
        sa.Column('ticker', sa.String(), nullable=False),
        sa.Column('asset_class', sa.String(), nullable=False),
        sa.Column('transaction_type', sa.String(), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False),
        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['position_id'], ['positions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_transactions_user', 'transactions', ['user_id'], unique=False)
    op.create_index('idx_transactions_ticker', 'transactions', ['ticker'], unique=False)
    op.create_index('idx_transactions_date', 'transactions', ['transaction_date'], unique=False)

    op.create_table(
        'price_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ticker', sa.String(), nullable=False),
        sa.Column('asset_class', sa.String(), nullable=False),
        sa.Column('price_date', sa.Date(), nullable=False),
        sa.Column('price_usd', sa.Float(), nullable=True),
        sa.Column('price_try', sa.Float(), nullable=True),
        sa.Column('usd_try_rate', sa.Float(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticker', 'price_date', name='uq_ticker_date'),
    )
    op.create_index('idx_price_history_ticker_date', 'price_history', ['ticker', 'price_date'], unique=False)

    op.create_table(
        'exchange_rates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rate_date', sa.Date(), nullable=False),
        sa.Column('usd_try_rate', sa.Float(), nullable=False),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rate_date'),
    )

    op.create_table(
        'portfolio_snapshots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('total_invested_try', sa.Float(), nullable=True),
        sa.Column('total_value_try', sa.Float(), nullable=True),
        sa.Column('total_return_try', sa.Float(), nullable=True),
        sa.Column('total_return_pct', sa.Float(), nullable=True),
        sa.Column('snapshot_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'snapshot_date', name='uq_user_snapshot_date'),
    )
    op.create_index('idx_portfolio_snapshots_user_date', 'portfolio_snapshots', ['user_id', 'snapshot_date'], unique=False)

    op.create_table(
        'asset_class_summaries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('asset_class', sa.String(), nullable=False),
        sa.Column('total_invested_try', sa.Float(), nullable=True),
        sa.Column('total_value_try', sa.Float(), nullable=True),
        sa.Column('total_return_try', sa.Float(), nullable=True),
        sa.Column('total_return_pct', sa.Float(), nullable=True),
        sa.Column('position_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'snapshot_date', 'asset_class', name='uq_user_date_asset_class'),
    )
    op.create_index('idx_asset_class_summaries_date', 'asset_class_summaries', ['snapshot_date'], unique=False)

    op.create_table(
        'performance_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('period_date', sa.Date(), nullable=False),
        sa.Column('period_type', sa.String(), nullable=False),
        sa.Column('value_try', sa.Float(), nullable=True),
        sa.Column('return_pct', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'period_date', 'period_type', name='uq_user_period_type'),
    )
    op.create_index('idx_performance_history_user_date', 'performance_history', ['user_id', 'period_date'], unique=False)

    op.create_table(
        'liabilities',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('liability_type', sa.String(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(), nullable=True),
        sa.Column('due_date', sa.String(), nullable=True),
        sa.Column('interest_rate', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'target_allocations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('asset_class', sa.String(), nullable=False),
        sa.Column('target_pct', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'price_alerts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(), nullable=False),
        sa.Column('target_price', sa.Float(), nullable=False),
        sa.Column('condition', sa.String(), nullable=False),
        sa.Column('is_triggered', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('message', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('is_read', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('notifications')
    op.drop_table('price_alerts')
    op.drop_table('target_allocations')
    op.drop_table('liabilities')
    op.drop_index('idx_performance_history_user_date', table_name='performance_history')
    op.drop_table('performance_history')
    op.drop_index('idx_asset_class_summaries_date', table_name='asset_class_summaries')
    op.drop_table('asset_class_summaries')
    op.drop_index('idx_portfolio_snapshots_user_date', table_name='portfolio_snapshots')
    op.drop_table('portfolio_snapshots')
    op.drop_table('exchange_rates')
    op.drop_index('idx_price_history_ticker_date', table_name='price_history')
    op.drop_table('price_history')
    op.drop_index('idx_transactions_date', table_name='transactions')
    op.drop_index('idx_transactions_ticker', table_name='transactions')
    op.drop_index('idx_transactions_user', table_name='transactions')
    op.drop_table('transactions')
    op.drop_index('idx_positions_user', table_name='positions')
    op.drop_table('positions')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
