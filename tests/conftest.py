"""Shared test fixtures for pytest"""
import asyncio
import sys
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.auth import create_access_token, get_password_hash
from core.database import Base, get_db
from main import app
from models.subject import Subject
from models.tenant import Tenant
from models.user import User

# Test database URL - use a separate test database
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost/timeline_test"

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_engine():
    """Create test database engine"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def test_db(test_engine):
    """Create test database session"""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with async_session() as session:
        yield session


@pytest.fixture
async def client(test_db):
    """HTTP client for API testing"""
    from httpx import ASGITransport

    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def test_tenant(test_db):
    """Create test tenant"""
    tenant = Tenant(
        id="test-tenant-id",
        code="TEST",
        name="Test Tenant",
        status="active",
        is_active=True,
    )
    test_db.add(tenant)
    await test_db.commit()
    await test_db.refresh(tenant)
    return tenant


@pytest.fixture
async def test_user(test_db, test_tenant):
    """Create test user"""
    user = User(
        id="test-user-id",
        tenant_id=test_tenant.id,
        username="testuser",
        email="test@example.com",
        password_hash=get_password_hash("testpass123"),
        is_active=True,
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_tenant, test_user):
    """Generate auth headers with JWT token"""
    token = create_access_token(data={"sub": test_user.id, "tenant_id": test_tenant.id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def test_subject(test_db, test_tenant):
    """Create test subject"""
    subject = Subject(
        id="test-subject-id",
        tenant_id=test_tenant.id,
        subject_type="user",
        external_ref="test-user-123",
    )
    test_db.add(subject)
    await test_db.commit()
    await test_db.refresh(subject)
    return subject
