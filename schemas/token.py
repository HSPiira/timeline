from pydantic import BaseModel, Field


class TokenPayload(BaseModel):
    """JWT token payload schema with tenant and user information"""
    sub: str = Field(..., description="User ID (subject)")
    tenant_id: str = Field(..., description="Tenant ID the user belongs to")
    exp: int = Field(..., description="Token expiration timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "sub": "user_123",
                "tenant_id": "tenant_abc",
                "exp": 1234567890
            }
        }


class Token(BaseModel):
    """Access token response"""
    access_token: str
    token_type: str = "bearer"


class TokenRequest(BaseModel):
    """Token request (for login)"""
    username: str
    password: str
    tenant_code: str = Field(..., description="Tenant code for multi-tenant isolation")
