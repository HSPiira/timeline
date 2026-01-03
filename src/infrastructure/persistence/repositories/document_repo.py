from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.models.document import Document
from src.infrastructure.persistence.repositories.auditable_repo import AuditableRepository
from src.shared.enums import AuditAction

if TYPE_CHECKING:
    from src.application.services.system_audit_service import SystemAuditService


class DocumentRepository(AuditableRepository[Document]):
    """Repository for Document entity with automatic audit tracking."""

    def __init__(
        self,
        db: AsyncSession,
        audit_service: "SystemAuditService | None" = None,
        *,
        enable_audit: bool = True,
    ):
        super().__init__(db, Document, audit_service, enable_audit=enable_audit)

    # Auditable implementation
    def _get_entity_type(self) -> str:
        return "document"

    def _get_tenant_id(self, obj: Document) -> str:
        return obj.tenant_id

    def _serialize_for_audit(self, obj: Document) -> dict[str, Any]:
        return {
            "id": obj.id,
            "filename": obj.filename,
            "original_filename": obj.original_filename,
            "content_type": obj.content_type,
            "size_bytes": obj.size_bytes,
            "subject_id": obj.subject_id,
            "event_id": obj.event_id,
            "version": obj.version,
            # Note: storage_path and checksum excluded for security
        }

    async def get_by_subject(
        self, subject_id: str, tenant_id: str, include_deleted: bool = False
    ) -> list[Document]:
        """Get all documents for a subject within a tenant"""
        query = select(Document).where(
            and_(Document.subject_id == subject_id, Document.tenant_id == tenant_id)
        )

        if not include_deleted:
            query = query.where(Document.deleted_at.is_(None))

        query = query.order_by(Document.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_event(self, event_id: str, tenant_id: str) -> list[Document]:
        """Get all documents linked to an event within a tenant"""
        result = await self.db.execute(
            select(Document)
            .where(
                and_(
                    Document.event_id == event_id,
                    Document.tenant_id == tenant_id,
                    Document.deleted_at.is_(None),
                )
            )
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_checksum(self, tenant_id: str, checksum: str) -> Document | None:
        """Check if document with same content already exists"""
        result = await self.db.execute(
            select(Document).where(
                and_(
                    Document.tenant_id == tenant_id,
                    Document.checksum == checksum,
                    Document.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_versions(self, document_id: str, tenant_id: str) -> list[Document]:
        """Get all versions of a document within a tenant"""
        result = await self.db.execute(
            select(Document)
            .where(
                and_(
                    Document.parent_document_id == document_id,
                    Document.tenant_id == tenant_id,
                )
            )
            .order_by(Document.version.asc())
        )
        return list(result.scalars().all())

    async def soft_delete(self, document_id: str) -> Document | None:
        """Soft delete a document with audit event."""
        document = await self.get_by_id(document_id)
        if document:
            document.deleted_at = datetime.now(UTC)
            updated = await self.update(document)
            await self.emit_custom_audit(updated, AuditAction.DELETED)
            return updated
        return None
