"""Document service for coordinating storage and database operations."""
import hashlib
from typing import Optional, BinaryIO
from datetime import datetime

from core.storage_protocols import IStorageService
from core.exceptions import StorageException
from repositories.document_repo import DocumentRepository
from repositories.tenant_repo import TenantRepository
from models.document import Document
from utils.generators import generate_cuid


class DocumentService:
    """
    Orchestrates document upload/download coordinating storage + database.

    Responsibilities:
    - Generate storage_ref paths
    - Compute file checksums
    - Coordinate storage upload with database transaction
    - Handle versioning logic
    - Validate tenant ownership
    """

    def __init__(
        self,
        storage_service: IStorageService,
        document_repo: DocumentRepository,
        tenant_repo: TenantRepository
    ):
        self.storage = storage_service
        self.document_repo = document_repo
        self.tenant_repo = tenant_repo

    def _generate_storage_ref(
        self,
        tenant_code: str,
        document_id: str,
        version: int,
        filename: str
    ) -> str:
        """
        Generate storage reference path.

        Format: tenants/{tenant_code}/documents/{document_id}/v{version}/{filename}

        Args:
            tenant_code: Human-readable tenant code
            document_id: Document CUID
            version: Version number
            filename: Original filename

        Returns:
            str: Storage reference path
        """
        return f"tenants/{tenant_code}/documents/{document_id}/v{version}/{filename}"

    async def _compute_checksum(self, file_data: BinaryIO) -> str:
        """
        Compute SHA-256 checksum of file.

        Args:
            file_data: File binary data

        Returns:
            str: Hex checksum (64 chars)
        """
        sha256 = hashlib.sha256()

        # Read file
        content = file_data.read()
        sha256.update(content)

        # Reset file pointer for subsequent reads
        file_data.seek(0)

        return sha256.hexdigest()

    async def upload_document(
        self,
        tenant_id: str,
        subject_id: str,
        file_data: BinaryIO,
        filename: str,
        original_filename: str,
        mime_type: str,
        document_type: str,
        event_id: Optional[str] = None,
        created_by: Optional[str] = None,
        parent_document_id: Optional[str] = None
    ) -> Document:
        """
        Upload document file and create database record.

        Workflow:
        1. Get tenant code
        2. Compute checksum
        3. Check for duplicates
        4. Determine version number
        5. Generate storage_ref
        6. Upload to storage
        7. Create database record

        Args:
            tenant_id: Tenant ID
            subject_id: Subject ID
            file_data: File binary data
            filename: Storage filename
            original_filename: User-facing filename
            mime_type: MIME type
            document_type: Document type classification
            event_id: Optional event linkage
            created_by: User ID
            parent_document_id: For versioning

        Returns:
            Document: Created document model

        Raises:
            ValueError: If duplicate found or validation fails
            StorageException: If upload fails
        """
        # Get tenant for code
        tenant = await self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant not found: {tenant_id}")

        # Compute checksum
        file_data.seek(0)  # Ensure at start
        checksum = await self._compute_checksum(file_data)
        file_data.seek(0)

        # Check for duplicates (per tenant)
        existing = await self.document_repo.get_by_checksum(tenant_id, checksum)
        if existing:
            raise ValueError(
                f"Document with checksum {checksum} already exists (ID: {existing.id})"
            )

        # Determine version
        if parent_document_id:
            parent = await self.document_repo.get_by_id(parent_document_id)
            if not parent:
                raise ValueError(f"Parent document not found: {parent_document_id}")
            if parent.tenant_id != tenant_id:
                raise ValueError("Parent document belongs to different tenant")

            version = parent.version + 1

            # Mark parent as not latest
            parent.is_latest_version = False
            await self.document_repo.update(parent)
        else:
            version = 1

        # Generate document ID and storage_ref
        document_id = generate_cuid()
        storage_ref = self._generate_storage_ref(
            tenant.code,
            document_id,
            version,
            filename
        )

        # Get file size
        file_data.seek(0, 2)  # Seek to end
        file_size = file_data.tell()
        file_data.seek(0)  # Reset

        # Upload to storage
        try:
            upload_result = await self.storage.upload(
                file_data=file_data,
                storage_ref=storage_ref,
                expected_checksum=checksum,
                content_type=mime_type,
                metadata={
                    "document_id": document_id,
                    "tenant_id": tenant_id,
                    "subject_id": subject_id
                }
            )
        except StorageException as e:
            raise ValueError(f"Storage upload failed: {str(e)}") from e

        # Create database record
        document = Document(
            id=document_id,
            tenant_id=tenant_id,
            subject_id=subject_id,
            event_id=event_id,
            document_type=document_type,
            filename=filename,
            original_filename=original_filename,
            mime_type=mime_type,
            file_size=file_size,
            checksum=checksum,
            storage_ref=storage_ref,
            version=version,
            is_latest_version=True,
            parent_document_id=parent_document_id,
            created_by=created_by
        )

        return await self.document_repo.create(document)

    async def download_document_stream(self, document: Document):
        """
        Get download stream for document.

        Args:
            document: Document model

        Returns:
            AsyncIterator[bytes]: File content stream

        Raises:
            StorageException: If download fails
        """
        return self.storage.download(document.storage_ref)

    async def delete_document_file(self, document: Document) -> bool:
        """
        Delete document file from storage (for cleanup).

        Args:
            document: Document model

        Returns:
            bool: True if deleted

        Note: This is for soft-deleted documents cleanup.
        Database record should be soft-deleted separately.
        """
        return await self.storage.delete(document.storage_ref)
