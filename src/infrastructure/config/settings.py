from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    app_name: str = "Timeline"
    app_version: str = "1.0.0"
    debug: bool = False

    # Database
    database_url: str = ""  # Loaded from environment, validated in model_validator
    database_echo: bool = False

    # Security
    secret_key: str = ""  # Loaded from environment, validated in model_validator
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 hours
    encryption_salt: str = ""  # Loaded from environment, validated in model_validator

    # CORS - comma-separated list of allowed origins
    allowed_origins: str = "http://localhost:3000,http://localhost:8080"

    # Storage
    storage_backend: str = "local"  # Options: "local", "s3"
    storage_root: str = "/var/timeline/storage"  # For local backend
    storage_base_url: str | None = None  # Base URL for download links (e.g., "https://api.example.com")
    s3_bucket: str | None = None  # Required for S3 backend
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = None  # For MinIO/LocalStack
    s3_access_key: str | None = None  # Optional, uses IAM role if not provided
    s3_secret_key: str | None = None  # Optional, uses IAM role if not provided
    max_upload_size: int = 100 * 1024 * 1024  # 100MB default
    allowed_mime_types: str = "*/*"  # Or comma-separated list

    # Tenant
    tenant_header_name: str = "X-Tenant-ID"

    # Redis Cache
    redis_enabled: bool = True  # Enable/disable caching
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    redis_max_connections: int = 10

    # Cache TTL (Time-To-Live) in seconds
    cache_ttl_permissions: int = 300  # 5 minutes
    cache_ttl_schemas: int = 600  # 10 minutes
    cache_ttl_tenants: int = 900  # 15 minutes

    # OpenTelemetry Distributed Tracing
    telemetry_enabled: bool = True  # Enable/disable distributed tracing
    telemetry_exporter: str = "console"  # Options: "console", "otlp", "jaeger", "none"
    telemetry_otlp_endpoint: str | None = None  # e.g., "http://localhost:4317"
    telemetry_jaeger_endpoint: str | None = (
        "localhost"  # Jaeger agent host (default: localhost if enabled)
    )
    telemetry_sample_rate: float = 1.0  # Sampling rate (0.0-1.0, 1.0 = 100%)
    telemetry_environment: str = "development"  # deployment environment tag

    @model_validator(mode="after")
    def validate_storage_config(self) -> "Settings":
        """Validate storage backend and required configuration"""
        # Validate required fields are loaded from environment
        if not self.database_url:
            raise ValueError("DATABASE_URL is required. Set in environment or .env file.")
        if not self.secret_key:
            raise ValueError("SECRET_KEY is required. Generate with: openssl rand -hex 32")
        if not self.encryption_salt:
            raise ValueError("ENCRYPTION_SALT is required. Generate with: openssl rand -hex 16")

        # Validate storage backend
        if self.storage_backend == "s3":
            if not self.s3_bucket:
                raise ValueError(
                    "s3_bucket is required when storage_backend is 's3'. "
                    "Set S3_BUCKET environment variable or update .env file."
                )
            # Note: s3_access_key and s3_secret_key are optional
            # If not provided, AWS SDK will attempt to use IAM role/instance profile
        elif self.storage_backend not in ("local", "s3"):
            raise ValueError(
                f"Invalid storage_backend '{self.storage_backend}'. "
                f"Must be one of: 'local', 's3'"
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="allow", case_sensitive=False
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
