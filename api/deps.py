from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, get_db_transactional
from core.auth import verify_token
from models.tenant import Tenant
from repositories.tenant_repo import TenantRepository
from repositories.event_repo import EventRepository
from repositories.subject_repo import SubjectRepository
from repositories.document_repo import DocumentRepository
from services.event_service import EventService
from services.hash_service import HashService
from schemas.token import TokenPayload

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenPayload:
    """
    Validate JWT token and return authenticated user payload.
    Token must contain 'sub' (user_id) and 'tenant_id' claims.
    """
    try:
        payload = verify_token(credentials.credentials)
        token_data = TokenPayload(**payload)
        return token_data
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_tenant(
    user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    """
    Get current tenant from authenticated user's token claims.
    Tenant ID is derived from JWT token, preventing header spoofing attacks.
    """
    tenant = await TenantRepository(db).get_by_id(user.tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant not found or access denied"
        )
    return tenant


async def get_event_service(
    db: AsyncSession = Depends(get_db)
) -> EventService:
    """Event service dependency"""
    return EventService(
        event_repo=EventRepository(db),
        hash_service=HashService()
    )


async def get_subject_repo(
    db: AsyncSession = Depends(get_db)
) -> SubjectRepository:
    """Subject repository dependency"""
    return SubjectRepository(db)


async def get_event_repo(
    db: AsyncSession = Depends(get_db)
) -> EventRepository:
    """Event repository dependency"""
    return EventRepository(db)


async def get_tenant_repo(
    db: AsyncSession = Depends(get_db)
) -> TenantRepository:
    """Tenant repository dependency"""
    return TenantRepository(db)


async def get_document_repo(
    db: AsyncSession = Depends(get_db)
) -> DocumentRepository:
    """Document repository dependency"""
    return DocumentRepository(db)


# Transactional dependencies for write operations
async def get_event_service_transactional(
    db: AsyncSession = Depends(get_db_transactional)
) -> EventService:
    """Event service dependency with transaction management"""
    return EventService(
        event_repo=EventRepository(db),
        hash_service=HashService()
    )


async def get_subject_repo_transactional(
    db: AsyncSession = Depends(get_db_transactional)
) -> SubjectRepository:
    """Subject repository dependency with transaction management"""
    return SubjectRepository(db)


async def get_tenant_repo_transactional(
    db: AsyncSession = Depends(get_db_transactional)
) -> TenantRepository:
    """Tenant repository dependency with transaction management"""
    return TenantRepository(db)


async def get_document_repo_transactional(
    db: AsyncSession = Depends(get_db_transactional)
) -> DocumentRepository:
    """Document repository dependency with transaction management"""
    return DocumentRepository(db)