from typing import Annotated
from fastapi import APIRouter, Depends, status, HTTPException
from models.tenant import Tenant
from api.deps import get_current_tenant, get_event_service_transactional, get_event_repo
from schemas.event import EventCreate, EventResponse
from services.event_service import EventService
from repositories.event_repo import EventRepository


router = APIRouter()


@router.post("/", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event: EventCreate,
    service: Annotated[EventService, Depends(get_event_service_transactional)],
    tenant: Tenant = Depends(get_current_tenant)
) -> EventResponse:
    """Create a new event with cryptographic chaining"""
    return await service.create_event(tenant.id, event)


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: str,
    repo: Annotated[EventRepository, Depends(get_event_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """Get a single event by ID"""
    event = await repo.get_by_id(event_id)

    if not event or event.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Event not found")

    return event


@router.get("/subject/{subject_id}", response_model=list[EventResponse])
async def get_subject_timeline(
    subject_id: str,
    repo: Annotated[EventRepository, Depends(get_event_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    skip: int = 0,
    limit: int = 100
):
    """Get all events for a subject (timeline)"""
    events = await repo.get_by_subject(subject_id, tenant.id, skip, limit)
    return events


@router.get("/", response_model=list[EventResponse])
async def list_events(
    repo: Annotated[EventRepository, Depends(get_event_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    skip: int = 0,
    limit: int = 100,
    *,
    event_type: str | None = None
):
    """List all events for the tenant, optionally filtered by event_type"""
    if event_type:
        return await repo.get_by_type(tenant.id, event_type, skip, limit)

    return await repo.get_by_tenant(tenant.id, skip, limit)