"""
SQLAlchemy mixins for common model patterns.

These mixins provide reusable column definitions to follow DRY principles
and ensure consistency across all models.

Audit Levels:
    - TimestampMixin: Just timestamps (created_at, updated_at)
    - SoftDeleteMixin: Adds soft delete (deleted_at)
    - UserAuditMixin: Adds user tracking (created_by, updated_by, deleted_by)
    - FullAuditMixin: Complete audit trail with version tracking and metadata
"""
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy.sql import func

from utils.generators import generate_cuid


class CuidMixin:
    """
    Mixin for models using CUID as primary key.

    Provides:
        - id: String primary key with automatic CUID generation

    Usage:
        class MyModel(CuidMixin, Base):
            __tablename__ = "my_model"
            # ... other columns
    """

    @declared_attr
    def id(cls) -> Mapped[str]:
        return mapped_column(String, primary_key=True, default=generate_cuid)


class TenantMixin:
    """
    Mixin for multi-tenant models.

    Provides:
        - tenant_id: Foreign key to tenant table with cascade delete

    Usage:
        class MyModel(TenantMixin, Base):
            __tablename__ = "my_model"
            # ... other columns
    """

    @declared_attr
    def tenant_id(cls) -> Mapped[str]:
        return mapped_column(
            String,
            ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )


class TimestampMixin:
    """
    Mixin for timestamp tracking.

    Provides:
        - created_at: Timestamp set on creation (server-side default)
        - updated_at: Timestamp updated on modification (server-side default + onupdate)

    Note: Uses timezone-aware DateTime for consistency

    Usage:
        class MyModel(TimestampMixin, Base):
            __tablename__ = "my_model"
            # ... other columns
    """

    @declared_attr
    def created_at(cls) -> Mapped[datetime]:
        return mapped_column(
            DateTime(timezone=True), server_default=func.now(), nullable=False
        )

    @declared_attr
    def updated_at(cls) -> Mapped[datetime]:
        return mapped_column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        )


class SoftDeleteMixin:
    """
    Soft delete support (tombstone pattern).

    Provides:
        - deleted_at: Timestamp set on soft delete (null = not deleted)

    Usage:
        class MyModel(SoftDeleteMixin, Base):
            __tablename__ = "my_model"
            # ... other columns

        # In repository:
        # Soft delete: instance.deleted_at = func.now()
        # Query active only: .where(Model.deleted_at.is_(None))
    """

    @declared_attr
    def deleted_at(cls) -> Mapped[datetime | None]:
        return mapped_column(DateTime(timezone=True), nullable=True, index=True)


class UserAuditMixin(TimestampMixin, SoftDeleteMixin):
    """
    User audit tracking (who did what).

    Provides:
        - created_at: When record was created
        - updated_at: When record was last updated
        - deleted_at: When record was soft deleted
        - created_by: User ID who created the record
        - updated_by: User ID who last updated the record
        - deleted_by: User ID who soft deleted the record

    Note: User IDs are stored as strings (CUIDs) and are nullable to support
          system-generated records (e.g., migrations, background jobs)

    Usage:
        class MyModel(UserAuditMixin, Base):
            __tablename__ = "my_model"
            # ... other columns

        # In service/repository:
        # Create: instance.created_by = current_user.id
        # Update: instance.updated_by = current_user.id
        # Delete: instance.deleted_at = func.now(); instance.deleted_by = current_user.id
    """

    @declared_attr
    def created_by(cls) -> Mapped[str | None]:
        return mapped_column(
            String,
            ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        )

    @declared_attr
    def updated_by(cls) -> Mapped[str | None]:
        return mapped_column(
            String, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
        )

    @declared_attr
    def deleted_by(cls) -> Mapped[str | None]:
        return mapped_column(
            String, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
        )


