"""add_rbac_tables

Revision ID: 9e1aedfa0671
Revises: 934461a1e264
Create Date: 2025-12-16 18:51:04.735621

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e1aedfa0671"
down_revision: Union[str, Sequence[str], None] = "934461a1e264"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add RBAC tables (role, permission, role_permission, user_role)."""

    # Create role table
    op.create_table(
        "role",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
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
        sa.UniqueConstraint("tenant_id", "code", name="uq_role_tenant_code"),
    )
    op.create_index("ix_role_tenant_id", "role", ["tenant_id"])

    # Create permission table
    op.create_table(
        "permission",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("resource", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_permission_tenant_code"),
    )
    op.create_index("ix_permission_tenant_id", "permission", ["tenant_id"])
    op.create_index("ix_permission_resource", "permission", ["resource"])
    op.create_index("ix_permission_action", "permission", ["action"])
    op.create_index(
        "ix_permission_resource_action",
        "permission",
        ["tenant_id", "resource", "action"],
    )

    # Create role_permission table (many-to-many)
    op.create_table(
        "role_permission",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("role_id", sa.String(), nullable=False),
        sa.Column("permission_id", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permission.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )
    op.create_index("ix_role_permission_tenant_id", "role_permission", ["tenant_id"])
    op.create_index("ix_role_permission_lookup", "role_permission", ["tenant_id", "role_id"])

    # Create user_role table (many-to-many)
    op.create_table(
        "user_role",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role_id", sa.String(), nullable=False),
        sa.Column("assigned_by", sa.String(), nullable=True),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by"], ["user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )
    op.create_index("ix_user_role_tenant_id", "user_role", ["tenant_id"])
    op.create_index("ix_user_role_lookup", "user_role", ["tenant_id", "user_id"])


def downgrade() -> None:
    """Downgrade schema - remove RBAC tables."""

    # Drop user_role table
    op.drop_index("ix_user_role_lookup", "user_role")
    op.drop_index("ix_user_role_tenant_id", "user_role")
    op.drop_table("user_role")

    # Drop role_permission table
    op.drop_index("ix_role_permission_lookup", "role_permission")
    op.drop_index("ix_role_permission_tenant_id", "role_permission")
    op.drop_table("role_permission")

    # Drop permission table
    op.drop_index("ix_permission_resource_action", "permission")
    op.drop_index("ix_permission_action", "permission")
    op.drop_index("ix_permission_resource", "permission")
    op.drop_index("ix_permission_tenant_id", "permission")
    op.drop_table("permission")

    # Drop role table
    op.drop_index("ix_role_tenant_id", "role")
    op.drop_table("role")
