from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from core.database import get_db
from models.tenant import Tenant
from repositories.tenant_repo import TenantRepository
from repositories.event_repo import EventRepository
from services.event_service import EventService
from services.hash_service import HashService


async def get_current_tenant(
    x_tenant_id: Annotated[str, Header()],
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