class VersionedMixin:
    """
    Optimistic locking with version tracking.

    Provides:
        - version: Integer counter incremented on each update

    Prevents concurrent update conflicts (lost update problem).

    Usage:
        class MyModel(VersionedMixin, Base):
            __tablename__ = "my_model"
            # ... other columns

        # In service:
        # SQLAlchemy will automatically increment version on each update
        # To detect conflicts:
        # result = await db.execute(
        #     update(Model)
        #     .where(Model.id == id, Model.version == old_version)
        #     .values(data, version=old_version + 1)
        # )
        # if result.rowcount == 0:
        #     raise ConcurrentUpdateError("Record was modified by another user")
    """

    @declared_attr
    def version(cls) -> Mapped[int]:
        return mapped_column(Integer, default=1, nullable=False)


class FullAuditMixin(UserAuditMixin, VersionedMixin):
    """
    Complete audit trail with version tracking and metadata.

    Provides:
        - created_at, updated_at, deleted_at: Timestamps
        - created_by, updated_by, deleted_by: User tracking
        - version: Optimistic locking counter
        - audit_metadata: JSON field for additional audit context

    The audit_metadata field can store:
        - IP address of the user
        - User agent string
        - Request ID for tracing
        - Reason for change (for compliance)
        - Previous values (for full audit trail)
        - Custom application-specific context

    Usage:
        class MyModel(FullAuditMixin, Base):
            __tablename__ = "my_model"
            # ... other columns

        # In service:
        instance.audit_metadata = {
            "ip_address": request.client.host,
            "user_agent": request.headers.get("user-agent"),
            "reason": "Customer requested update",
            "request_id": request_id,
            "previous_values": {
                "status": old_status,
                "amount": old_amount
            }
        }
    """

    @declared_attr
    def audit_metadata(cls) -> Mapped[dict[str, Any] | None]:
        return mapped_column(JSON, nullable=True)


class MultiTenantModel(CuidMixin, TenantMixin, TimestampMixin):
    """
    Complete mixin for standard multi-tenant models.

    Combines:
        - CuidMixin: CUID primary key
        - TenantMixin: Tenant foreign key
        - TimestampMixin: Created/updated timestamps

    This is the most common pattern for Timeline models.

    Usage:
        class MyModel(MultiTenantModel, Base):
            __tablename__ = "my_model"

            # Your custom columns here
            name: Mapped[str]
            description: Mapped[Optional[str]]
    """

    __abstract__ = True


class AuditedMultiTenantModel(CuidMixin, TenantMixin, UserAuditMixin):
    """
    Multi-tenant model with full user audit tracking.

    Combines:
        - CuidMixin: CUID primary key
        - TenantMixin: Tenant foreign key
        - UserAuditMixin: Timestamps + user tracking + soft delete

    Use this for models where you need to track who created/updated/deleted records.

    Usage:
        class MyModel(AuditedMultiTenantModel, Base):
            __tablename__ = "my_model"

            # Your custom columns here
            name: Mapped[str]

        # In service:
        instance.created_by = current_user.id
        instance.updated_by = current_user.id
    """

    __abstract__ = True


class FullyAuditedMultiTenantModel(CuidMixin, TenantMixin, FullAuditMixin):
    """
    Multi-tenant model with complete audit trail.

    Combines:
        - CuidMixin: CUID primary key
        - TenantMixin: Tenant foreign key
        - FullAuditMixin: Complete audit trail (timestamps, users, version, metadata)

    Use this for critical business records that require comprehensive audit trails
    (financial transactions, compliance records, sensitive data changes).

    Usage:
        class Transaction(FullyAuditedMultiTenantModel, Base):
            __tablename__ = "transaction"

            amount: Mapped[Decimal]
            status: Mapped[str]

        # In service:
        transaction.created_by = current_user.id
        transaction.audit_metadata = {
            "ip_address": request.client.host,
            "reason": "Customer withdrawal",
            "previous_balance": old_balance
        }
    """

    __abstract__ = True
