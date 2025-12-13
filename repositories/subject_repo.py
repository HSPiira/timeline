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

    async def get_by_type(self, tenant_id: str, subject_type: str) -> List[Subject]:
        """Get all subjects of a specific type for a tenant"""
        result = await self.db.execute(
            select(Subject)
            .where(
                Subject.tenant_id == tenant_id,
                Subject.subject_type == subject_type
            )
            .order_by(Subject.created_at.desc())
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
