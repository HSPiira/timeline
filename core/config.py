import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from functools import lru_cache
from typing import Optional                                                                                                                                                       
                                                                                                                                                                                        
class Settings(BaseSettings):
    # App
    app_name: str = "Timeline"
    app_version: str = "1.0.0"
    debug: bool = False

    # Database
    database_url: str
    database_echo: bool = False

    # Security
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 hours
    encryption_salt: str = os.getenv("ENCRYPTION_SALT")

    # CORS - comma-separated list of allowed origins
    allowed_origins: str = "http://localhost:3000,http://localhost:8080"

    # Storage
    storage_backend: str = "local"  # Options: "local", "s3"
    storage_root: str = "/var/timeline/storage"  # For local backend
    s3_bucket: Optional[str] = None  # Required for S3 backend
    s3_region: str = "us-east-1"
    s3_endpoint_url: Optional[str] = None  # For MinIO/LocalStack
    s3_access_key: Optional[str] = None  # Optional, uses IAM role if not provided
    s3_secret_key: Optional[str] = None  # Optional, uses IAM role if not provided
    max_upload_size: int = 100 * 1024 * 1024  # 100MB default
    allowed_mime_types: str = "*/*"  # Or comma-separated list

    # Tenant
    tenant_header_name: str = "X-Tenant-ID"

    # Redis Cache
    redis_enabled: bool = True  # Enable/disable caching
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_max_connections: int = 10

    # Cache TTL (Time-To-Live) in seconds
    cache_ttl_permissions: int = 300  # 5 minutes
    cache_ttl_schemas: int = 600  # 10 minutes
    cache_ttl_tenants: int = 900  # 15 minutes

    # OpenTelemetry Distributed Tracing
    telemetry_enabled: bool = True  # Enable/disable distributed tracing
    telemetry_exporter: str = "console"  # Options: "console", "otlp", "jaeger", "none"
    telemetry_otlp_endpoint: Optional[str] = None  # e.g., "http://localhost:4317"
    telemetry_jaeger_endpoint: Optional[str] = "localhost"  # Jaeger agent host
    telemetry_sample_rate: float = 1.0  # Sampling rate (0.0-1.0, 1.0 = 100%)
    telemetry_environment: str = "development"  # deployment environment tag

    @model_validator(mode='after')
    def validate_storage_config(self) -> 'Settings':
        """Validate storage backend configuration"""
        if self.storage_backend == 's3':
            if not self.s3_bucket:
                raise ValueError(
                    "s3_bucket is required when storage_backend is 's3'. "
                    "Set S3_BUCKET environment variable or update .env file."
                )
            # Note: s3_access_key and s3_secret_key are optional
            # If not provided, AWS SDK will attempt to use IAM role/instance profile
        elif self.storage_backend not in ('local', 's3'):
            raise ValueError(
                f"Invalid storage_backend '{self.storage_backend}'. "
                f"Must be one of: 'local', 's3'"
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        case_sensitive=False
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()