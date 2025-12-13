from typing_extensions import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from models.tenant import Tenant
from api.deps import get_db, get_current_tenant
from schemas.event import EventCreate
from services.event_service import EventService


router = APIRouter()


@router.post("/")
async def create_event(
    event: EventCreate,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    service: Annotated[EventService, Depends(get_event_service)]
):
    return await service.create_event(tenant.id, event)