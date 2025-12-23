"""Create a test user with known credentials for development"""
import asyncio
from sqlalchemy import select
from core.database import AsyncSessionLocal
from models.tenant import Tenant
from models.user import User
from repositories.user_repo import UserRepository
from schemas.user import UserCreate


async def create_test_user():
    async with AsyncSessionLocal() as db:
        # Get taoshi tenant
        result = await db.execute(
            select(Tenant).where(Tenant.code == "taoshi")
        )
        tenant = result.scalar_one_or_none()

        if not tenant:
            print("Tenant 'taoshi' not found")
            return

        # Check if testuser exists
        result = await db.execute(
            select(User).where(
                User.username == "testuser",
                User.tenant_id == tenant.id
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            print("User 'testuser' already exists for taoshi tenant")
            print("\nLogin with:")
            print(f"  Username: testuser")
            print(f"  Password: testpass123")
            print(f"  Tenant Code: taoshi")
            return

        # Create new user
        user_repo = UserRepository(db)
        user = await user_repo.create_user(
            tenant_id=tenant.id,
            username="testuser",
            email="testuser@taoshi.com",
            password="testpass123"
        )
        await db.commit()

        print("✅ Test user created successfully!")
        print("\nLogin credentials:")
        print(f"  Username: testuser")
        print(f"  Password: testpass123")
        print(f"  Tenant Code: taoshi")
        print("\nTest login:")
        print("""
curl -X POST http://localhost:8000/auth/token \\
  -H "Content-Type: application/json" \\
  -d '{
    "username": "testuser",
    "password": "testpass123",
    "tenant_code": "taoshi"
  }'
        """)


if __name__ == "__main__":
    asyncio.run(create_test_user())
