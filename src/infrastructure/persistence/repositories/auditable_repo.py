"""
Auditable Repository base class for automatic system event tracking.

Extends BaseRepository with hooks that automatically emit audit events
for all CRUD operations on entities that should be tracked.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, TypeVar

from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.repositories.base import BaseRepository
from src.shared.enums import AuditAction

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.application.services.system_audit_service import SystemAuditService

ModelType = TypeVar("ModelType", bound=Base)


class AuditableRepository(BaseRepository[ModelType]):
    """
    Repository base class with automatic audit event emission.

    Auditing is ENABLED BY DEFAULT. Audit events are automatically created
    for all CRUD operations without any additional configuration.

    Subclasses must implement:
    - _get_entity_type(): Return the entity type string (e.g., "subject")
    - _get_tenant_id(obj): Extract tenant_id from the entity
    - _serialize_for_audit(obj): Convert entity to dict for audit payload

    Optionally override:
    - _get_actor_id(): Return the current actor ID (user performing action)
    - _should_audit(): Return False to skip auditing for certain operations
    """

    def __init__(
        self,
        db: "AsyncSession",
        model: type[ModelType],
        audit_service: "SystemAuditService | None" = None,
        *,
        enable_audit: bool = True,
    ):
        super().__init__(db, model)
        self._audit_service = audit_service
        self._audit_enabled = enable_audit

    @property
    def audit_service(self) -> "SystemAuditService | None":
        """Get the audit service, lazily initializing if needed."""
        if self._audit_service is None and self._audit_enabled:
            from src.application.services.system_audit_service import SystemAuditService
            self._audit_service = SystemAuditService(self.db)
        return self._audit_service

    def enable_auditing(self, audit_service: "SystemAuditService | None" = None) -> None:
        """Enable auditing for this repository instance."""
        self._audit_enabled = True
        if audit_service is not None:
            self._audit_service = audit_service

    def disable_auditing(self) -> None:
        """Disable auditing for this repository instance."""
        self._audit_enabled = False

    # Abstract methods that subclasses must implement
    @abstractmethod
    def _get_entity_type(self) -> str:
        """Return the entity type string for audit events (e.g., 'subject')."""
        ...

    @abstractmethod
    def _get_tenant_id(self, obj: ModelType) -> str:
        """Extract tenant_id from the entity."""
        ...

    @abstractmethod
    def _serialize_for_audit(self, obj: ModelType) -> dict[str, Any]:
        """Convert entity to dict for audit payload."""
        ...

    # Optional overrides
    def _get_actor_id(self) -> str | None:
        """Return the current actor ID. Override to provide user context."""
        return None

    def _should_audit(self, action: AuditAction, obj: ModelType) -> bool:
        """Return whether this operation should be audited. Override to filter."""
        return True

    # Audit event emission
    async def _emit_audit_event(
        self,
        action: AuditAction,
        obj: ModelType,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Emit an audit event for the given action and entity."""
        if not self._audit_enabled or not self._should_audit(action, obj):
            return

        service = self.audit_service
        if service is None:
            return

        try:
            await service.emit_audit_event(
                tenant_id=self._get_tenant_id(obj),
                entity_type=self._get_entity_type(),
                action=action,
                entity_id=getattr(obj, "id", str(obj)),
                entity_data=self._serialize_for_audit(obj),
                actor_id=self._get_actor_id(),
                metadata=metadata,
            )
        except Exception as e:
            # Log but don't fail the operation if auditing fails
            from src.shared.telemetry.logging import get_logger
            logger = get_logger(__name__)
            logger.warning(
                "Failed to emit audit event for %s.%s: %s",
                self._get_entity_type(),
                action.value,
                str(e),
            )

    # Override hooks from BaseRepository
    async def _on_after_create(self, obj: ModelType) -> None:
        """Emit created audit event after entity creation."""
        await super()._on_after_create(obj)
        await self._emit_audit_event(AuditAction.CREATED, obj)

    async def _on_after_update(self, obj: ModelType) -> None:
        """Emit updated audit event after entity update."""
        await super()._on_after_update(obj)
        await self._emit_audit_event(AuditAction.UPDATED, obj)

    async def _on_before_delete(self, obj: ModelType) -> None:
        """Emit deleted audit event before entity deletion."""
        await super()._on_before_delete(obj)
        await self._emit_audit_event(AuditAction.DELETED, obj)

    # Convenience methods for custom audit events
    async def emit_custom_audit(
        self,
        obj: ModelType,
        action: AuditAction,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Emit a custom audit event (e.g., activated, deactivated)."""
        await self._emit_audit_event(action, obj, metadata)
