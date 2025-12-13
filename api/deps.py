from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.tenant import Tenant
from repositories.tenant_repo import TenantRepository
from repositories.event_repo import EventRepository
from repositories.subject_repo import SubjectRepository
from repositories.document_repo import DocumentRepository
from services.event_service import EventService
from services.hash_service import HashService


async def get_current_tenant(
    x_tenant_id: str = Header(..., alias="x-tenant-id"),
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    tenant = await TenantRepository(db).get_by_id(x_tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


async def get_event_service(
    db: AsyncSession = Depends(get_db)
) -> EventService:
    """Event service dependency"""
    return EventService(
        event_repo=EventRepository(db),
        hash_service=HashService()
    )


async def get_subject_repo(
    db: AsyncSession = Depends(get_db)
) -> SubjectRepository:
    """Subject repository dependency"""
    return SubjectRepository(db)


async def get_tenant_repo(
    db: AsyncSession = Depends(get_db)
) -> TenantRepository:
    """Tenant repository dependency"""
    return TenantRepository(db)


async def get_document_repo(
    db: AsyncSession = Depends(get_db)
) -> DocumentRepository:
    """Document repository dependency"""
    return DocumentRepository(db)