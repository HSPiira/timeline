"""Add Gmail history ID to email account

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2025-01-10 10:00:00.000000

Adds Gmail History API support fields for incremental sync:
- gmail_history_id: Last known history ID for incremental sync
- history_sync_enabled: Whether to use history-based sync
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add Gmail history ID columns for incremental sync."""
    # Gmail History API support
    op.add_column(
        "email_account",
        sa.Column("gmail_history_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "email_account",
        sa.Column("history_sync_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    """Remove Gmail history ID columns."""
    op.drop_column("email_account", "history_sync_enabled")
    op.drop_column("email_account", "gmail_history_id")
