"""add_server_defaults_to_email_account_timestamps

Revision ID: 68c22898a728
Revises: 703d6dc32355
Create Date: 2025-12-27 00:07:38.123847

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68c22898a728'
down_revision: Union[str, Sequence[str], None] = '703d6dc32355'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add server defaults to timestamp columns
    op.alter_column(
        'email_account',
        'created_at',
        existing_type=sa.DateTime(),
        server_default=sa.text('now()'),
        existing_nullable=False
    )
    op.alter_column(
        'email_account',
        'updated_at',
        existing_type=sa.DateTime(),
        server_default=sa.text('now()'),
        existing_nullable=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove server defaults from timestamp columns
    op.alter_column(
        'email_account',
        'created_at',
        existing_type=sa.DateTime(),
        server_default=None,
        existing_nullable=False
    )
    op.alter_column(
        'email_account',
        'updated_at',
        existing_type=sa.DateTime(),
        server_default=None,
        existing_nullable=False
    )
