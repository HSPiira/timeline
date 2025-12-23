from typing import Annotated
from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.params import Query
from sqlalchemy.exc import IntegrityError

from api.deps import (
    get_event_schema_repo,
    get_event_schema_repo_transactional,
    get_current_tenant
)
from models.tenant import Tenant
from models.event_schema import EventSchema 
from schemas.event_schema import EventSchemaCreate, EventSchemaUpdate, EventSchemaResponse
from repositories.event_schema_repo import EventSchemaRepository


router = APIRouter()


@router.post("/", response_model=EventSchemaResponse, status_code=status.HTTP_201_CREATED)
async def create_event_schema(
    data: EventSchemaCreate,
    repo: Annotated[EventSchemaRepository, Depends(get_event_schema_repo_transactional)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
) -> EventSchemaResponse:
    """Create a new event schema for the tenant"""
    try:
        schema = EventSchema(
            tenant_id=tenant.id,
            event_type=data.event_type,
            schema_definition=data.schema_definition,
            version=data.version,
            is_active=True
        )
        created_schema = await repo.create(schema)
        return EventSchemaResponse.model_validate(created_schema)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Schema version {data.version} for event type '{data.event_type}' already exists"
        ) from None


@router.get("/", response_model=list[EventSchemaResponse])
async def list_event_schemas(
    repo: Annotated[EventSchemaRepository, Depends(get_event_schema_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return")
) -> list[EventSchemaResponse]:
    """List all event schemas for the tenant"""
    schemas = await repo.get_all_for_tenant(tenant.id, skip, limit)
    return [EventSchemaResponse.model_validate(schema) for schema in schemas]


@router.get("/event-type/{event_type}", response_model=list[EventSchemaResponse])
async def get_schemas_for_event_type(
    event_type: str,
    repo: Annotated[EventSchemaRepository, Depends(get_event_schema_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
) -> list[EventSchemaResponse]:
    """Get all schema versions for a specific event type"""
    schemas = await repo.get_all_for_event_type(tenant.id, event_type)
    if not schemas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No schemas found for event type '{event_type}'"
        )
    return [EventSchemaResponse.model_validate(schema) for schema in schemas]


@router.get("/event-type/{event_type}/active", response_model=EventSchemaResponse)
async def get_active_schema(
    event_type: str,
    repo: Annotated[EventSchemaRepository, Depends(get_event_schema_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
) -> EventSchemaResponse:
    """Get the active schema for a specific event type"""
    schema = await repo.get_active_schema(tenant.id, event_type)
    if not schema:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active schema found for event type '{event_type}'"
        )
    return EventSchemaResponse.model_validate(schema)


@router.get("/{schema_id}", response_model=EventSchemaResponse)
async def get_event_schema(
    schema_id: str,
    repo: Annotated[EventSchemaRepository, Depends(get_event_schema_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
) -> EventSchemaResponse:
    """Get a specific event schema by ID"""
    schema = await repo.get_by_id(schema_id)
    if not schema or schema.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schema not found"
        )
    return EventSchemaResponse.model_validate(schema)


@router.patch("/{schema_id}", response_model=EventSchemaResponse)
async def update_event_schema(
    schema_id: str,
    data: EventSchemaUpdate,
    repo: Annotated[EventSchemaRepository, Depends(get_event_schema_repo_transactional)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
) -> EventSchemaResponse:
    """Update an event schema (activate/deactivate)"""
    schema = await repo.get_by_id(schema_id)
    if not schema or schema.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schema not found"
        )

    if data.is_active is not None:
        schema.is_active = data.is_active  
        updated_schema = await repo.update(schema)  
        return EventSchemaResponse.model_validate(updated_schema)

    return EventSchemaResponse.model_validate(schema)


@router.patch("/{schema_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event_schema(
    schema_id: str,
    repo: Annotated[EventSchemaRepository, Depends(get_event_schema_repo_transactional)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """Delete an event schema (soft delete by deactivating)"""
    schema = await repo.get_by_id(schema_id)
    if not schema or schema.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schema not found"
        )

    await repo.deactivate_schema(schema_id)
