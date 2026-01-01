"""rename schema_json to schema_definition

Revision ID: f61af9c8e951
Revises: e469986dce88
Create Date: 2025-12-17 04:25:47.255722

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f61af9c8e951"
down_revision: Union[str, Sequence[str], None] = "e469986dce88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Rename column from schema_json to schema_definition
    op.alter_column("event_schema", "schema_json", new_column_name="schema_definition")


def downgrade() -> None:
    """Downgrade schema."""
    # Rename column back from schema_definition to schema_json
    op.alter_column("event_schema", "schema_definition", new_column_name="schema_json")
