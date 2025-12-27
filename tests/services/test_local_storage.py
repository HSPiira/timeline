"""Unit tests for LocalStorageService"""
import io
import tempfile
import pytest
from pathlib import Path
from services.storage.local_storage import LocalStorageService
from core.exceptions import (
    StorageNotFoundError,
    StorageChecksumMismatchError,
    StoragePermissionError,
    StorageAlreadyExistsError
)


@pytest.fixture
def temp_storage_root(tmp_path):
    """Provides a temporary storage root directory."""
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    return str(storage_root)


@pytest.fixture
def storage_service(temp_storage_root):
    """Provides a LocalStorageService instance with temporary storage."""
    return LocalStorageService(storage_root=temp_storage_root)


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


class TestLocalStorageUpload:
    """Tests for LocalStorageService upload functionality."""

    @pytest.mark.asyncio
    async def test_upload_success(self, storage_service, sample_file_data, sample_checksum):
        """
        GIVEN a valid file with correct checksum
        WHEN uploading to storage
        THEN file should be saved successfully with metadata
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/doc_123/v1/test.txt"
        content_type = "text/plain"

        # WHEN
        result = await storage_service.upload(
            file_data=sample_file_data,
            storage_ref=storage_ref,
            expected_checksum=sample_checksum,
            content_type=content_type,
            metadata={"custom_key": "custom_value"}
        )

        # THEN
        assert result["storage_ref"] == storage_ref
        assert result["checksum"] == sample_checksum
        assert result["size"] == 35
        assert "uploaded_at" in result

        # Verify file exists on disk
        file_path = storage_service._get_full_path(storage_ref)
        assert file_path.exists()

    @pytest.mark.asyncio
    async def test_upload_checksum_mismatch(self, storage_service, sample_file_data):
        """
        GIVEN a file with incorrect checksum
        WHEN uploading to storage
        THEN should raise StorageChecksumMismatchError
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/doc_456/v1/test.txt"
        wrong_checksum = "0000000000000000000000000000000000000000000000000000000000000000"

        # WHEN/THEN
        with pytest.raises(StorageChecksumMismatchError) as exc_info:
            await storage_service.upload(
                file_data=sample_file_data,
                storage_ref=storage_ref,
                expected_checksum=wrong_checksum,
                content_type="text/plain"
            )

        assert "Checksum mismatch" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_upload_idempotent_same_checksum(
        self, storage_service, sample_file_data, sample_checksum
    ):
        """
        GIVEN a file already uploaded with same checksum
        WHEN uploading again with same checksum
        THEN should return existing file metadata (idempotent)
        """
        # GIVEN - Upload file first time
        storage_ref = "tenants/acme/documents/doc_789/v1/test.txt"
        first_result = await storage_service.upload(
            file_data=sample_file_data,
            storage_ref=storage_ref,
            expected_checksum=sample_checksum,
            content_type="text/plain"
        )

        # WHEN - Upload same file again
        sample_file_data.seek(0)  # Reset file pointer
        second_result = await storage_service.upload(
            file_data=sample_file_data,
            storage_ref=storage_ref,
            expected_checksum=sample_checksum,
            content_type="text/plain"
        )

        # THEN - Should return same metadata (idempotent)
        assert second_result["checksum"] == first_result["checksum"]
        assert second_result["size"] == first_result["size"]

    @pytest.mark.asyncio
    async def test_upload_rejects_different_checksum(
        self, storage_service, sample_file_data, sample_checksum
    ):
        """
        GIVEN a file already exists with different checksum
        WHEN uploading with different content
        THEN should raise StorageAlreadyExistsError
        """
        # GIVEN - Upload file first time
        storage_ref = "tenants/acme/documents/doc_abc/v1/test.txt"
        await storage_service.upload(
            file_data=sample_file_data,
            storage_ref=storage_ref,
            expected_checksum=sample_checksum,
            content_type="text/plain"
        )

        # WHEN - Try to upload different content to same path
        different_content = io.BytesIO(b"Different content")
        different_checksum = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"

        # THEN
        with pytest.raises(StorageAlreadyExistsError):
            await storage_service.upload(
                file_data=different_content,
                storage_ref=storage_ref,
                expected_checksum=different_checksum,
                content_type="text/plain"
            )


