"""
Local filesystem storage implementation with enterprise security features.

Security Features:
- Path traversal protection (resolve + prefix validation)
- Atomic writes (temp file + atomic rename)
- Checksum validation (SHA-256)
- File permissions (0o640 files, 0o750 dirs)
- Idempotent operations
"""

import hashlib
import json
import os
import secrets
import tempfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO, cast

import aiofiles
import aiofiles.os

from src.infrastructure.exceptions import (
    StorageAlreadyExistsError,
    StorageChecksumMismatchError,
    StorageDeleteError,
    StorageDownloadError,
    StorageNotFoundError,
    StoragePermissionError,
    StorageUploadError,
)


class LocalStorageService:
    """
    Local filesystem storage with atomic writes and path traversal protection.

    Directory Structure:
    /storage/tenants/{tenant_code}/documents/{document_id}/v{version}/{filename}

    Security:
    - All paths validated against storage root (no ../.. attacks)
    - Atomic writes via temp file + rename
    - Checksums validated on upload
    - File permissions: 0o640 (owner rw, group r)
    - Directory permissions: 0o750 (owner rwx, group rx)
    - Pre-signed URLs with expiration for secure temporary access
    """

    CHUNK_SIZE = 64 * 1024  # 64KB chunks for streaming

    # Token storage: {token: (storage_ref, expires_at)}
    _download_tokens: dict[str, tuple[str, datetime]] = {}

    def __init__(self, storage_root: str, base_url: str | None = None) -> None:
        """
        Initialize local storage service.

        Args:
            storage_root: Base directory for all file storage
            base_url: Base URL for download endpoints (e.g., "https://api.example.com")
                     If None, returns relative path
        """
        self.storage_root = Path(storage_root).resolve()
        self.base_url = base_url.rstrip("/") if base_url else None

        # Create storage root if it doesn't exist
        self.storage_root.mkdir(parents=True, exist_ok=True, mode=0o750)

    def _get_full_path(self, storage_ref: str) -> Path:
        """
        Get full filesystem path with security validation.

        Args:
            storage_ref: Relative storage path (e.g., "tenants/acme/documents/...")

        Returns:
            Path: Validated absolute path

        Raises:
            StoragePermissionError: If path traversal detected
        """
        # Resolve full path
        full_path = (self.storage_root / storage_ref).resolve()

        # Security check: ensure path is within storage root
        try:
            full_path.relative_to(self.storage_root)
        except ValueError as e:
            raise StoragePermissionError(storage_ref, "path_validation") from e

        return full_path

    async def _compute_checksum(self, file_path: Path) -> str:
        """
        Compute SHA-256 checksum of file.

        Args:
            file_path: Path to file

        Returns:
            str: Hexadecimal checksum (64 characters)
        """
        sha256 = hashlib.sha256()

        async with aiofiles.open(file_path, "rb") as f:
            while True:
                chunk = await f.read(self.CHUNK_SIZE)
                if not chunk:
                    break
                sha256.update(chunk)

        return sha256.hexdigest()

    async def _write_metadata(self, file_path: Path, metadata: dict[str, Any]) -> None:
        """
        Write metadata to JSON sidecar file.

        Args:
            file_path: Path to data file
            metadata: Metadata dictionary
        """
        metadata_path = file_path.with_suffix(file_path.suffix + ".meta.json")

        async with aiofiles.open(metadata_path, "w") as f:
            await f.write(json.dumps(metadata, indent=2))

        # Set permissions
        os.chmod(metadata_path, 0o640)

    async def _read_metadata(self, file_path: Path) -> dict[str, Any]:
        """
        Read metadata from JSON sidecar file.

        Args:
            file_path: Path to data file

        Returns:
            dict: Metadata or empty dict if not found
        """
        metadata_path = file_path.with_suffix(file_path.suffix + ".meta.json")

        if not metadata_path.exists():
            return {}

        async with aiofiles.open(metadata_path, "r") as f:
            content = await f.read()
            result = json.loads(content)
            if not isinstance(result, dict):
                return {}
            return cast(dict[str, Any], result)

    async def upload(
        self,
        file_data: BinaryIO,
        storage_ref: str,
        expected_checksum: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Upload file with atomic write and checksum validation.

        Implementation:
        1. Validate path (no traversal)
        2. Check if file exists with same checksum (idempotency)
        3. Write to temp file
        4. Compute checksum
        5. Validate checksum
        6. Atomic rename to final location
        7. Write metadata sidecar

        Args:
            file_data: File content (binary mode)
            storage_ref: Storage path
            expected_checksum: SHA-256 checksum (64 hex chars)
            content_type: MIME type
            metadata: Optional custom metadata

        Returns:
            dict: Upload result

        Raises:
            StorageChecksumMismatchError: If checksum doesn't match
            StorageAlreadyExistsError: If file exists with different checksum
            StorageUploadError: If upload fails
        """
        try:
            # Validate path
            target_path = self._get_full_path(storage_ref)

            # Check if file already exists
            if target_path.exists():
                existing_checksum = await self._compute_checksum(target_path)

                if existing_checksum == expected_checksum:
                    # Idempotent: file already exists with same checksum
                    existing_metadata = await self._read_metadata(target_path)
                    return {
                        "storage_ref": storage_ref,
                        "checksum": existing_checksum,
                        "size": target_path.stat().st_size,
                        "uploaded_at": existing_metadata.get(
                            "uploaded_at", datetime.now(UTC).isoformat()
                        ),
                    }
                else:
                    # File exists with different checksum
                    raise StorageAlreadyExistsError(storage_ref)

            # Create parent directories
            target_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)

            # Read file content
            file_content = file_data.read()
            file_size = len(file_content)

            # Write to temp file first (atomic write pattern)
            temp_fd, temp_path = tempfile.mkstemp(
                dir=target_path.parent, prefix=".tmp_", suffix=target_path.suffix
            )

            try:
                # Write content
                async with aiofiles.open(temp_path, "wb") as f:
                    await f.write(file_content)

                # Set file permissions
                os.chmod(temp_path, 0o640)

                # Compute checksum
                computed_checksum = await self._compute_checksum(Path(temp_path))

                # Validate checksum
                if computed_checksum != expected_checksum:
                    raise StorageChecksumMismatchError(
                        storage_ref,
                        expected_checksum,
                        computed_checksum,
                    )

                # Atomic rename
                os.rename(temp_path, target_path)

                # Write metadata
                upload_metadata: dict[str, Any] = {
                    "storage_ref": storage_ref,
                    "checksum": computed_checksum,
                    "size": file_size,
                    "content_type": content_type,
                    "uploaded_at": datetime.now(UTC).isoformat(),
                    "custom": metadata or {},
                }
                await self._write_metadata(target_path, upload_metadata)

                return cast(dict[str, Any], {
                    "storage_ref": storage_ref,
                    "checksum": computed_checksum,
                    "size": file_size,
                    "uploaded_at": upload_metadata["uploaded_at"],
                })

            finally:
                # Clean up temp file if it still exists
                if Path(temp_path).exists():
                    os.close(temp_fd)
                    os.unlink(temp_path)

        except (
            StorageChecksumMismatchError,
            StorageAlreadyExistsError,
            StoragePermissionError,
        ):
            raise
        except Exception as e:
            raise StorageUploadError(storage_ref, f"Upload failed: {str(e)}") from e

    async def download(self, storage_ref: str) -> AsyncIterator[bytes]:
        """
        Stream file from storage.

        Args:
            storage_ref: Storage path

        Yields:
            bytes: File content chunks

        Raises:
            StorageNotFoundError: If file doesn't exist
            StorageDownloadError: If download fails
        """
        try:
            file_path = self._get_full_path(storage_ref)

            if not file_path.exists():
                raise StorageNotFoundError(f"File not found: {storage_ref}")

            async with aiofiles.open(file_path, "rb") as f:
                while True:
                    chunk = await f.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk

        except StorageNotFoundError:
            raise
        except Exception as e:
            raise StorageDownloadError(storage_ref, f"Download failed: {str(e)}") from e

    async def delete(self, storage_ref: str) -> bool:
        """
        Delete file from storage.

        Args:
            storage_ref: Storage path

        Returns:
            bool: True if deleted, False if didn't exist

        Raises:
            StorageDeleteError: If deletion fails
        """
        try:
            file_path = self._get_full_path(storage_ref)

            if not file_path.exists():
                return False

            # Delete data file
            await aiofiles.os.remove(file_path)

            # Delete metadata file if exists
            metadata_path = file_path.with_suffix(file_path.suffix + ".meta.json")
            if metadata_path.exists():
                await aiofiles.os.remove(metadata_path)

            # Clean up empty parent directories
            parent = file_path.parent
            while parent != self.storage_root:
                try:
                    if not any(parent.iterdir()):
                        parent.rmdir()
                        parent = parent.parent
                    else:
                        break
                except OSError:
                    break

            return True

        except Exception as e:
            raise StorageDeleteError(storage_ref, f"Delete failed: {str(e)}") from e

    async def exists(self, storage_ref: str) -> bool:
        """
        Check if file exists.

        Args:
            storage_ref: Storage path

        Returns:
            bool: True if exists
        """
        try:
            file_path = self._get_full_path(storage_ref)
            return file_path.exists()
        except Exception as e:
            raise StorageNotFoundError(f"File not found: {storage_ref}") from e

    async def get_metadata(self, storage_ref: str) -> dict[str, Any]:
        """
        Get file metadata without downloading.

        Args:
            storage_ref: Storage path

        Returns:
            dict: Metadata

        Raises:
            StorageNotFoundError: If file doesn't exist
        """
        file_path = self._get_full_path(storage_ref)

        if not file_path.exists():
            raise StorageNotFoundError(f"File not found: {storage_ref}")

        stat = file_path.stat()
        stored_metadata = await self._read_metadata(file_path)

        return {
            "size": stat.st_size,
            "content_type": stored_metadata.get("content_type", "application/octet-stream"),
            "checksum": stored_metadata.get("checksum"),
            "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "custom": stored_metadata.get("custom", {}),
        }

    async def generate_download_url(
        self,
        storage_ref: str,
        expiration: timedelta = timedelta(hours=1)
    ) -> str:
        """
        Generate temporary download URL with expiration.

        Args:
            storage_ref: Storage path
            expiration: URL expiration time (default: 1 hour)

        Returns:
            str: Temporary download URL

        Raises:
            StorageNotFoundError: If file doesn't exist
        """
        # Verify file exists
        if not await self.exists(storage_ref):
            raise StorageNotFoundError(f"File not found: {storage_ref}")

        # Generate secure token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + expiration

        # Store token mapping
        self._download_tokens[token] = (storage_ref, expires_at)

        # Clean expired tokens
        self._cleanup_expired_tokens()

        # Return URL
        path = f"/api/storage/download/{token}"
        if self.base_url:
            return f"{self.base_url}{path}"
        return path

    def _cleanup_expired_tokens(self) -> None:
        """Remove expired download tokens."""
        now = datetime.now(UTC)
        expired = [
            token
            for token, (_, expires_at) in self._download_tokens.items()
            if expires_at <= now
        ]
        for token in expired:
            del self._download_tokens[token]

    def validate_download_token(self, token: str) -> str | None:
        """
        Validate download token and return storage_ref if valid.

        Args:
            token: Download token

        Returns:
            str | None: Storage reference if valid, None if invalid/expired
        """
        if token not in self._download_tokens:
            return None

        storage_ref, expires_at = self._download_tokens[token]

        # Check if expired
        if datetime.now(UTC) > expires_at:
            del self._download_tokens[token]
            return None

        return storage_ref
