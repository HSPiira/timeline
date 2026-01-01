from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.params import Query
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from src.presentation.api.dependencies import (
    get_current_tenant,
    get_current_user,
    get_event_repo,
    get_event_schema_repo,
    get_event_schema_repo_transactional,
)
from src.infrastructure.persistence.models.event_schema import EventSchema
from src.infrastructure.persistence.models.tenant import Tenant
from src.infrastructure.persistence.repositories.event_repo import EventRepository
from src.infrastructure.persistence.repositories.event_schema_repo import EventSchemaRepository
from src.presentation.api.v1.schemas.event_schema import (
    EventSchemaCreate,
    EventSchemaResponse,
    EventSchemaUpdate,
)
from src.presentation.api.v1.schemas.token import TokenPayload

router = APIRouter()

T = TypeVar("T", bound=BaseModel)


def validate(model: type[T], obj: object) -> T:
    """Helper to validate Pydantic models with proper type inference"""
    validated = model.model_validate(obj)
    assert isinstance(validated, model)
    return validated


@router.post(
    "/", response_model=EventSchemaResponse, status_code=status.HTTP_201_CREATED
)
async def create_event_schema(
    data: EventSchemaCreate,
    repo: Annotated[
        EventSchemaRepository, Depends(get_event_schema_repo_transactional)
    ],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
) -> EventSchemaResponse:
    """
    Create a new event schema version for the tenant.

    The version number is auto-incremented based on existing versions for this event_type.
    New schemas are automatically activated, and the previous active schema is deactivated.

    Note on schema activation:
    - Deactivating previous schemas ensures new events use the latest schema for data quality
    - Clients that cached the old active schema will get a validation error and must retry
    - This is transactional, so race conditions are minimized
    - Events can only be created with active schemas to maintain data integrity
    """
    try:
        # Auto-increment version number
        next_version = await repo.get_next_version(tenant.id, data.event_type)

        # Deactivate the currently active schema (if any)
        previous_active = await repo.get_active_schema(tenant.id, data.event_type)
        if previous_active:
            previous_active.is_active = False
            await repo.update(previous_active)

        # Create new schema and automatically activate it
        schema = EventSchema(
            tenant_id=tenant.id,
            event_type=data.event_type,
            schema_definition=data.schema_definition,
            version=next_version,
            is_active=True,  # Auto-activate new schema
            created_by=current_user.sub,  # User ID from JWT token
        )
        created_schema = await repo.create(schema)
        return validate(EventSchemaResponse, created_schema)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Schema for event type '{data.event_type}' already exists (concurrent creation conflict)",
        ) from None


@router.get("/", response_model=list[EventSchemaResponse])
async def list_event_schemas(
    repo: Annotated[EventSchemaRepository, Depends(get_event_schema_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int, Query(ge=1, le=1000, description="Max records to return")
    ] = 100,
) -> list[EventSchemaResponse]:
    """List all event schemas for the tenant"""
    schemas = await repo.get_all_for_tenant(tenant.id, skip, limit)
    return [validate(EventSchemaResponse, schema) for schema in schemas]


@router.get("/event-type/{event_type}", response_model=list[EventSchemaResponse])
async def get_schemas_for_event_type(
    event_type: str,
    repo: Annotated[EventSchemaRepository, Depends(get_event_schema_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
) -> list[EventSchemaResponse]:
    """Get all schema versions for a specific event type"""
    schemas = await repo.get_all_for_event_type(tenant.id, event_type)
    if not schemas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No schemas found for event type '{event_type}'",
        )
    return [validate(EventSchemaResponse, schema) for schema in schemas]


@router.get("/event-type/{event_type}/active", response_model=EventSchemaResponse)
async def get_active_schema(
    event_type: str,
    repo: Annotated[EventSchemaRepository, Depends(get_event_schema_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
) -> EventSchemaResponse:
    """Get the active schema for a specific event type"""
    schema = await repo.get_active_schema(tenant.id, event_type)
    if not schema:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active schema found for event type '{event_type}'",
        )
    return validate(EventSchemaResponse, schema)


@router.get(
    "/event-type/{event_type}/version/{version}", response_model=EventSchemaResponse
)
async def get_schema_by_version(
    event_type: str,
    version: int,
    repo: Annotated[EventSchemaRepository, Depends(get_event_schema_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
) -> EventSchemaResponse:
    """Get a specific schema version for an event type (used for event verification)"""
    schema = await repo.get_by_version(tenant.id, event_type, version)
    if not schema:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schema version {version} not found for event type '{event_type}'",
        )
    return validate(EventSchemaResponse, schema)


@router.get("/{schema_id}", response_model=EventSchemaResponse)
async def get_event_schema(
    schema_id: str,
    repo: Annotated[EventSchemaRepository, Depends(get_event_schema_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
) -> EventSchemaResponse:
    """Get a specific event schema by ID"""
    schema = await repo.get_by_id(schema_id)
    if not schema or schema.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Schema not found"
        )
    return validate(EventSchemaResponse, schema)


@router.patch("/{schema_id}", response_model=EventSchemaResponse)
async def update_event_schema(
    schema_id: str,
    data: EventSchemaUpdate,
    repo: Annotated[
        EventSchemaRepository, Depends(get_event_schema_repo_transactional)
    ],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
) -> EventSchemaResponse:
    """
    Update an event schema (activate/deactivate only).

    Schema definitions are immutable - only is_active can be changed.
    """
    schema = await repo.get_by_id(schema_id)
    if not schema or schema.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Schema not found"
        )

    if data.is_active is not None:
        schema.is_active = data.is_active
        updated_schema = await repo.update(schema)
        return validate(EventSchemaResponse, updated_schema)

    return validate(EventSchemaResponse, schema)


@router.delete("/{schema_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event_schema(
    schema_id: str,
    schema_repo: Annotated[
        EventSchemaRepository, Depends(get_event_schema_repo_transactional)
    ],
    event_repo: Annotated[EventRepository, Depends(get_event_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
) -> None:
    """
    Delete an event schema.

    Deletion is only allowed if no events reference this schema version.
    If events exist, the schema should be deactivated instead.
    """
    schema = await schema_repo.get_by_id(schema_id)
    if not schema or schema.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Schema not found"
        )

    # Check if any events reference this schema version
    event_count = await event_repo.count_by_schema_version(
        tenant.id, schema.event_type, schema.version
    )

    if event_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete schema: {event_count} event(s) reference this schema version. "
            f"Deactivate the schema instead using PATCH /{schema_id} with is_active=false",
        )

    # Safe to delete - no events reference this schema
    await schema_repo.delete(schema)
