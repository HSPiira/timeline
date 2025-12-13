from pydantic_settings import BaseSettings, SettingsConfigDict                                                                                                                                            
from functools import lru_cache                                                                                                                                                       
                                                                                                                                                                                        
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

    # Storage
    s3_bucket: str
    s3_region: str = "us-east-1"

    # Tenant
    tenant_header_name: str = "X-Tenant-ID"                                                                                                                                         
                                                                                                                                                                                    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()