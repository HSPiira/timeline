from typing import Annotated, List
from fastapi import APIRouter, Depends, status, HTTPException
from models.tenant import Tenant
from api.deps import get_current_tenant, get_document_repo
from schemas.document import DocumentCreate, DocumentUpdate, DocumentResponse
from repositories.document_repo import DocumentRepository


router = APIRouter()


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    data: DocumentCreate,
    repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """Create a new document"""
    from models.document import Document

    # Check for duplicate (same checksum)
    existing = await repo.get_by_checksum(tenant.id, data.checksum)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Document with same content already exists (ID: {existing.id})"
        )

    document = Document(
        tenant_id=tenant.id,
        subject_id=data.subject_id,
        event_id=data.event_id,
        document_type=data.document_type,
        filename=data.filename,
        original_filename=data.original_filename,
        mime_type=data.mime_type,
        file_size=data.file_size,
        checksum=data.checksum,
        storage_ref=data.storage_ref,
        created_by=data.created_by
    )

    created = await repo.create(document)
    return created


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """Get a document by ID"""
    document = await repo.get_by_id(document_id)

    if not document or document.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.deleted_at:
        raise HTTPException(status_code=410, detail="Document has been deleted")

    return document


@router.get("/subject/{subject_id}", response_model=List[DocumentResponse])
async def get_documents_by_subject(
    subject_id: str,
    repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    include_deleted: bool = False
):
    """Get all documents for a subject"""
    documents = await repo.get_by_subject(subject_id, include_deleted)

    # Filter by tenant
    return [doc for doc in documents if doc.tenant_id == tenant.id]


@router.get("/event/{event_id}", response_model=List[DocumentResponse])
async def get_documents_by_event(
    event_id: str,
    repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """Get all documents for an event"""
    documents = await repo.get_by_event(event_id)

    # Filter by tenant
    return [doc for doc in documents if doc.tenant_id == tenant.id]


@router.get("/{document_id}/versions", response_model=List[DocumentResponse])
async def get_document_versions(
    document_id: str,
    repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """Get all versions of a document"""
    # First check if the document exists and belongs to tenant
    document = await repo.get_by_id(document_id)

    if not document or document.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Document not found")

    versions = await repo.get_versions(document_id)
    return versions


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    data: DocumentUpdate,
    repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """Update document metadata"""
    document = await repo.get_by_id(document_id)

    if not document or document.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.deleted_at:
        raise HTTPException(status_code=410, detail="Document has been deleted")

    if data.document_type is not None:
        document.document_type = data.document_type

    updated = await repo.update(document)
    return updated


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """Soft delete a document"""
    document = await repo.get_by_id(document_id)

    if not document or document.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.deleted_at:
        raise HTTPException(status_code=410, detail="Document already deleted")

    await repo.soft_delete(document_id)
