from typing import Annotated
from fastapi import APIRouter, Depends, status
from models.tenant import Tenant
from api.deps import get_current_tenant, get_event_service
from schemas.event import EventCreate, EventResponse
from services.event_service import EventService


router = APIRouter()


@router.post("/", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event: EventCreate,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    service: Annotated[EventService, Depends(get_event_service)]
):
    """Create a new event with cryptographic chaining"""
    return await service.create_event(tenant.id, event)