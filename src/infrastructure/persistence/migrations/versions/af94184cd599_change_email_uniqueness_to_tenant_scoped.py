"""change_email_uniqueness_to_tenant_scoped

Revision ID: af94184cd599
Revises: e86ff0b3330d
Create Date: 2025-12-15 21:25:26.315545

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "af94184cd599"
down_revision: Union[str, Sequence[str], None] = "e86ff0b3330d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - change email uniqueness from global to tenant-scoped."""
    # Drop global email unique constraint
    op.drop_constraint("uq_user_email", "user", type_="unique")

    # Add tenant-scoped email unique constraint
    op.create_unique_constraint("uq_tenant_email", "user", ["tenant_id", "email"])


def downgrade() -> None:
    """Downgrade schema - revert to global email uniqueness."""
    # Drop tenant-scoped email constraint
    op.drop_constraint("uq_tenant_email", "user", type_="unique")

    # Restore global email unique constraint
    op.create_unique_constraint("uq_user_email", "user", ["email"])
