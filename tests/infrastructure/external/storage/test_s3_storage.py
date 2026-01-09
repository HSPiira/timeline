"""Unit tests for S3StorageService"""

import io
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from botocore.exceptions import ClientError

from src.infrastructure.exceptions import (StorageAlreadyExistsError,
                                           StorageChecksumMismatchError,
                                           StorageNotFoundError)
from src.infrastructure.external.storage.s3_storage import S3StorageService


@pytest.fixture
def s3_service():
    """Provides an S3StorageService instance for testing."""
    return S3StorageService(
        bucket="test-bucket",
        region="us-east-1",
        endpoint_url="http://localhost:9000",  # MinIO
        access_key="test-access-key",
        secret_key="test-secret-key",
    )


@pytest.fixture
def sample_file_data():
    """Provides sample file data for testing."""
    content = b"Hello, World! This is test content."
    return io.BytesIO(content)


@pytest.fixture
def sample_checksum():
    """
    Provides the SHA-256 checksum for the sample file data.

    Computed from: b"Hello, World! This is test content."
    """
    return "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"


class TestS3StorageUpload:
    """Tests for S3StorageService upload functionality."""

    @pytest.mark.asyncio
    async def test_upload_success(self, s3_service, sample_file_data, sample_checksum):
        """
        GIVEN a valid file with correct checksum
        WHEN uploading to S3
        THEN file should be uploaded successfully with metadata
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/doc_123/v1/test.txt"
        content_type = "text/plain"

        mock_s3_client = AsyncMock()
        mock_s3_client.head_object = AsyncMock(
            side_effect=ClientError({"Error": {"Code": "404"}}, "head_object")
        )
        mock_s3_client.put_object = AsyncMock()
        mock_s3_client.head_object = AsyncMock(
            side_effect=[
                ClientError({"Error": {"Code": "404"}}, "head_object"),  # First check
                {"ContentLength": 35, "LastModified": datetime.now(UTC)()},  # After upload
            ]
        )

        # WHEN
        with patch.object(s3_service.session, "client") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_s3_client

            result = await s3_service.upload(
                file_data=sample_file_data,
                storage_ref=storage_ref,
                expected_checksum=sample_checksum,
                content_type=content_type,
                metadata={"custom_key": "custom_value"},
            )

        # THEN
        assert result["storage_ref"] == storage_ref
        assert result["checksum"] == sample_checksum
        assert result["size"] == 35
        assert "uploaded_at" in result

        # Verify put_object was called with correct parameters
        mock_s3_client.put_object.assert_called_once()
        call_kwargs = mock_s3_client.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Key"] == storage_ref
        assert call_kwargs["ContentType"] == content_type
        assert call_kwargs["ServerSideEncryption"] == "AES256"
        assert "sha256" in call_kwargs["Metadata"]

    @pytest.mark.asyncio
    async def test_upload_checksum_mismatch(self, s3_service, sample_file_data):
        """
        GIVEN a file with incorrect checksum
        WHEN uploading to S3
        THEN should raise StorageChecksumMismatchError
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/doc_456/v1/test.txt"
        wrong_checksum = "0000000000000000000000000000000000000000000000000000000000000000"

        mock_s3_client = AsyncMock()
        mock_s3_client.head_object = AsyncMock(
            side_effect=ClientError({"Error": {"Code": "404"}}, "head_object")
        )

        # WHEN/THEN
        with patch.object(s3_service.session, "client") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_s3_client

            with pytest.raises(StorageChecksumMismatchError) as exc_info:
                await s3_service.upload(
                    file_data=sample_file_data,
                    storage_ref=storage_ref,
                    expected_checksum=wrong_checksum,
                    content_type="text/plain",
                )

            assert "Checksum mismatch" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_upload_idempotent_same_checksum(
        self, s3_service, sample_file_data, sample_checksum
    ):
        """
        GIVEN an object already exists with same checksum
        WHEN uploading again with same checksum
        THEN should return existing metadata (idempotent)
        """
        # GIVEN - Object already exists
        existing_metadata = {
            "ContentLength": 35,
            "LastModified": datetime.now(UTC),
            "Metadata": {"sha256": sample_checksum},
        }

        mock_s3_client = AsyncMock()
        mock_s3_client.head_object = AsyncMock(return_value=existing_metadata)

        # WHEN
        with patch.object(s3_service.session, "client") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_s3_client

            result = await s3_service.upload(
                file_data=sample_file_data,
                storage_ref="tenants/acme/documents/doc_789/v1/test.txt",
                expected_checksum=sample_checksum,
                content_type="text/plain",
            )

        # THEN - Should return existing metadata (no upload)
        assert result["checksum"] == sample_checksum
        assert result["size"] == 35
        mock_s3_client.put_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_upload_rejects_different_checksum(
        self, s3_service, sample_file_data, sample_checksum
    ):
        """
        GIVEN an object exists with different checksum
        WHEN uploading with different content
        THEN should raise StorageAlreadyExistsError
        """
        # GIVEN - Object exists with different checksum
        existing_metadata = {
            "ContentLength": 35,
            "LastModified": datetime.now(UTC),
            "Metadata": {"sha256": "different_checksum"},
        }

        mock_s3_client = AsyncMock()
        mock_s3_client.head_object = AsyncMock(return_value=existing_metadata)

        # WHEN/THEN
        with patch.object(s3_service.session, "client") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_s3_client

            with pytest.raises(StorageAlreadyExistsError):
                await s3_service.upload(
                    file_data=sample_file_data,
                    storage_ref="tenants/acme/documents/doc_abc/v1/test.txt",
                    expected_checksum=sample_checksum,
                    content_type="text/plain",
                )


