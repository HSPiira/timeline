"""add_oauth_provider_tables_and_email_account_oauth_fields

Revision ID: 063b9eee42d4
Revises: 086f991ff6d7
Create Date: 2025-12-28 15:30:12.343396

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '063b9eee42d4'
down_revision: Union[str, Sequence[str], None] = '086f991ff6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create oauth_provider_config table
    op.create_table(
        'oauth_provider_config',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('provider_type', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('superseded_by_id', sa.String(), nullable=True),
        sa.Column('client_id_encrypted', sa.String(), nullable=False),
        sa.Column('client_secret_encrypted', sa.String(), nullable=False),
        sa.Column('encryption_key_id', sa.String(), nullable=False),
        sa.Column('redirect_uri', sa.String(), nullable=False),
        sa.Column('redirect_uri_whitelist', sa.JSON(), nullable=False),
        sa.Column('allowed_scopes', sa.JSON(), nullable=False),
        sa.Column('default_scopes', sa.JSON(), nullable=False),
        sa.Column('tenant_configured_scopes', sa.JSON(), nullable=False),
        sa.Column('authorization_endpoint', sa.String(), nullable=False),
        sa.Column('token_endpoint', sa.String(), nullable=False),
        sa.Column('provider_metadata', sa.JSON(), nullable=True),
        sa.Column('health_status', sa.String(), nullable=False),
        sa.Column('last_health_check_at', sa.DateTime(), nullable=True),
        sa.Column('last_health_error', sa.String(), nullable=True),
        sa.Column('rate_limit_connections_per_hour', sa.Integer(), nullable=True),
        sa.Column('current_hour_connections', sa.Integer(), nullable=False),
        sa.Column('rate_limit_reset_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_oauth_provider_config_deleted_at'), 'oauth_provider_config', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_oauth_provider_config_health_status'), 'oauth_provider_config', ['health_status'], unique=False)
    op.create_index(op.f('ix_oauth_provider_config_is_active'), 'oauth_provider_config', ['is_active'], unique=False)
    op.create_index(op.f('ix_oauth_provider_config_provider_type'), 'oauth_provider_config', ['provider_type'], unique=False)
    op.create_index(op.f('ix_oauth_provider_config_superseded_by_id'), 'oauth_provider_config', ['superseded_by_id'], unique=False)
    op.create_index(op.f('ix_oauth_provider_config_tenant_id'), 'oauth_provider_config', ['tenant_id'], unique=False)

    # Create oauth_state table
    op.create_table(
        'oauth_state',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('provider_config_id', sa.String(), nullable=False),
        sa.Column('nonce', sa.String(), nullable=False),
        sa.Column('signature', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('consumed', sa.Boolean(), nullable=False),
        sa.Column('consumed_at', sa.DateTime(), nullable=True),
        sa.Column('callback_received_at', sa.DateTime(), nullable=True),
        sa.Column('return_url', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['provider_config_id'], ['oauth_provider_config.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_oauth_state_consumed'), 'oauth_state', ['consumed'], unique=False)
    op.create_index(op.f('ix_oauth_state_expires_at'), 'oauth_state', ['expires_at'], unique=False)
    op.create_index(op.f('ix_oauth_state_provider_config_id'), 'oauth_state', ['provider_config_id'], unique=False)
    op.create_index(op.f('ix_oauth_state_tenant_id'), 'oauth_state', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_oauth_state_user_id'), 'oauth_state', ['user_id'], unique=False)

    # Create oauth_audit_log table
    op.create_table(
        'oauth_audit_log',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('provider_config_id', sa.String(), nullable=False),
        sa.Column('actor_user_id', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('changes', sa.JSON(), nullable=False),
        sa.Column('reason', sa.String(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['provider_config_id'], ['oauth_provider_config.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_oauth_audit_log_actor_user_id'), 'oauth_audit_log', ['actor_user_id'], unique=False)
    op.create_index(op.f('ix_oauth_audit_log_provider_config_id'), 'oauth_audit_log', ['provider_config_id'], unique=False)
    op.create_index(op.f('ix_oauth_audit_log_tenant_id'), 'oauth_audit_log', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_oauth_audit_log_timestamp'), 'oauth_audit_log', ['timestamp'], unique=False)

    # Add OAuth tracking fields to email_account table
    op.add_column('email_account', sa.Column('oauth_provider_config_id', sa.String(), nullable=True))
    op.add_column('email_account', sa.Column('oauth_provider_config_version', sa.Integer(), nullable=True))
    op.add_column('email_account', sa.Column('granted_scopes', sa.JSON(), nullable=True))
    op.add_column('email_account', sa.Column('oauth_status', sa.String(), nullable=False, server_default='active'))
    op.add_column('email_account', sa.Column('oauth_error_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('email_account', sa.Column('oauth_next_retry_at', sa.DateTime(), nullable=True))
    op.add_column('email_account', sa.Column('token_last_refreshed_at', sa.DateTime(), nullable=True))
    op.add_column('email_account', sa.Column('token_refresh_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('email_account', sa.Column('token_refresh_failures', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('email_account', sa.Column('last_auth_error', sa.String(), nullable=True))
    op.add_column('email_account', sa.Column('last_auth_error_at', sa.DateTime(), nullable=True))

    op.create_index(op.f('ix_email_account_oauth_provider_config_id'), 'email_account', ['oauth_provider_config_id'], unique=False)
    op.create_index(op.f('ix_email_account_oauth_status'), 'email_account', ['oauth_status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Remove indexes from email_account
    op.drop_index(op.f('ix_email_account_oauth_status'), table_name='email_account')
    op.drop_index(op.f('ix_email_account_oauth_provider_config_id'), table_name='email_account')

    # Remove OAuth tracking columns from email_account
    op.drop_column('email_account', 'last_auth_error_at')
    op.drop_column('email_account', 'last_auth_error')
    op.drop_column('email_account', 'token_refresh_failures')
    op.drop_column('email_account', 'token_refresh_count')
    op.drop_column('email_account', 'token_last_refreshed_at')
    op.drop_column('email_account', 'oauth_next_retry_at')
    op.drop_column('email_account', 'oauth_error_count')
    op.drop_column('email_account', 'oauth_status')
    op.drop_column('email_account', 'granted_scopes')
    op.drop_column('email_account', 'oauth_provider_config_version')
    op.drop_column('email_account', 'oauth_provider_config_id')

    # Drop oauth_audit_log table
    op.drop_index(op.f('ix_oauth_audit_log_timestamp'), table_name='oauth_audit_log')
    op.drop_index(op.f('ix_oauth_audit_log_tenant_id'), table_name='oauth_audit_log')
    op.drop_index(op.f('ix_oauth_audit_log_provider_config_id'), table_name='oauth_audit_log')
    op.drop_index(op.f('ix_oauth_audit_log_actor_user_id'), table_name='oauth_audit_log')
    op.drop_table('oauth_audit_log')

    # Drop oauth_state table
    op.drop_index(op.f('ix_oauth_state_user_id'), table_name='oauth_state')
    op.drop_index(op.f('ix_oauth_state_tenant_id'), table_name='oauth_state')
    op.drop_index(op.f('ix_oauth_state_provider_config_id'), table_name='oauth_state')
    op.drop_index(op.f('ix_oauth_state_expires_at'), table_name='oauth_state')
    op.drop_index(op.f('ix_oauth_state_consumed'), table_name='oauth_state')
    op.drop_table('oauth_state')

    # Drop oauth_provider_config table
    op.drop_index(op.f('ix_oauth_provider_config_tenant_id'), table_name='oauth_provider_config')
    op.drop_index(op.f('ix_oauth_provider_config_superseded_by_id'), table_name='oauth_provider_config')
    op.drop_index(op.f('ix_oauth_provider_config_provider_type'), table_name='oauth_provider_config')
    op.drop_index(op.f('ix_oauth_provider_config_is_active'), table_name='oauth_provider_config')
    op.drop_index(op.f('ix_oauth_provider_config_health_status'), table_name='oauth_provider_config')
    op.drop_index(op.f('ix_oauth_provider_config_deleted_at'), table_name='oauth_provider_config')
    op.drop_table('oauth_provider_config')
