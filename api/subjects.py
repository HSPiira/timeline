from typing import Annotated, List
from fastapi import APIRouter, Depends, status, HTTPException
from models.tenant import Tenant
from api.deps import get_current_tenant, get_subject_repo, get_subject_repo_transactional
from schemas.subject import SubjectCreate, SubjectUpdate, SubjectResponse
from repositories.subject_repo import SubjectRepository


router = APIRouter()


@router.post("/", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
async def create_subject(
    data: SubjectCreate,
    repo: Annotated[SubjectRepository, Depends(get_subject_repo_transactional)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """Create a new subject"""
    from models.subject import Subject

    subject = Subject(
        tenant_id=tenant.id,
        subject_type=data.subject_type,
        external_ref=data.external_ref
    )

    created = await repo.create(subject)
    return created


@router.get("/{subject_id}", response_model=SubjectResponse)
async def get_subject(
    subject_id: str,
    repo: Annotated[SubjectRepository, Depends(get_subject_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """Get a subject by ID"""
    subject = await repo.get_by_id(subject_id)

    if not subject or subject.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Subject not found")

    return subject


@router.get("/", response_model=List[SubjectResponse])
async def list_subjects(
    repo: Annotated[SubjectRepository, Depends(get_subject_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    skip: int = 0,
    limit: int = 100,
    subject_type: str | None = None
):
    """List all subjects for the tenant"""
    if subject_type:
        return await repo.get_by_type(tenant.id, subject_type, skip, limit)

    return await repo.get_by_tenant(tenant.id, skip, limit)


@router.put("/{subject_id}", response_model=SubjectResponse)
async def update_subject(
    subject_id: str,
    data: SubjectUpdate,
    repo: Annotated[SubjectRepository, Depends(get_subject_repo_transactional)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """Update a subject"""
    subject = await repo.get_by_id(subject_id)

    if not subject or subject.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Subject not found")

    if data.external_ref is not None:
        subject.external_ref = data.external_ref

    updated = await repo.update(subject)
    return updated


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject(
    subject_id: str,
    repo: Annotated[SubjectRepository, Depends(get_subject_repo_transactional)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """Delete a subject"""
    subject = await repo.get_by_id(subject_id)

    if not subject or subject.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Subject not found")

    await repo.delete(subject)