class TestS3StorageDownload:
    """Tests for S3StorageService download functionality."""

    @pytest.mark.asyncio
    async def test_download_success(self, s3_service, sample_file_data):
        """
        GIVEN an object exists in S3
        WHEN downloading
        THEN should stream content correctly
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/doc_123/v1/test.txt"

        # Create mock streaming body
        mock_stream = AsyncMock()
        mock_stream.read = AsyncMock(
            side_effect=[sample_file_data.read(), b""]  # Return content then EOF
        )

        mock_response = {"Body": mock_stream}

        mock_s3_client = AsyncMock()
        mock_s3_client.get_object = AsyncMock(return_value=mock_response)

        # WHEN
        with patch.object(s3_service.session, "client") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_s3_client

            chunks = []
            async for chunk in s3_service.download(storage_ref):
                chunks.append(chunk)

        # THEN
        downloaded_content = b"".join(chunks)
        sample_file_data.seek(0)
        assert downloaded_content == sample_file_data.read()

    @pytest.mark.asyncio
    async def test_download_not_found(self, s3_service):
        """
        GIVEN a non-existent object
        WHEN trying to download
        THEN should raise StorageNotFoundError
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/nonexistent/v1/test.txt"

        mock_s3_client = AsyncMock()
        mock_s3_client.get_object = AsyncMock(
            side_effect=ClientError({"Error": {"Code": "NoSuchKey"}}, "get_object")
        )

        # WHEN/THEN
        with patch.object(s3_service.session, "client") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_s3_client

            with pytest.raises(StorageNotFoundError) as exc_info:
                async for _ in s3_service.download(storage_ref):
                    pass

            assert "Object not found" in str(exc_info.value)


