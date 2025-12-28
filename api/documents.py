from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from api.deps import (
    get_current_tenant,
    get_document_repo,
    get_document_repo_transactional,
    get_document_service_transactional,
    get_event_repo,
    get_subject_repo,
    require_permission,
)
from core.config import get_settings
from core.exceptions import (
    StorageChecksumMismatchError,
    StorageNotFoundError,
    StorageUploadError,
)
from core.logging import get_logger
from models.tenant import Tenant
from repositories.document_repo import DocumentRepository
from repositories.event_repo import EventRepository
from repositories.subject_repo import SubjectRepository
from schemas.document import DocumentCreate, DocumentResponse, DocumentUpdate
from schemas.storage import DocumentUploadResponse
from services.document_service import DocumentService

logger = get_logger(__name__)


router = APIRouter()


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("document", "create"))],
)
async def upload_document(
    doc_service: Annotated[
        DocumentService, Depends(get_document_service_transactional)
    ],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    file: UploadFile = File(..., description="File to upload"),
    subject_id: str = Form(..., description="Subject ID this document belongs to"),
    document_type: str = Form(
        ..., description="Document type (invoice, contract, etc.)"
    ),
    event_id: str
    | None = Form(None, description="Optional event ID to link document to"),
):
    """
    Upload a document file with metadata.

    Security:
    - Requires 'document:create' permission
    - Validates file size against max_upload_size config
    - Validates MIME type against allowed_mime_types config
    - Validates subject_id belongs to current tenant
    - Computes SHA-256 checksum for integrity
    - Prevents duplicate uploads (same checksum)

    Storage:
    - Files stored at: tenants/{tenant_code}/documents/{document_id}/v{version}/{filename}
    - Atomic writes with path traversal protection
    - Metadata stored in database, binary data in storage
    """
    settings = get_settings()

    # Validate file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset to beginning

    if file_size > settings.max_upload_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size {file_size} bytes exceeds maximum allowed size of {settings.max_upload_size} bytes",
        )

    # Validate MIME type (if not wildcard)
    if settings.allowed_mime_types != "*/*":
        allowed_types = [t.strip() for t in settings.allowed_mime_types.split(",")]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"MIME type '{file.content_type}' not allowed. Allowed types: {settings.allowed_mime_types}",
            )

    # Validate required file metadata
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must have a filename",
        )
    if not file.content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must have a content type",
        )

    try:
        # Upload document through service layer
        document = await doc_service.upload_document(
            tenant_id=tenant.id,
            subject_id=subject_id,
            event_id=event_id,
            file_data=file.file,
            filename=file.filename,
            original_filename=file.filename,
            mime_type=file.content_type,
            document_type=document_type,
            created_by=None,  # TODO: Get from authenticated user when user context available
        )

        return DocumentUploadResponse(
            id=document.id,
            subject_id=document.subject_id,
            event_id=document.event_id,
            document_type=document.document_type,
            filename=document.filename,
            original_filename=document.original_filename,
            storage_ref=document.storage_ref,
            checksum=document.checksum,
            file_size=document.file_size,
            mime_type=document.mime_type,
            version=document.version,
            is_latest_version=document.is_latest_version,
            created_at=document.created_at,
        )

    except ValueError as e:
        # Business logic errors (duplicate, invalid subject, etc.)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    except StorageChecksumMismatchError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File integrity check failed: {e!s}",
        ) from e
    except StorageUploadError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage upload failed: {e!s}",
        ) from e
    except (OSError, RuntimeError) as e:
        # Catch specific exceptions that may occur during upload
        logger.error(f"Unexpected error during document upload: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error during upload",
        ) from e


@router.get(
    "/{document_id}/download",
    dependencies=[Depends(require_permission("document", "read"))],
)
async def download_document(
    document_id: str,
    doc_service: Annotated[
        DocumentService, Depends(get_document_service_transactional)
    ],
    repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    """
    Download a document file.

    Security:
    - Requires 'document:read' permission
    - Validates document belongs to current tenant
    - Streams file content (memory efficient)

    Returns:
    - StreamingResponse with original filename and MIME type
    - Content-Disposition header for browser download
    """
    # Get document metadata and validate tenant access
    document = await repo.get_by_id(document_id)

    if not document or document.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    if document.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="Document has been deleted"
        )

    try:
        # Stream file from storage
        file_stream = await doc_service.download_document_stream(document)

        return StreamingResponse(
            file_stream,
            media_type=document.mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{document.original_filename}"',
                "Content-Length": str(document.file_size),
            },
        )

    except StorageNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found in storage",
        ) from None
    except (OSError, RuntimeError) as e:
        logger.error(
            f"Error downloading document {document_id}: {e}",
            exc_info=True,
            extra={"document_id": document_id, "tenant_id": tenant.id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error downloading document",
        ) from e


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    data: DocumentCreate,
    repo: Annotated[DocumentRepository, Depends(get_document_repo_transactional)],
    subject_repo: Annotated[SubjectRepository, Depends(get_subject_repo)],
    event_repo: Annotated[EventRepository, Depends(get_event_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    """
    Create a new document.

    Security: Validates that subject_id and event_id (if provided) belong to
    the current tenant to prevent cross-tenant reference attacks.
    """
    from models.document import Document

    # Validate subject_id belongs to tenant (prevents cross-tenant reference)
    subject = await subject_repo.get_by_id_and_tenant(data.subject_id, tenant.id)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject '{data.subject_id}' not found or does not belong to your tenant",
        )

    # Validate event_id belongs to tenant if provided (prevents cross-tenant reference)
    if data.event_id:
        event = await event_repo.get_by_id_and_tenant(data.event_id, tenant.id)
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event '{data.event_id}' not found or does not belong to your tenant",
            )

    # Check for duplicate (same checksum)
    existing = await repo.get_by_checksum(tenant.id, data.checksum)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document with same content already exists (ID: {existing.id})",
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
        created_by=data.created_by,
    )

    created = await repo.create(document)
    return created


@router.get("/subject/{subject_id}", response_model=list[DocumentResponse])
async def get_documents_by_subject(
    subject_id: str,
    repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    include_deleted: bool = False,
):
    """Get all documents for a subject"""
    return await repo.get_by_subject(subject_id, tenant.id, include_deleted)


@router.get("/event/{event_id}", response_model=list[DocumentResponse])
async def get_documents_by_event(
    event_id: str,
    repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    """Get all documents for an event"""
    return await repo.get_by_event(event_id, tenant.id)


@router.get("/{document_id}/versions", response_model=list[DocumentResponse])
async def get_document_versions(
    document_id: str,
    repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    """Get all versions of a document"""
    # First check if the document exists and belongs to tenant
    document = await repo.get_by_id(document_id)

    if not document or document.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Document not found")

    return await repo.get_versions(document_id, tenant.id)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    """Get a document by ID"""
    document = await repo.get_by_id(document_id)

    if not document or document.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.deleted_at:
        raise HTTPException(status_code=410, detail="Document has been deleted")

    return document


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    data: DocumentUpdate,
    repo: Annotated[DocumentRepository, Depends(get_document_repo_transactional)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
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
    repo: Annotated[DocumentRepository, Depends(get_document_repo_transactional)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    """Soft delete a document"""
    document = await repo.get_by_id(document_id)

    if not document or document.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.deleted_at:
        raise HTTPException(status_code=410, detail="Document already deleted")

    await repo.soft_delete(document_id)
