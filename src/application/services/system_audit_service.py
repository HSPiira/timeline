"""
System Audit Service for automatic event tracking of internal CRUD operations.

This service creates immutable audit events for all system entity changes,
using the proper EventSchema infrastructure for validation and consistency.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from src.application.services.system_audit_schema import (
    SYSTEM_AUDIT_EVENT_TYPE,
    SYSTEM_AUDIT_SCHEMA_VERSION,
    SYSTEM_AUDIT_SUBJECT_REF,
    SYSTEM_AUDIT_SUBJECT_TYPE,
)
from src.shared.enums import ActorType, AuditAction
from src.shared.telemetry.logging import get_logger
from src.shared.utils import utc_now

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.infrastructure.persistence.models.event import Event

logger = get_logger(__name__)


class SystemAuditService:
    """
    Service for creating system audit events.

    Uses the tenant's system audit subject and schema (created during
    tenant initialization) to track all internal CRUD operations.
    Events are cryptographically chained for integrity.

    Important: This service expects the audit schema and subject to exist.
    They are created by TenantInitializationService during tenant setup.
    """

    def __init__(self, db: "AsyncSession") -> None:
        self.db = db
        self._subject_cache: dict[str, str] = {}  # tenant_id -> subject_id

    async def emit_audit_event(
        self,
        tenant_id: str,
        entity_type: str,
        action: AuditAction,
        entity_id: str,
        entity_data: dict[str, Any],
        actor_id: str | None = None,
        actor_type: ActorType = ActorType.SYSTEM,
        metadata: dict[str, Any] | None = None,
    ) -> "Event | None":
        """
        Emit a system audit event for an entity operation.

        Args:
            tenant_id: The tenant context
            entity_type: Type of entity (e.g., "subject", "workflow", "user")
            action: The action performed (created, updated, deleted, etc.)
            entity_id: ID of the affected entity
            entity_data: Snapshot of entity data (for create/update)
            actor_id: ID of the user/system that performed the action
            actor_type: Type of actor (user, system, external)
            metadata: Additional context about the operation

        Returns:
            The created audit Event, or None if audit infrastructure not available
        """
        from src.infrastructure.persistence.models.event import Event

        # Get the system audit subject for this tenant
        system_subject_id = await self._get_system_subject(tenant_id)
        if not system_subject_id:
            logger.warning(
                "Audit subject not found for tenant %s. "
                "Ensure tenant was properly initialized.",
                tenant_id,
            )
            return None

        # Build the audit payload following the schema
        event_time = utc_now()
        payload = self._build_audit_payload(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_id,
            actor_type=actor_type,
            entity_data=entity_data,
            metadata=metadata,
            timestamp=event_time,
        )

        # Get previous hash for chain integrity
        previous_hash = await self._get_latest_hash(system_subject_id)

        # Compute hash
        computed_hash = Event.compute_hash(
            subject_id=system_subject_id,
            event_type=SYSTEM_AUDIT_EVENT_TYPE,
            schema_version=SYSTEM_AUDIT_SCHEMA_VERSION,
            event_time=event_time,
            payload=payload,
            previous_hash=previous_hash,
        )

        # Create event
        event = Event(
            tenant_id=tenant_id,
            subject_id=system_subject_id,
            event_type=SYSTEM_AUDIT_EVENT_TYPE,
            schema_version=SYSTEM_AUDIT_SCHEMA_VERSION,
            event_time=event_time,
            payload=payload,
            previous_hash=previous_hash,
            hash=computed_hash,
        )

        self.db.add(event)
        # Note: Don't flush here - let the caller control transaction
        # The event will be committed with the main entity operation

        logger.debug(
            "Emitted audit event for %s.%s (entity_id: %s)",
            entity_type,
            action.value,
            entity_id,
        )

        return event

    async def _get_system_subject(self, tenant_id: str) -> str | None:
        """
        Get the system audit subject ID for a tenant.

        The subject should have been created during tenant initialization.
        Returns None if not found (indicates incomplete tenant setup).
        """
        from src.infrastructure.persistence.models.subject import Subject

        # Check cache first
        if tenant_id in self._subject_cache:
            return self._subject_cache[tenant_id]

        # Query for existing system subject using the reserved external_ref
        result = await self.db.execute(
            select(Subject.id).where(
                Subject.tenant_id == tenant_id,
                Subject.subject_type == SYSTEM_AUDIT_SUBJECT_TYPE,
                Subject.external_ref == SYSTEM_AUDIT_SUBJECT_REF,
            )
        )
        subject_id = result.scalar_one_or_none()

        if subject_id:
            self._subject_cache[tenant_id] = subject_id
            return subject_id

        return None

    async def _get_latest_hash(self, subject_id: str) -> str | None:
        """Get the hash of the most recent event for a subject."""
        from src.infrastructure.persistence.models.event import Event

        result = await self.db.execute(
            select(Event.hash)
            .where(Event.subject_id == subject_id)
            .order_by(Event.event_time.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def _build_audit_payload(
        self,
        entity_type: str,
        entity_id: str,
        action: AuditAction,
        actor_id: str | None,
        actor_type: ActorType,
        entity_data: dict[str, Any],
        metadata: dict[str, Any] | None,
        timestamp: datetime,
    ) -> dict[str, Any]:
        """
        Build the audit event payload following the system audit schema.

        The payload structure matches the JSON Schema defined in
        system_audit_schema.py for consistent validation.
        """
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action.value,
            "actor": {
                "type": actor_type.value,
                "id": actor_id,
            },
            "timestamp": timestamp.isoformat(),
            "entity_data": self._sanitize_entity_data(entity_data),
            "metadata": metadata or {},
        }

    @staticmethod
    def _sanitize_entity_data(data: dict[str, Any]) -> dict[str, Any]:
        """
        Sanitize entity data for storage in audit event.

        Removes sensitive fields and handles non-serializable types.
        """
        sensitive_fields = {
            "password",
            "hashed_password",
            "secret",
            "api_key",
            "token",
            "credentials",
            "credentials_encrypted",
            "client_secret",
            "client_secret_encrypted",
            "refresh_token",
            "access_token",
        }

        sanitized = {}
        for key, value in data.items():
            if key.lower() in sensitive_fields:
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, datetime):
                sanitized[key] = value.isoformat()
            elif hasattr(value, "__dict__") and not isinstance(value, dict):
                # Handle SQLAlchemy models or other objects
                sanitized[key] = str(value)
            else:
                sanitized[key] = value

        return sanitized


# Convenience functions for common audit operations
async def audit_entity_created(
    db: "AsyncSession",
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    entity_data: dict[str, Any],
    actor_id: str | None = None,
) -> "Event | None":
    """Convenience function to emit a created audit event."""
    service = SystemAuditService(db)
    return await service.emit_audit_event(
        tenant_id=tenant_id,
        entity_type=entity_type,
        action=AuditAction.CREATED,
        entity_id=entity_id,
        entity_data=entity_data,
        actor_id=actor_id,
    )


async def audit_entity_updated(
    db: "AsyncSession",
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    entity_data: dict[str, Any],
    actor_id: str | None = None,
    changes: dict[str, Any] | None = None,
) -> "Event | None":
    """Convenience function to emit an updated audit event."""
    service = SystemAuditService(db)
    return await service.emit_audit_event(
        tenant_id=tenant_id,
        entity_type=entity_type,
        action=AuditAction.UPDATED,
        entity_id=entity_id,
        entity_data=entity_data,
        actor_id=actor_id,
        metadata={"changes": changes} if changes else None,
    )


async def audit_entity_deleted(
    db: "AsyncSession",
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    entity_data: dict[str, Any],
    actor_id: str | None = None,
) -> "Event | None":
    """Convenience function to emit a deleted audit event."""
    service = SystemAuditService(db)
    return await service.emit_audit_event(
        tenant_id=tenant_id,
        entity_type=entity_type,
        action=AuditAction.DELETED,
        entity_id=entity_id,
        entity_data=entity_data,
        actor_id=actor_id,
    )
