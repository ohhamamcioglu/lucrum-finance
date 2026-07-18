"""add_audit_logs_table

Revision ID: b7e4a2c9f1d3
Revises: f3a9c1d8e2b7
Create Date: 2026-07-18 00:00:00.000000

Admin panel: tier/aktiflik değişimi ve destek amaçlı portföy görüntüleme
işlemlerinin kalıcı izini tutan audit_logs tablosu. admin_user_id/target_user_id
FK'leri ondelete='SET NULL' — kullanıcı silinse (bkz. DELETE /api/users/me)
bile audit kaydının kendisi kaybolmamalı, sadece FK bağı boşa çıkar (e-posta
zaten metin olarak ayrıca saklanıyor).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7e4a2c9f1d3'
down_revision: Union[str, Sequence[str], None] = 'f3a9c1d8e2b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('admin_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('admin_email', sa.String(), nullable=True),
        sa.Column('target_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('target_email', sa.String(), nullable=True),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('details', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_audit_logs_admin_user_id', 'audit_logs', ['admin_user_id'])
    op.create_index('ix_audit_logs_target_user_id', 'audit_logs', ['target_user_id'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('ix_audit_logs_target_user_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_admin_user_id', table_name='audit_logs')
    op.drop_table('audit_logs')
