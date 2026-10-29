"""Esquema inicial del MVP (spec §7): users, refresh_tokens, clients, invoices,
payments, audit_events e import_batches.

Revision ID: 0001
Revises:
Create Date: 2026-10-28 23:58:32.649099+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('clients',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('tax_id', sa.String(length=20), nullable=True),
    sa.Column('email', sa.String(length=254), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clients'))
    )
    op.create_index('uq_clients_name_lower', 'clients', [sa.literal_column('lower(name)')], unique=True)
    op.create_table('users',
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=150), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('admin', 'operator')", name=op.f('ck_users_role_valid')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('audit_events',
    sa.Column('actor_user_id', sa.Uuid(), nullable=False),
    sa.Column('entity_type', sa.String(length=30), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=False),
    sa.Column('action', sa.String(length=30), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_audit_events_actor_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events'))
    )
    op.create_index('ix_audit_events_entity', 'audit_events', ['entity_type', 'entity_id'], unique=False)
    op.create_table('import_batches',
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('row_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('imported_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('rejected_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_import_batches_created_by_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_import_batches'))
    )
    op.create_table('invoices',
    sa.Column('client_id', sa.Uuid(), nullable=False),
    sa.Column('invoice_number', sa.String(length=50), nullable=False),
    sa.Column('issue_date', sa.Date(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), server_default='ARS', nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_void', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("currency = 'ARS'", name=op.f('ck_invoices_currency_ars')),
    sa.CheckConstraint('amount > 0', name=op.f('ck_invoices_amount_positive')),
    sa.CheckConstraint('due_date >= issue_date', name=op.f('ck_invoices_due_after_issue')),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], name=op.f('fk_invoices_client_id_clients'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_invoices_created_by_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invoices')),
    sa.UniqueConstraint('client_id', 'invoice_number', name='uq_invoices_client_number')
    )
    op.create_index('ix_invoices_client_id_due_date', 'invoices', ['client_id', 'due_date'], unique=False)
    op.create_index('ix_invoices_due_date_active', 'invoices', ['due_date'], unique=False, postgresql_where=sa.text('NOT is_void'))
    op.create_table('refresh_tokens',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('replaced_by_id', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_refresh_tokens_token_hash'))
    )
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'], unique=False)
    op.create_table('payments',
    sa.Column('invoice_id', sa.Uuid(), nullable=False),
    sa.Column('payment_date', sa.Date(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False),
    sa.Column('method', sa.String(length=30), nullable=False),
    sa.Column('reference', sa.String(length=100), nullable=True),
    sa.Column('is_void', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('void_reason', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('voided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('amount > 0', name=op.f('ck_payments_amount_positive')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_payments_created_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], name=op.f('fk_payments_invoice_id_invoices'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payments'))
    )
    op.create_index('ix_payments_invoice_id_active', 'payments', ['invoice_id'], unique=False, postgresql_where=sa.text('NOT is_void'))
    op.create_index('ix_payments_payment_date', 'payments', ['payment_date'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_payments_payment_date', table_name='payments')
    op.drop_index('ix_payments_invoice_id_active', table_name='payments', postgresql_where=sa.text('NOT is_void'))
    op.drop_table('payments')
    op.drop_index('ix_refresh_tokens_user_id', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index('ix_invoices_due_date_active', table_name='invoices', postgresql_where=sa.text('NOT is_void'))
    op.drop_index('ix_invoices_client_id_due_date', table_name='invoices')
    op.drop_table('invoices')
    op.drop_table('import_batches')
    op.drop_index('ix_audit_events_entity', table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_table('users')
    op.drop_index('uq_clients_name_lower', table_name='clients')
    op.drop_table('clients')
