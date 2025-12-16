"""
Storage service protocols for Timeline document storage.

Provides abstract interface for object storage backends following
Dependency Inversion Principle (DIP) - enables switching between
local filesystem, S3, MinIO, Azure Blob, etc. without domain logic changes.
"""
from typing import Protocol, BinaryIO, AsyncIterator, Optional, Dict, Any
from datetime import timedelta


class IStorageService(Protocol):
    """
    Protocol for object storage backends (DIP compliance).

    All storage implementations must provide these methods to ensure
    seamless backend switching without modifying business logic.

    Implementations:
    - LocalStorageService: Filesystem storage with atomic writes
    - S3StorageService: AWS S3 or MinIO compatible storage
    - AzureBlobStorageService: Azure Blob Storage (future)
    """

    async def upload(
        self,
        file_data: BinaryIO,
        storage_ref: str,
        expected_checksum: str,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Upload file to storage with checksum verification.

        Args:
            file_data: File-like object (binary mode)
            storage_ref: Storage path/key (e.g., "tenants/acme/documents/doc123/v1/file.pdf")
            expected_checksum: SHA-256 checksum (64 hex characters)
            content_type: MIME type (e.g., "application/pdf")
            metadata: Optional key-value pairs for custom metadata

        Returns:
            dict: Upload result with keys:
                - storage_ref: Confirmed storage path
                - checksum: Verified checksum
                - size: File size in bytes
                - uploaded_at: ISO timestamp

        Raises:
            StorageChecksumMismatchError: If computed checksum != expected
            StorageUploadError: If upload fails
            StorageAlreadyExistsError: If file exists with different checksum

        Implementation Notes:
        - Must be idempotent (same checksum = no-op, return existing)
        - Must validate checksum before finalizing upload
        - Should use atomic operations (temp file + rename pattern)
        """
        ...

    async def download(self, storage_ref: str) -> AsyncIterator[bytes]:
        """
        Stream file from storage.

        Args:
            storage_ref: Storage path/key

        Yields:
            bytes: File content chunks (streaming for memory efficiency)

        Raises:
            StorageNotFoundError: If file doesn't exist
            StorageDownloadError: If download fails

        Implementation Notes:
        - Must stream in chunks to avoid loading entire file in memory
        - Recommended chunk size: 64KB - 1MB
        - For local storage: use aiofiles
        - For S3: use aioboto3 streaming
        """
        ...

    async def delete(self, storage_ref: str) -> bool:
        """
        Delete file from storage.

        Args:
            storage_ref: Storage path/key

        Returns:
            bool: True if deleted, False if didn't exist

        Raises:
            StorageDeleteError: If deletion fails

        Implementation Notes:
        - Should be idempotent (deleting non-existent file returns False)
        - For soft-deleted documents, this is called during cleanup
        """
        ...

    async def exists(self, storage_ref: str) -> bool:
        """
        Check if file exists in storage.

        Args:
            storage_ref: Storage path/key

        Returns:
            bool: True if file exists, False otherwise

        Implementation Notes:
        - Cheap operation (HEAD request for S3, stat for filesystem)
        - Used for idempotency checks before upload
        """
        ...

    async def get_metadata(self, storage_ref: str) -> Dict[str, Any]:
        """
        Get file metadata without downloading content.

        Args:
            storage_ref: Storage path/key

        Returns:
            dict: Metadata with keys:
                - size: File size in bytes
                - content_type: MIME type
                - checksum: SHA-256 checksum (if available)
                - last_modified: ISO timestamp
                - custom: Dict of custom metadata (if any)

        Raises:
            StorageNotFoundError: If file doesn't exist

        Implementation Notes:
        - For local storage: read from sidecar JSON file
        - For S3: use HEAD request to get object metadata
        """
        ...

    async def generate_download_url(
        self,
        storage_ref: str,
        expiration: timedelta = timedelta(hours=1)
    ) -> str:
        """
        Generate pre-signed download URL (S3) or direct URL (local).

        Args:
            storage_ref: Storage path/key
            expiration: URL validity duration (default: 1 hour)

        Returns:
            str: Download URL (pre-signed for S3, local path for filesystem)

        Raises:
            StorageNotFoundError: If file doesn't exist
            StorageNotSupportedError: If operation not supported by backend

        Implementation Notes:
        - For S3: generate pre-signed URL with expiration
        - For local storage: may return file:// URL or raise NotSupported
        - Used for direct client downloads without proxying through API
        """
        ...
