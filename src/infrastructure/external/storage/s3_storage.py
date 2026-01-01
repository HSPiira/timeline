"""
S3-compatible storage implementation (AWS S3, MinIO, DigitalOcean Spaces).

Security Features:
- Server-side encryption (AES256)
- Pre-signed URLs with expiration
- Checksum validation (SHA-256)
- Idempotent operations
- Bucket validation

Compatible with:
- AWS S3
- MinIO
- DigitalOcean Spaces
- Any S3-compatible storage
"""

import hashlib
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any, BinaryIO

import aioboto3
from botocore.exceptions import ClientError

from src.infrastructure.exceptions import (StorageAlreadyExistsError,
                                           StorageChecksumMismatchError,
                                           StorageDeleteError,
                                           StorageDownloadError,
                                           StorageNotFoundError,
                                           StorageUploadError)


class S3StorageService:
    """
    S3-compatible object storage with checksums and pre-signed URLs.

    Directory Structure (Object Keys):
    tenants/{tenant_code}/documents/{document_id}/v{version}/{filename}

    Security:
    - Server-side encryption (AES256)
    - Checksum validation via S3 metadata
    - Pre-signed URLs with expiration
    - Idempotent uploads
    """

    CHUNK_SIZE = 64 * 1024  # 64KB chunks for streaming

    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
    ):
        """
        Initialize S3 storage service.

        Args:
            bucket: S3 bucket name
            region: AWS region (default: us-east-1)
            endpoint_url: Custom endpoint for MinIO/DigitalOcean (optional)
            access_key: AWS access key (optional, uses IAM role if not provided)
            secret_key: AWS secret key (optional, uses IAM role if not provided)
        """
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key

        # Session configuration
        self.session = aioboto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def _get_client_config(self):
        """Get boto3 client configuration"""
        config = {}
        if self.endpoint_url:
            config["endpoint_url"] = self.endpoint_url
        return config

    async def _compute_checksum(self, file_data: BinaryIO) -> str:
        """
        Compute SHA-256 checksum of file.

        Args:
            file_data: File content (binary mode)

        Returns:
            str: Hexadecimal checksum (64 characters)
        """
        sha256 = hashlib.sha256()
        file_data.seek(0)

        while True:
            chunk = file_data.read(self.CHUNK_SIZE)
            if not chunk:
                break
            sha256.update(chunk)

        file_data.seek(0)
        return sha256.hexdigest()

    async def upload(
        self,
        file_data: BinaryIO,
        storage_ref: str,
        expected_checksum: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Upload file to S3 with checksum validation.

        Implementation:
        1. Check if object exists with same checksum (idempotency)
        2. Upload to S3 with server-side encryption
        3. Store checksum in S3 metadata
        4. Validate upload success

        Args:
            file_data: File content (binary mode)
            storage_ref: Object key (e.g., "tenants/acme/documents/doc_123/v1/file.pdf")
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
            async with self.session.client("s3", **self._get_client_config()) as s3:
                # Check if object already exists
                try:
                    head = await s3.head_object(Bucket=self.bucket, Key=storage_ref)
                    existing_checksum = head.get("Metadata", {}).get("sha256")

                    if existing_checksum == expected_checksum:
                        # Idempotent: object already exists with same checksum
                        return {
                            "storage_ref": storage_ref,
                            "checksum": existing_checksum,
                            "size": head["ContentLength"],
                            "uploaded_at": head["LastModified"].isoformat(),
                        }
                    else:
                        # Object exists with different checksum
                        raise StorageAlreadyExistsError(
                            f"Object exists at {storage_ref} with different checksum"
                        )
                except ClientError as e:
                    if e.response["Error"]["Code"] != "404":
                        raise

                # Read file content
                file_data.seek(0)
                file_content = file_data.read()
                file_size = len(file_content)

                # Compute checksum
                file_data.seek(0)
                computed_checksum = await self._compute_checksum(file_data)

                # Validate checksum
                if computed_checksum != expected_checksum:
                    raise StorageChecksumMismatchError(
                        file_path=storage_ref,
                        expected=expected_checksum,
                        actual=computed_checksum,
                    )

                # Prepare metadata
                s3_metadata = {
                    "sha256": computed_checksum,
                    "original-size": str(file_size),
                }
                if metadata:
                    # S3 metadata keys must be lowercase with hyphens
                    for key, value in metadata.items():
                        s3_metadata[key.lower().replace("_", "-")] = value

                # Upload to S3
                file_data.seek(0)
                await s3.put_object(
                    Bucket=self.bucket,
                    Key=storage_ref,
                    Body=file_content,
                    ContentType=content_type,
                    ServerSideEncryption="AES256",
                    Metadata=s3_metadata,
                )

                # Verify upload
                head = await s3.head_object(Bucket=self.bucket, Key=storage_ref)

                return {
                    "storage_ref": storage_ref,
                    "checksum": computed_checksum,
                    "size": file_size,
                    "uploaded_at": head["LastModified"].isoformat(),
                }

        except (StorageChecksumMismatchError, StorageAlreadyExistsError):
            raise
        except Exception as e:
            raise StorageUploadError(file_path=storage_ref, reason=str(e)) from e

    async def download(self, storage_ref: str) -> AsyncIterator[bytes]:
        """
        Stream file from S3.

        Args:
            storage_ref: Object key

        Yields:
            bytes: File content chunks

        Raises:
            StorageNotFoundError: If object doesn't exist
            StorageDownloadError: If download fails
        """
        try:
            async with self.session.client("s3", **self._get_client_config()) as s3:
                try:
                    response = await s3.get_object(Bucket=self.bucket, Key=storage_ref)

                    async with response["Body"] as stream:
                        while True:
                            chunk = await stream.read(self.CHUNK_SIZE)
                            if not chunk:
                                break
                            yield chunk

                except ClientError as e:
                    if e.response["Error"]["Code"] == "NoSuchKey":
                        raise StorageNotFoundError(
                            file_path=storage_ref,
                            message=e.response["Error"]["Message"],
                        ) from e
                    raise

        except StorageNotFoundError:
            raise
        except Exception as e:
            raise StorageDownloadError(file_path=storage_ref, reason=str(e)) from e

    async def delete(self, storage_ref: str) -> bool:
        """
        Delete object from S3.

        Args:
            storage_ref: Object key

        Returns:
            bool: True if deleted, False if didn't exist

        Raises:
            StorageDeleteError: If deletion fails
        """
        try:
            async with self.session.client("s3", **self._get_client_config()) as s3:
                # Check if object exists
                try:
                    await s3.head_object(Bucket=self.bucket, Key=storage_ref)
                except ClientError as e:
                    if e.response["Error"]["Code"] == "404":
                        return False
                    raise

                # Delete object
                await s3.delete_object(Bucket=self.bucket, Key=storage_ref)
                return True

        except Exception as e:
            raise StorageDeleteError(file_path=storage_ref, reason=str(e)) from e

    async def exists(self, storage_ref: str) -> bool:
        """
        Check if object exists in S3.

        Args:
            storage_ref: Object key

        Returns:
            bool: True if exists
        """
        try:
            async with self.session.client("s3", **self._get_client_config()) as s3:
                await s3.head_object(Bucket=self.bucket, Key=storage_ref)
                return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            return False
        except Exception:
            return False

    async def get_metadata(self, storage_ref: str) -> dict[str, Any]:
        """
        Get object metadata without downloading.

        Args:
            storage_ref: Object key

        Returns:
            dict: Metadata

        Raises:
            StorageNotFoundError: If object doesn't exist
        """
        try:
            async with self.session.client("s3", **self._get_client_config()) as s3:
                head = await s3.head_object(Bucket=self.bucket, Key=storage_ref)

                custom_metadata = head.get("Metadata", {})

                return {
                    "size": head["ContentLength"],
                    "content_type": head.get("ContentType", "application/octet-stream"),
                    "checksum": custom_metadata.get("sha256"),
                    "last_modified": head["LastModified"].isoformat(),
                    "custom": custom_metadata,
                }

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                raise StorageNotFoundError(file_path=storage_ref) from e
            raise
        except Exception as e:
            raise StorageDownloadError(file_path=storage_ref, reason=str(e)) from e

    async def generate_download_url(
        self, storage_ref: str, expiration: timedelta = timedelta(hours=1)
    ) -> str:
        """
        Generate pre-signed download URL.

        Args:
            storage_ref: Object key
            expiration: URL expiration time (default: 1 hour)

        Returns:
            str: Pre-signed URL

        Raises:
            StorageNotFoundError: If object doesn't exist
        """
        try:
            async with self.session.client("s3", **self._get_client_config()) as s3:
                # Verify object exists
                try:
                    await s3.head_object(Bucket=self.bucket, Key=storage_ref)
                except ClientError as e:
                    if e.response["Error"]["Code"] == "404":
                        raise StorageNotFoundError(file_path=storage_ref) from e
                    raise

                # Generate pre-signed URL
                url: str = await s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": storage_ref},
                    ExpiresIn=int(expiration.total_seconds()),
                )

                return url

        except StorageNotFoundError:
            raise
        except Exception as e:
            raise StorageDownloadError(file_path=storage_ref, reason=str(e)) from e
