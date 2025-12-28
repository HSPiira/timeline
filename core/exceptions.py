class TimelineException(Exception):
    """Base exception"""

    pass


class TenantNotFoundException(TimelineException):
    """Tenant not found"""

    pass


class EventChainBrokenException(TimelineException):
    """Event chain integrity violated"""

    pass


class SchemaValidationException(TimelineException):
    """Schema validation failed"""


class PermissionDeniedError(TimelineException):
    """Permission denied - user lacks required permission"""

    pass


# Storage Exceptions
class StorageException(TimelineException):
    """Base exception for storage operations"""

    pass


class StorageNotFoundError(StorageException):
    """File not found in storage"""

    pass


class StorageUploadError(StorageException):
    """File upload failed"""

    pass


class StorageDownloadError(StorageException):
    """File download failed"""

    pass


class StorageDeleteError(StorageException):
    """File deletion failed"""

    pass


class StorageChecksumMismatchError(StorageException):
    """Checksum validation failed - file corrupted or tampered"""

    pass


class StorageAlreadyExistsError(StorageException):
    """File already exists with different checksum"""

    pass


class StorageNotSupportedError(StorageException):
    """Operation not supported by this storage backend"""

    pass


class StorageQuotaExceededError(StorageException):
    """Storage quota exceeded"""

    pass


class StoragePermissionError(StorageException):
    """Insufficient permissions for storage operation (e.g., path traversal detected)"""

    pass
