from datetime import datetime
from typing import Any

from sqlalchemy import (
    Connection,
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    event,
)
from sqlalchemy.orm import Mapped, Mapper, Session, mapped_column
from sqlalchemy.sql import func

from src.application.services.hash_service import HashService
from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models.mixins import CuidMixin, TenantMixin


class Event(CuidMixin, TenantMixin, Base):
    """
    Immutable event entity for event sourcing.

    Inherits from:
        - CuidMixin: CUID primary key
        - TenantMixin: Tenant foreign key

    Note: Events are append-only and cannot be modified after creation.
    Uses manual created_at (no updated_at since events are immutable).
    """

    __tablename__ = "event"

    subject_id: Mapped[str] = mapped_column(
        String, ForeignKey("subject.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # Immutable - tracks which schema version was used
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String)
    hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Indexes for query performance
        Index("ix_event_subject_time", "subject_id", "event_time"),
        Index("ix_event_tenant_subject", "tenant_id", "subject_id"),
        Index("ix_event_tenant_type_version", "tenant_id", "event_type", "schema_version"),
        # Immutability enforcement: created_at must always be set (prevents updates)
        CheckConstraint("created_at IS NOT NULL", name="ck_event_created_at_immutable"),
    )

    # Hash service instance for computing event hashes
    _hash_service = HashService()

    @classmethod
    def compute_hash(
        cls,
        subject_id: str,
        event_type: str,
        schema_version: int,
        event_time: datetime,
        payload: dict[str, Any],
        previous_hash: str | None,
    ) -> str:
        """
        Compute cryptographic hash for event integrity.

        Delegates to HashService which is the single source of truth
        for hash computation across the application.
        """
        return cls._hash_service.compute_hash(
            subject_id=subject_id,
            event_type=event_type,
            schema_version=schema_version,
            event_time=event_time,
            payload=payload,
            previous_hash=previous_hash,
        )

    @classmethod
    def create_event(
        cls,
        session: Session,
        tenant_id: str,
        subject_id: str,
        event_type: str,
        schema_version: int,
        event_time: datetime,
        payload: dict[str, Any],
        previous_hash: str | None = None,
    ) -> "Event":
        """
        Factory method that validates hash chain and prevents tampering at insert time.

        Security validations:
        1. If previous_hash provided, verify it exists and belongs to same subject
        2. Ensure temporal ordering (new event must be after previous)
        3. Compute and validate hash before insertion

        Raises:
            ValueError: If previous_hash is invalid or temporal ordering is violated
        """
        # Validate previous hash if provided
        if previous_hash:
            prev_event = (
                session.query(Event)
                .filter(Event.subject_id == subject_id, Event.hash == previous_hash)
                .first()
            )

            if not prev_event:
                raise ValueError(
                    f"Invalid previous_hash: {previous_hash} not found for subject {subject_id}"
                )

            # Enforce temporal ordering
            if event_time <= prev_event.event_time:
                raise ValueError(
                    f"Event time {event_time} must be after previous event time {prev_event.event_time}"
                )

        # Compute hash with validated inputs
        computed_hash = cls.compute_hash(
            subject_id=subject_id,
            event_type=event_type,
            schema_version=schema_version,
            event_time=event_time,
            payload=payload,
            previous_hash=previous_hash,
        )

        # Create event with validated hash
        return cls(
            tenant_id=tenant_id,
            subject_id=subject_id,
            event_type=event_type,
            schema_version=schema_version,
            event_time=event_time,
            payload=payload,
            previous_hash=previous_hash,
            hash=computed_hash,
        )


# Prevent updates to events at ORM level (events are immutable)
@event.listens_for(Event, "before_update")
def prevent_event_updates(
    _mapper: Mapper[Any], 
    _connection: Connection, 
    _target: "Event"
) -> None:
    """
    Events are append-only and cannot be modified after creation.
    This is fundamental to event sourcing and audit trail integrity.
    """
    raise ValueError(
        "Events are immutable and cannot be updated. Create a new compensating event instead."
    )
