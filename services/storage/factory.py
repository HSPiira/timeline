"""Storage service factory for backend selection."""
from core.storage_protocols import IStorageService
from services.storage.local_storage import LocalStorageService


class StorageFactory:
    """Factory for creating storage service instances based on configuration."""

    @staticmethod
    def create_storage_service(settings) -> IStorageService:
        """
        Create storage service based on settings.

        Args:
            settings: Application settings with storage configuration

        Returns:
            IStorageService: Configured storage service

        Raises:
            ValueError: If unknown backend or missing required config
        """
        backend = settings.storage_backend.lower()

        if backend == "local":
            if not settings.storage_root:
                raise ValueError("STORAGE_ROOT required for local backend")
            return LocalStorageService(storage_root=settings.storage_root)

        elif backend == "s3":
            # Import here to avoid dependency if not using S3
            from services.storage.s3_storage import S3StorageService

            if not settings.s3_bucket:
                raise ValueError("S3_BUCKET required for s3 backend")

            return S3StorageService(
                bucket=settings.s3_bucket,
                region=settings.s3_region,
                endpoint_url=settings.s3_endpoint_url,
                access_key=settings.s3_access_key,
                secret_key=settings.s3_secret_key,
            )

        else:
            raise ValueError(
                f"Unknown storage backend: {backend}. " f"Supported: 'local', 's3'"
            )
