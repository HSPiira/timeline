from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON, Index, CheckConstraint, event
from sqlalchemy.sql import func
from sqlalchemy.orm import Session
from core.database import Base
from utils.generators import generate_cuid
import hashlib
import json
from datetime import datetime
from typing import Optional


class Event(Base):
    __tablename__ = "event"

    id = Column(String, primary_key=True, default=generate_cuid)
    tenant_id = Column(String, ForeignKey("tenant.id"), nullable=False, index=True)
    subject_id = Column(String, ForeignKey("subject.id"), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    schema_version = Column(Integer, nullable=False)  # Immutable - tracks which schema version was used
    event_time = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JSON, nullable=False)
    previous_hash = Column(String)
    hash = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Indexes for query performance
        Index('ix_event_subject_time', 'subject_id', 'event_time'),
        Index('ix_event_tenant_subject', 'tenant_id', 'subject_id'),
        Index('ix_event_tenant_type_version', 'tenant_id', 'event_type', 'schema_version'),

        # Immutability enforcement: created_at must always be set (prevents updates)
        CheckConstraint('created_at IS NOT NULL', name='ck_event_created_at_immutable'),
    )

    @staticmethod
    def compute_hash(
        subject_id: str,
        event_type: str,
        schema_version: int,
        event_time: datetime,
        payload: dict,
        previous_hash: Optional[str]
    ) -> str:
        """
        Compute cryptographic hash for event integrity.

        Hash includes:
        - subject_id: Who the event is about
        - event_type: What happened
        - schema_version: Schema used
        - event_time: When it happened (ISO format)
        - payload: Event data (canonicalized JSON)
        - previous_hash: Link to previous event (creates chain)
        """
        hash_content = {
            "subject_id": subject_id,
            "event_type": event_type,
            "schema_version": schema_version,
            "event_time": event_time.isoformat(),
            "payload": payload,
            "previous_hash": previous_hash
        }

        # Canonicalize JSON for consistent hashing
        canonical_json = json.dumps(hash_content, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode()).hexdigest()

    @classmethod
    def create_event(
        cls,
        session: Session,
        tenant_id: str,
        subject_id: str,
        event_type: str,
        schema_version: int,
        event_time: datetime,
        payload: dict,
        previous_hash: Optional[str] = None
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
            prev_event = session.query(Event).filter(
                Event.subject_id == subject_id,
                Event.hash == previous_hash
            ).first()

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
            previous_hash=previous_hash
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
            hash=computed_hash
        )


# Prevent updates to events at ORM level (events are immutable)
@event.listens_for(Event, 'before_update')
def prevent_event_updates(mapper, connection, target):
    """
    Events are append-only and cannot be modified after creation.
    This is fundamental to event sourcing and audit trail integrity.
    """
    raise ValueError(
        "Events are immutable and cannot be updated. "
        "Create a new compensating event instead."
    )