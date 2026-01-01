"""Initial schema: tenants, subjects, events, documents

Revision ID: 6cb0887d08e6
Revises:
Create Date: 2025-12-14 09:22:13.224323

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6cb0887d08e6"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema."""
    # Create tenant table
    op.create_table(
        "tenant",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'archived')", name="tenant_status_check"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_tenant_code"), "tenant", ["code"], unique=True)
    op.create_index(op.f("ix_tenant_status"), "tenant", ["status"], unique=False)

    # Create subject table
    op.create_table(
        "subject",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("subject_type", sa.String(), nullable=False),
        sa.Column("external_ref", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_subject_external_ref"), "subject", ["external_ref"], unique=False
    )
    op.create_index(
        op.f("ix_subject_subject_type"), "subject", ["subject_type"], unique=False
    )
    op.create_index(
        op.f("ix_subject_tenant_id"), "subject", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_subject_tenant_type", "subject", ["tenant_id", "subject_type"], unique=False
    )

    # Create event table
    op.create_table(
        "event",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("subject_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("previous_hash", sa.String(), nullable=True),
        sa.Column("hash", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subject.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hash"),
    )
    op.create_index(op.f("ix_event_event_type"), "event", ["event_type"], unique=False)
    op.create_index(op.f("ix_event_hash"), "event", ["hash"], unique=True)
    op.create_index(op.f("ix_event_subject_id"), "event", ["subject_id"], unique=False)
    op.create_index(op.f("ix_event_tenant_id"), "event", ["tenant_id"], unique=False)
    op.create_index(
        "ix_event_subject_time", "event", ["subject_id", "event_time"], unique=False
    )
    op.create_index(
        "ix_event_tenant_subject", "event", ["tenant_id", "subject_id"], unique=False
    )

    # Create document table
    op.create_table(
        "document",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("subject_id", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=True),
        sa.Column("document_type", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(), nullable=False),
        sa.Column("storage_ref", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_document_id", sa.String(), nullable=True),
        sa.Column("is_latest_version", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["event.id"],
        ),
        sa.ForeignKeyConstraint(
            ["parent_document_id"],
            ["document.id"],
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subject.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_checksum"), "document", ["checksum"], unique=False
    )
    op.create_index(
        op.f("ix_document_document_type"), "document", ["document_type"], unique=False
    )
    op.create_index(
        op.f("ix_document_event_id"), "document", ["event_id"], unique=False
    )
    op.create_index(
        op.f("ix_document_subject_id"), "document", ["subject_id"], unique=False
    )
    op.create_index(
        op.f("ix_document_tenant_id"), "document", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_document_tenant_checksum",
        "document",
        ["tenant_id", "checksum"],
        unique=False,
    )


def downgrade() -> None:
    """Drop all tables."""
    op.drop_index("ix_document_tenant_checksum", table_name="document")
    op.drop_index(op.f("ix_document_tenant_id"), table_name="document")
    op.drop_index(op.f("ix_document_subject_id"), table_name="document")
    op.drop_index(op.f("ix_document_event_id"), table_name="document")
    op.drop_index(op.f("ix_document_document_type"), table_name="document")
    op.drop_index(op.f("ix_document_checksum"), table_name="document")
    op.drop_table("document")

    op.drop_index("ix_event_tenant_subject", table_name="event")
    op.drop_index("ix_event_subject_time", table_name="event")
    op.drop_index(op.f("ix_event_tenant_id"), table_name="event")
    op.drop_index(op.f("ix_event_subject_id"), table_name="event")
    op.drop_index(op.f("ix_event_hash"), table_name="event")
    op.drop_index(op.f("ix_event_event_type"), table_name="event")
    op.drop_table("event")

    op.drop_index("ix_subject_tenant_type", table_name="subject")
    op.drop_index(op.f("ix_subject_tenant_id"), table_name="subject")
    op.drop_index(op.f("ix_subject_subject_type"), table_name="subject")
    op.drop_index(op.f("ix_subject_external_ref"), table_name="subject")
    op.drop_table("subject")

    op.drop_index(op.f("ix_tenant_status"), table_name="tenant")
    op.drop_index(op.f("ix_tenant_code"), table_name="tenant")
    op.drop_table("tenant")