class TestLocalStoragePathSecurity:
    """Tests for path traversal protection."""

    @pytest.mark.asyncio
    async def test_path_traversal_prevention(self, storage_service, sample_file_data):
        """
        GIVEN a malicious storage_ref with path traversal attempt
        WHEN trying to upload
        THEN should raise StoragePermissionError
        """
        # GIVEN - Malicious path attempting to escape storage root
        malicious_refs = [
            "../../../etc/passwd",
            "tenants/../../etc/passwd",
            "tenants/acme/../../../etc/passwd",
            "tenants/acme/documents/../../../../../etc/passwd"
        ]

        # WHEN/THEN
        for malicious_ref in malicious_refs:
            with pytest.raises(StoragePermissionError) as exc_info:
                await storage_service.upload(
                    file_data=sample_file_data,
                    storage_ref=malicious_ref,
                    expected_checksum="dummy",
                    content_type="text/plain"
                )
            assert "Path traversal detected" in str(exc_info.value)
            sample_file_data.seek(0)  # Reset for next iteration

    def test_get_full_path_security(self, storage_service):
        """
        GIVEN various storage_ref paths
        WHEN resolving to full paths
        THEN should validate all paths are within storage root
        """
        # GIVEN
        valid_refs = [
            "tenants/acme/documents/doc_1/v1/file.txt",
            "tenants/acme/documents/doc_2/v2/file.pdf"
        ]
        invalid_refs = [
            "../../../etc/passwd",
            "tenants/../../secret.txt"
        ]

        # WHEN/THEN - Valid paths should succeed
        for ref in valid_refs:
            path = storage_service._get_full_path(ref)
            assert str(path).startswith(storage_service.storage_root.as_posix())

        # WHEN/THEN - Invalid paths should raise error
        for ref in invalid_refs:
            with pytest.raises(StoragePermissionError):
                storage_service._get_full_path(ref)


class TestLocalStorageDownload:
    """Tests for LocalStorageService download functionality."""

    @pytest.mark.asyncio
    async def test_download_success(self, storage_service, sample_file_data, sample_checksum):
        """
        GIVEN an uploaded file
        WHEN downloading
        THEN should stream file content correctly
        """
        # GIVEN - Upload file first
        storage_ref = "tenants/acme/documents/doc_123/v1/test.txt"
        await storage_service.upload(
            file_data=sample_file_data,
            storage_ref=storage_ref,
            expected_checksum=sample_checksum,
            content_type="text/plain"
        )

        # WHEN - Download file
        chunks = []
        async for chunk in storage_service.download(storage_ref):
            chunks.append(chunk)

        downloaded_content = b"".join(chunks)

        # THEN - Content should match original
        sample_file_data.seek(0)
        assert downloaded_content == sample_file_data.read()

    @pytest.mark.asyncio
    async def test_download_file_not_found(self, storage_service):
        """
        GIVEN a non-existent storage_ref
        WHEN trying to download
        THEN should raise StorageNotFoundError
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/nonexistent/v1/test.txt"

        # WHEN/THEN
        with pytest.raises(StorageNotFoundError) as exc_info:
            async for _ in storage_service.download(storage_ref):
                pass

        assert "File not found" in str(exc_info.value)


class TestLocalStorageMetadata:
    """Tests for metadata operations."""

    @pytest.mark.asyncio
    async def test_get_metadata(self, storage_service, sample_file_data, sample_checksum):
        """
        GIVEN an uploaded file with metadata
        WHEN retrieving metadata
        THEN should return correct file information
        """
        # GIVEN - Upload file with custom metadata
        storage_ref = "tenants/acme/documents/doc_123/v1/test.txt"
        custom_metadata = {"author": "test_user", "version": "1"}

        await storage_service.upload(
            file_data=sample_file_data,
            storage_ref=storage_ref,
            expected_checksum=sample_checksum,
            content_type="text/plain",
            metadata=custom_metadata
        )

        # WHEN - Get metadata
        metadata = await storage_service.get_metadata(storage_ref)

        # THEN - Should contain file info
        assert metadata["size"] == 35
        assert metadata["content_type"] == "text/plain"
        assert metadata["checksum"] == sample_checksum
        assert "last_modified" in metadata
        assert metadata["custom"]["author"] == "test_user"

    @pytest.mark.asyncio
    async def test_exists_true(self, storage_service, sample_file_data, sample_checksum):
        """
        GIVEN an uploaded file
        WHEN checking if exists
        THEN should return True
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/doc_123/v1/test.txt"
        await storage_service.upload(
            file_data=sample_file_data,
            storage_ref=storage_ref,
            expected_checksum=sample_checksum,
            content_type="text/plain"
        )

        # WHEN/THEN
        assert await storage_service.exists(storage_ref) is True

    @pytest.mark.asyncio
    async def test_exists_false(self, storage_service):
        """
        GIVEN a non-existent file
        WHEN checking if exists
        THEN should return False
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/nonexistent/v1/test.txt"

        # WHEN/THEN
        assert await storage_service.exists(storage_ref) is False


class TestLocalStorageDelete:
    """Tests for delete functionality."""

    @pytest.mark.asyncio
    async def test_delete_success(self, storage_service, sample_file_data, sample_checksum):
        """
        GIVEN an uploaded file
        WHEN deleting
        THEN file and metadata should be removed
        """
        # GIVEN - Upload file
        storage_ref = "tenants/acme/documents/doc_123/v1/test.txt"
        await storage_service.upload(
            file_data=sample_file_data,
            storage_ref=storage_ref,
            expected_checksum=sample_checksum,
            content_type="text/plain"
        )

        # WHEN - Delete file
        result = await storage_service.delete(storage_ref)

        # THEN - Should return True and file should not exist
        assert result is True
        assert await storage_service.exists(storage_ref) is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file(self, storage_service):
        """
        GIVEN a non-existent file
        WHEN trying to delete
        THEN should return False (idempotent)
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/nonexistent/v1/test.txt"

        # WHEN
        result = await storage_service.delete(storage_ref)

        # THEN
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_cleans_empty_directories(
        self, storage_service, sample_file_data, sample_checksum, temp_storage_root
    ):
        """
        GIVEN an uploaded file in nested directories
        WHEN deleting the file
        THEN empty parent directories should be cleaned up
        """
        # GIVEN - Upload file
        storage_ref = "tenants/acme/documents/doc_123/v1/test.txt"
        await storage_service.upload(
            file_data=sample_file_data,
            storage_ref=storage_ref,
            expected_checksum=sample_checksum,
            content_type="text/plain"
        )

        # WHEN - Delete file
        await storage_service.delete(storage_ref)

        # THEN - Parent directories should be cleaned if empty
        storage_root = Path(temp_storage_root)
        doc_dir = storage_root / "tenants" / "acme" / "documents" / "doc_123" / "v1"

        # The v1 directory should be removed
        assert not doc_dir.exists()


