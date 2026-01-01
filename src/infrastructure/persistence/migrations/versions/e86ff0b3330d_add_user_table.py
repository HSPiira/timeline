"""add_user_table

Revision ID: e86ff0b3330d
Revises: 6cb0887d08e6
Create Date: 2025-12-15 17:15:55.310271

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e86ff0b3330d"
down_revision: Union[str, Sequence[str], None] = "6cb0887d08e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "username", name="uq_tenant_username"),
        sa.UniqueConstraint("email", name="uq_user_email"),
    )
    op.create_index("ix_user_tenant_id", "user", ["tenant_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_user_tenant_id", table_name="user")
    op.drop_table("user")
