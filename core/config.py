from pydantic_settings import BaseSettings, SettingsConfigDict
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
    access_token_expire_minutes: int = 30

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
                                                                                                                                                                                    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        case_sensitive=False
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()