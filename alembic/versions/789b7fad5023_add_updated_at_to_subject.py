"""add_updated_at_to_subject

Revision ID: 789b7fad5023
Revises: 1290abddbdc0
Create Date: 2025-12-28 02:03:22.193964

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '789b7fad5023'
down_revision: Union[str, Sequence[str], None] = '1290abddbdc0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add updated_at column to subject table."""
    # Add updated_at column with server-side default
    op.add_column(
        'subject',
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False
        )
    )


def downgrade() -> None:
    """Remove updated_at column from subject table."""
    op.drop_column('subject', 'updated_at')
