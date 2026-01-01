"""add_event_schema_versioning_support

Revision ID: 703d6dc32355
Revises: ba0e2857597d
Create Date: 2025-12-24 01:14:08.764867

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "703d6dc32355"
down_revision: Union[str, Sequence[str], None] = "ba0e2857597d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add event schema versioning support."""
    # 1. Add schema_version column to event table
    # Using server_default='1' for existing rows, then removing it
    op.add_column(
        "event",
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("event", "schema_version", server_default=None)

    # 2. Add created_by column to event_schema table
    op.add_column("event_schema", sa.Column("created_by", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_event_schema_created_by_user",
        "event_schema",
        "user",
        ["created_by"],
        ["id"],
    )

    # 3. Change is_active default from True to False in event_schema table
    op.alter_column("event_schema", "is_active", server_default="false")

    # 4. Add index on (event_type, schema_version) in event table
    op.create_index("ix_event_type_version", "event", ["event_type", "schema_version"])


def downgrade() -> None:
    """Downgrade schema - remove event schema versioning support."""
    # Remove in reverse order
    # 4. Drop index on (event_type, schema_version)
    op.drop_index("ix_event_type_version", "event")

    # 3. Revert is_active default back to True
    op.alter_column("event_schema", "is_active", server_default="true")

    # 2. Remove created_by column from event_schema
    op.drop_constraint(
        "fk_event_schema_created_by_user", "event_schema", type_="foreignkey"
    )
    op.drop_column("event_schema", "created_by")

    # 1. Remove schema_version column from event
    op.drop_column("event", "schema_version")
