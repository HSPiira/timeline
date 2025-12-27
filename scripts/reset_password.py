"""Reset password for existing user"""
import asyncio
import sys
from sqlalchemy import select
from core.database import AsyncSessionLocal
from models.user import User
from core.auth import get_password_hash


async def reset_password(username: str, tenant_code: str, new_password: str):
    async with AsyncSessionLocal() as db:
        from models.tenant import Tenant

        # Get tenant
        result = await db.execute(
            select(Tenant).where(Tenant.code == tenant_code)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            print(f"❌ Tenant '{tenant_code}' not found")
            return

        # Get user
        result = await db.execute(
            select(User).where(
                User.username == username,
                User.tenant_id == tenant.id
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            print(f"❌ User '{username}' not found in tenant '{tenant_code}'")
            return

        # Update password
        user.hashed_password = get_password_hash(new_password)
        await db.commit()

        print(f"✅ Password reset successful!")
        print(f"\nLogin credentials:")
        print(f"  Username: {username}")
        print(f"  Password: {new_password}")
        print(f"  Tenant Code: {tenant_code}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python -m scripts.reset_password <username> <tenant_code> <new_password>")
        print("Example: python -m scripts.reset_password admin taoshi newpass123")
        sys.exit(1)

    username, tenant_code, new_password = sys.argv[1:]
    asyncio.run(reset_password(username, tenant_code, new_password))
