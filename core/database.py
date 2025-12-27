import os
from sqlalchemy.ext.asyncio import(
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base
from core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_size = 20,
    max_overflow = 30,
    pool_recycle = 3600,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_= AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)

Base = declarative_base()

async def get_db():
    """
    Database session dependency for read operations.
    Does not commit - read-only operations don't need commits.
    Write operations should use get_db_transactional().

    Note: async with context manager handles session cleanup automatically.
    """
    async with AsyncSessionLocal() as session:
        yield session


async def get_db_transactional():
    """
    Database session dependency for write operations.
    Uses async_sessionmaker.begin() for atomic transaction management:
    - Begins transaction automatically
    - Commits on success
    - Rolls back on exception
    - Closes session automatically

    Use this for POST, PUT, PATCH, DELETE endpoints.
    """
    async with AsyncSessionLocal.begin() as session:
        yield session