class TestS3StorageMetadata:
    """Tests for metadata operations."""

    @pytest.mark.asyncio
    async def test_get_metadata(self, s3_service):
        """
        GIVEN an object exists in S3
        WHEN retrieving metadata
        THEN should return correct object information
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/doc_123/v1/test.txt"
        head_response = {
            "ContentLength": 35,
            "ContentType": "text/plain",
            "LastModified": datetime.now(UTC),
            "Metadata": {"sha256": "test_checksum", "author": "test_user"},
        }

        mock_s3_client = AsyncMock()
        mock_s3_client.head_object = AsyncMock(return_value=head_response)

        # WHEN
        with patch.object(s3_service.session, "client") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_s3_client

            metadata = await s3_service.get_metadata(storage_ref)

        # THEN
        assert metadata["size"] == 35
        assert metadata["content_type"] == "text/plain"
        assert metadata["checksum"] == "test_checksum"
        assert "last_modified" in metadata
        assert metadata["custom"]["author"] == "test_user"

    @pytest.mark.asyncio
    async def test_exists_true(self, s3_service):
        """
        GIVEN an object exists in S3
        WHEN checking if exists
        THEN should return True
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/doc_123/v1/test.txt"

        mock_s3_client = AsyncMock()
        mock_s3_client.head_object = AsyncMock(return_value={})

        # WHEN/THEN
        with patch.object(s3_service.session, "client") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_s3_client

            assert await s3_service.exists(storage_ref) is True

    @pytest.mark.asyncio
    async def test_exists_false(self, s3_service):
        """
        GIVEN a non-existent object
        WHEN checking if exists
        THEN should return False
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/nonexistent/v1/test.txt"

        mock_s3_client = AsyncMock()
        mock_s3_client.head_object = AsyncMock(
            side_effect=ClientError({"Error": {"Code": "404"}}, "head_object")
        )

        # WHEN/THEN
        with patch.object(s3_service.session, "client") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_s3_client

            assert await s3_service.exists(storage_ref) is False


class TestS3StorageDelete:
    """Tests for delete functionality."""

    @pytest.mark.asyncio
    async def test_delete_success(self, s3_service):
        """
        GIVEN an object exists in S3
        WHEN deleting
        THEN object should be removed
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/doc_123/v1/test.txt"

        mock_s3_client = AsyncMock()
        mock_s3_client.head_object = AsyncMock(return_value={})
        mock_s3_client.delete_object = AsyncMock()

        # WHEN
        with patch.object(s3_service.session, "client") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_s3_client

            result = await s3_service.delete(storage_ref)

        # THEN
        assert result is True
        mock_s3_client.delete_object.assert_called_once_with(Bucket="test-bucket", Key=storage_ref)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_object(self, s3_service):
        """
        GIVEN a non-existent object
        WHEN trying to delete
        THEN should return False (idempotent)
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/nonexistent/v1/test.txt"

        mock_s3_client = AsyncMock()
        mock_s3_client.head_object = AsyncMock(
            side_effect=ClientError({"Error": {"Code": "404"}}, "head_object")
        )

        # WHEN
        with patch.object(s3_service.session, "client") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_s3_client

            result = await s3_service.delete(storage_ref)

        # THEN
        assert result is False
        mock_s3_client.delete_object.assert_not_called()


class TestS3StoragePresignedURLs:
    """Tests for pre-signed URL generation."""

    @pytest.mark.asyncio
    async def test_generate_download_url_success(self, s3_service):
        """
        GIVEN an object exists in S3
        WHEN generating pre-signed URL
        THEN should return valid URL with expiration
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/doc_123/v1/test.txt"
        expiration = timedelta(hours=1)
        expected_url = "https://test-bucket.s3.amazonaws.com/presigned-url"

        mock_s3_client = AsyncMock()
        mock_s3_client.head_object = AsyncMock(return_value={})
        mock_s3_client.generate_presigned_url = AsyncMock(return_value=expected_url)

        # WHEN
        with patch.object(s3_service.session, "client") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_s3_client

            url = await s3_service.generate_download_url(storage_ref, expiration)

        # THEN
        assert url == expected_url
        mock_s3_client.generate_presigned_url.assert_called_once()

        # Verify expiration was passed correctly
        call_kwargs = mock_s3_client.generate_presigned_url.call_args.kwargs
        assert call_kwargs["ExpiresIn"] == 3600  # 1 hour in seconds

    @pytest.mark.asyncio
    async def test_generate_download_url_not_found(self, s3_service):
        """
        GIVEN a non-existent object
        WHEN trying to generate pre-signed URL
        THEN should raise StorageNotFoundError
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/nonexistent/v1/test.txt"

        mock_s3_client = AsyncMock()
        mock_s3_client.head_object = AsyncMock(
            side_effect=ClientError({"Error": {"Code": "404"}}, "head_object")
        )

        # WHEN/THEN
        with patch.object(s3_service.session, "client") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_s3_client

            with pytest.raises(StorageNotFoundError):
                await s3_service.generate_download_url(storage_ref)


class TestS3ServiceConfiguration:
    """Tests for S3 service configuration."""

    def test_initialization_with_custom_endpoint(self):
        """
        GIVEN custom endpoint for MinIO/DigitalOcean
        WHEN creating S3 service
        THEN should configure endpoint correctly
        """
        # GIVEN/WHEN
        service = S3StorageService(
            bucket="test-bucket",
            region="us-east-1",
            endpoint_url="http://localhost:9000",
            access_key="test-key",
            secret_key="test-secret",
        )

        # THEN
        assert service.bucket == "test-bucket"
        assert service.region == "us-east-1"
        assert service.endpoint_url == "http://localhost:9000"

        client_config = service._get_client_config()
        assert client_config["endpoint_url"] == "http://localhost:9000"

    def test_initialization_aws_s3(self):
        """
        GIVEN AWS S3 configuration
        WHEN creating S3 service
        THEN should not include custom endpoint
        """
        # GIVEN/WHEN
        service = S3StorageService(
            bucket="my-bucket", region="us-west-2", access_key="aws-key", secret_key="aws-secret"
        )

        # THEN
        assert service.bucket == "my-bucket"
        assert service.region == "us-west-2"
        assert service.endpoint_url is None

        client_config = service._get_client_config()
        assert "endpoint_url" not in client_config
