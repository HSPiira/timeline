from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.params import Query

from api.deps import (
    get_current_tenant,
    get_event_repo,
    get_event_service_transactional,
    require_permission,
)
from models.tenant import Tenant
from repositories.event_repo import EventRepository
from schemas.event import EventCreate, EventResponse
from schemas.verification import ChainVerificationResponse, EventVerificationResult
from services.event_service import EventService
from services.hash_service import HashService
from services.verification_service import ChainVerificationResult, VerificationService

router = APIRouter()


def _to_verification_response(
    result: "ChainVerificationResult",
) -> ChainVerificationResponse:
    """Convert service result to API response schema."""
    return ChainVerificationResponse(
        subject_id=result.subject_id,
        tenant_id=result.tenant_id,
        total_events=result.total_events,
        valid_events=result.valid_events,
        invalid_events=result.invalid_events,
        is_chain_valid=result.is_chain_valid,
        verified_at=result.verified_at,
        event_results=[
            EventVerificationResult(
                event_id=er.event_id,
                event_type=er.event_type,
                event_time=er.event_time,
                sequence=er.sequence,
                is_valid=er.is_valid,
                error_type=er.error_type,
                error_message=er.error_message,
                expected_hash=er.expected_hash,
                actual_hash=er.actual_hash,
            )
            for er in result.event_results
        ],
    )


@router.post("/", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event: EventCreate,
    service: Annotated[EventService, Depends(get_event_service_transactional)],
    tenant: Tenant = Depends(get_current_tenant),
) -> EventResponse:
    """Create a new event with cryptographic chaining"""
    return await service.create_event(tenant.id, event)


@router.get("/subject/{subject_id}", response_model=list[EventResponse])
async def get_subject_timeline(
    subject_id: str,
    repo: Annotated[EventRepository, Depends(get_event_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int, Query(ge=1, le=1000, description="Max records to return")
    ] = 100,
):
    """Get all events for a subject (timeline)"""
    events = await repo.get_by_subject(subject_id, tenant.id, skip, limit)
    return events


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: str,
    repo: Annotated[EventRepository, Depends(get_event_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    """Get a single event by ID"""
    event = await repo.get_by_id_and_tenant(event_id, tenant.id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.get("/", response_model=list[EventResponse])
async def list_events(
    repo: Annotated[EventRepository, Depends(get_event_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int, Query(ge=1, le=1000, description="Max records to return")
    ] = 100,
    event_type: Annotated[
        str | None,
        Query(
            pattern=r"^[a-z0-9_]+$",
            description="Event type filter (alphanumeric and underscores only)",
        ),
    ] = None,
):
    """List all events for the tenant, optionally filtered by event_type"""
    if event_type:
        return await repo.get_by_type(tenant.id, event_type, skip, limit)

    return await repo.get_by_tenant(tenant.id, skip, limit)


@router.get(
    "/verify/tenant/all",
    response_model=ChainVerificationResponse,
    dependencies=[Depends(require_permission("event", "read"))],
)
async def verify_tenant_chains(
    repo: Annotated[EventRepository, Depends(get_event_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    limit: Annotated[
        int, Query(ge=1, le=10000, description="Max events to verify")
    ] = 1000,
):
    """
    Verify cryptographic integrity of all event chains for current tenant.

    Validates all events across all subjects for tenant.
    Use limit parameter to control scope (default 1000 events).

    Returns aggregated verification report.
    """
    verification_service = VerificationService(
        event_repo=repo, hash_service=HashService()
    )

    result = await verification_service.verify_tenant_chains(tenant.id, limit=limit)
    return _to_verification_response(result)


@router.get(
    "/verify/{subject_id}",
    response_model=ChainVerificationResponse,
    dependencies=[Depends(require_permission("event", "read"))],
)
async def verify_subject_chain(
    subject_id: str,
    repo: Annotated[EventRepository, Depends(get_event_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    """
    Verify cryptographic integrity of event chain for a subject.

    Checks:
    - Hash integrity: recomputed hash matches stored hash
    - Chain continuity: previous_hash links are valid
    - Tamper detection: identifies any modifications

    Returns detailed verification report with per-event status.
    """
    verification_service = VerificationService(
        event_repo=repo, hash_service=HashService()
    )

    result = await verification_service.verify_subject_chain(subject_id, tenant.id)
    return _to_verification_response(result)
