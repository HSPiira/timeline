"""add missing timestamp defaults to oauth tables

Revision ID: 0808a66fe6bf
Revises: 063b9eee42d4
Create Date: 2025-12-29 08:56:52.266958

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0808a66fe6bf'
down_revision: Union[str, Sequence[str], None] = '063b9eee42d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'oauth_provider_config',
        'created_at',
        server_default=sa.text('now()')
    )
    op.alter_column(
        'oauth_provider_config',
        'updated_at',
        server_default=sa.text('now()'),
        onupdate=sa.text('now()')
    )

    op.alter_column(
        'oauth_state',
        'created_at',
        server_default=sa.text('now()')
    )

    op.alter_column(
        'oauth_audit_log',
        'timestamp',
        server_default=sa.text('now()')
    )


def downgrade() -> None:
    """Downgrade schema."""
