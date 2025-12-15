from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from models.document import Document
from repositories.base import BaseRepository
from typing import List, Optional


class DocumentRepository(BaseRepository[Document]):
    """Repository for Document entity following LSP"""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Document)

    async def get_by_subject(self, subject_id: str, tenant_id: str, include_deleted: bool = False) -> List[Document]:
        """Get all documents for a subject within a tenant"""
        query = select(Document).where(
            and_(
                Document.subject_id == subject_id,
                Document.tenant_id == tenant_id
            )
        )

        if not include_deleted:
            query = query.where(Document.deleted_at.is_(None))

        query = query.order_by(Document.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_event(self, event_id: str, tenant_id: str) -> List[Document]:
        """Get all documents linked to an event within a tenant"""
        result = await self.db.execute(
            select(Document)
            .where(
                and_(
                    Document.event_id == event_id,
                    Document.tenant_id == tenant_id,
                    Document.deleted_at.is_(None)
                )
            )
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_checksum(self, tenant_id: str, checksum: str) -> Optional[Document]:
        """Check if document with same content already exists"""
        result = await self.db.execute(
            select(Document)
            .where(
                and_(
                    Document.tenant_id == tenant_id,
                    Document.checksum == checksum,
                    Document.deleted_at.is_(None)
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_versions(self, document_id: str, tenant_id: str) -> List[Document]:
        """Get all versions of a document within a tenant"""
        result = await self.db.execute(
            select(Document)
            .where(
                and_(
                    Document.parent_document_id == document_id,
                    Document.tenant_id == tenant_id
                )
            )
            .order_by(Document.version.asc())
        )
        return list(result.scalars().all())

    async def soft_delete(self, document_id: str) -> Optional[Document]:
        """Soft delete a document"""
        from datetime import datetime, timezone

        document = await self.get_by_id(document_id)
        if document:
            document.deleted_at = datetime.now(timezone.utc)
            return await self.update(document)
        return None
