from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.subject import Subject
from repositories.base import BaseRepository
from typing import List, Optional


class SubjectRepository(BaseRepository[Subject]):
    """Repository for Subject entity following LSP"""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Subject)

    async def get_by_tenant(self, tenant_id: str, skip: int = 0, limit: int = 100) -> List[Subject]:
        """Get all subjects for a tenant with pagination"""
        result = await self.db.execute(
            select(Subject)
            .where(Subject.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_type(self, tenant_id: str, subject_type: str, skip: int = 0, limit: int = 100) -> List[Subject]:
        """Get all subjects of a specific type for a tenant with pagination"""
        result = await self.db.execute(
            select(Subject)
            .where(
                Subject.tenant_id == tenant_id,
                Subject.subject_type == subject_type
            )
            .order_by(Subject.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_external_ref(self, tenant_id: str, external_ref: str) -> Optional[Subject]:
        """Get subject by external reference"""
        result = await self.db.execute(
            select(Subject)
            .where(
                Subject.tenant_id == tenant_id,
                Subject.external_ref == external_ref
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_and_tenant(self, subject_id: str, tenant_id: str) -> Optional[Subject]:
        """Get subject by ID and verify it belongs to the tenant"""
        result = await self.db.execute(
            select(Subject)
            .where(
                Subject.id == subject_id,
                Subject.tenant_id == tenant_id
            )
        )
        return result.scalar_one_or_none()
