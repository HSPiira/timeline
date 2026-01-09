"""Add sync status tracking to email account

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2025-01-09 12:30:00.000000

Adds sync status tracking fields to email_account for monitoring
background sync progress and status.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add sync status tracking columns."""
    # Sync status tracking
    op.add_column(
        "email_account",
        sa.Column("sync_status", sa.String(), nullable=False, server_default="idle"),
    )
    op.add_column(
        "email_account",
        sa.Column("sync_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "email_account",
        sa.Column("sync_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "email_account",
        sa.Column("sync_messages_fetched", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "email_account",
        sa.Column("sync_events_created", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "email_account",
        sa.Column("sync_error", sa.String(), nullable=True),
    )

    # Add index for sync_status to optimize status queries
    op.create_index("ix_email_account_sync_status", "email_account", ["sync_status"])


def downgrade() -> None:
    """Remove sync status tracking columns."""
    op.drop_index("ix_email_account_sync_status", table_name="email_account")
    op.drop_column("email_account", "sync_error")
    op.drop_column("email_account", "sync_events_created")
    op.drop_column("email_account", "sync_messages_fetched")
    op.drop_column("email_account", "sync_completed_at")
    op.drop_column("email_account", "sync_started_at")
    op.drop_column("email_account", "sync_status")