class TestLocalStoragePresignedURLs:
    """Tests for pre-signed URL generation."""

    @pytest.mark.asyncio
    async def test_generate_download_url_not_supported(self, storage_service):
        """
        GIVEN local storage backend
        WHEN trying to generate pre-signed URL
        THEN should raise StorageNotSupportedError
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/doc_123/v1/test.txt"

        # WHEN/THEN
        from core.exceptions import StorageNotSupportedError
        with pytest.raises(StorageNotSupportedError) as exc_info:
            await storage_service.generate_download_url(storage_ref)

        assert "Local storage doesn't support pre-signed URLs" in str(exc_info.value)


class TestLocalStorageAtomicWrites:
    """Tests for atomic write operations."""

    @pytest.mark.asyncio
    async def test_atomic_write_on_failure(
        self, storage_service, sample_file_data, temp_storage_root
    ):
        """
        GIVEN an upload that will fail checksum validation
        WHEN upload fails
        THEN no partial files should remain in storage
        """
        # GIVEN
        storage_ref = "tenants/acme/documents/doc_123/v1/test.txt"
        wrong_checksum = "0" * 64
        storage_root = Path(temp_storage_root)

        # WHEN - Upload will fail due to checksum mismatch
        try:
            await storage_service.upload(
                file_data=sample_file_data,
                storage_ref=storage_ref,
                expected_checksum=wrong_checksum,
                content_type="text/plain"
            )
        except StorageChecksumMismatchError:
            pass

        # THEN - No files should exist in storage (atomic rollback)
        target_path = storage_service._get_full_path(storage_ref)
        assert not target_path.exists()

        # No temp files should remain
        parent_dir = target_path.parent
        if parent_dir.exists():
            temp_files = list(parent_dir.glob(".tmp_*"))
            assert len(temp_files) == 0
