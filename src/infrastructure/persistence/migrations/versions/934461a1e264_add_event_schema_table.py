"""add event_schema table

Revision ID: 934461a1e264
Revises: af94184cd599
Create Date: 2025-12-15 22:48:57.917747

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "934461a1e264"
down_revision: Union[str, Sequence[str], None] = "af94184cd599"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add event_schema table for tenant-specific event validation."""
    op.create_table(
        "event_schema",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id", "event_type", "version", name="uq_tenant_event_type_version"
        ),
    )
    op.create_index("ix_event_schema_tenant_id", "event_schema", ["tenant_id"])
    op.create_index("ix_event_schema_event_type", "event_schema", ["event_type"])
    op.create_index(
        "ix_event_schema_active",
        "event_schema",
        ["tenant_id", "event_type", "is_active"],
    )


def downgrade() -> None:
    """Downgrade schema - remove event_schema table."""
    op.drop_index("ix_event_schema_active", "event_schema")
    op.drop_index("ix_event_schema_event_type", "event_schema")
    op.drop_index("ix_event_schema_tenant_id", "event_schema")
    op.drop_table("event_schema")
