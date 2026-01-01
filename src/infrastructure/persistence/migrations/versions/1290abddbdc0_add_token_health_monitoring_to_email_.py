"""add_token_health_monitoring_to_email_account

Revision ID: 1290abddbdc0
Revises: 68c22898a728
Create Date: 2025-12-27 00:29:57.186647

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1290abddbdc0"
down_revision: Union[str, Sequence[str], None] = "68c22898a728"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add token health monitoring fields
    op.add_column(
        "email_account",
        sa.Column("token_last_refreshed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "email_account",
        sa.Column("token_refresh_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "email_account",
        sa.Column("token_refresh_failures", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("email_account", sa.Column("last_auth_error", sa.String(), nullable=True))
    op.add_column("email_account", sa.Column("last_auth_error_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove token health monitoring fields
    op.drop_column("email_account", "last_auth_error_at")
    op.drop_column("email_account", "last_auth_error")
    op.drop_column("email_account", "token_refresh_failures")
    op.drop_column("email_account", "token_refresh_count")
    op.drop_column("email_account", "token_last_refreshed_at")
