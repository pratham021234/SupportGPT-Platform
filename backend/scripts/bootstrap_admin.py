"""SupportGPT AI — Initial Administrator & Organization Provisioning Script.

Seeds the root tenant organization and administrative user account.
Can be executed repeatedly without corrupting existing records (idempotent).
"""

import argparse
import asyncio
import sys
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import settings
from app.core.security import hash_password, normalize_email
from app.models.enums import MembershipRole, MembershipStatus, OrganizationStatus, UserStatus
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.user import User


async def bootstrap_organization_and_admin(
    org_name: str,
    admin_email: str,
    display_name: str,
    password: str,
    role: str = "owner",
    db_url_override: str | None = None,
) -> dict:
    """Provision or update organization, administrator user, and membership."""
    db_url = db_url_override or settings.DATABASE_URL
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    normalized_email = normalize_email(admin_email)
    role_enum = MembershipRole(role.lower())

    async with session_factory() as db:
        # 1. Organization
        org_slug = org_name.lower().replace(" ", "-").replace("_", "-")
        query_org = select(Organization).where(Organization.slug == org_slug)
        res_org = await db.execute(query_org)
        org = res_org.scalar_one_or_none()

        if not org:
            org = Organization(
                name=org_name,
                slug=org_slug,
                status=OrganizationStatus.ACTIVE,
            )
            db.add(org)
            await db.flush()
            print(f"[+] Created organization: '{org.name}' (ID: {org.id}, Slug: {org.slug})")
        else:
            print(f"[*] Found existing organization: '{org.name}' (ID: {org.id})")

        # 2. User
        query_user = select(User).where(User.email == normalized_email)
        res_user = await db.execute(query_user)
        user = res_user.scalar_one_or_none()

        if not user:
            user = User(
                email=normalized_email,
                password_hash=hash_password(password),
                display_name=display_name,
                status=UserStatus.ACTIVE,
            )
            db.add(user)
            await db.flush()
            print(f"[+] Created user: '{user.email}' (ID: {user.id})")
        else:
            user.password_hash = hash_password(password)
            user.display_name = display_name
            user.status = UserStatus.ACTIVE
            await db.flush()
            print(f"[*] Updated existing user: '{user.email}' (ID: {user.id})")

        # 3. Membership
        query_mem = select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org.id,
            OrganizationMembership.user_id == user.id,
        )
        res_mem = await db.execute(query_mem)
        membership = res_mem.scalar_one_or_none()

        if not membership:
            membership = OrganizationMembership(
                organization_id=org.id,
                user_id=user.id,
                role=role_enum,
                status=MembershipStatus.ACTIVE,
            )
            db.add(membership)
            await db.flush()
            print(f"[+] Provisioned membership: User '{user.email}' as '{role_enum.value}' in '{org.name}'")
        else:
            membership.role = role_enum
            membership.status = MembershipStatus.ACTIVE
            await db.flush()
            print(f"[*] Updated membership: User '{user.email}' as '{role_enum.value}' in '{org.name}'")

        await db.commit()

    await engine.dispose()
    return {
        "organization_id": str(org.id),
        "organization_slug": org.slug,
        "user_id": str(user.id),
        "user_email": user.email,
        "role": role_enum.value,
    }


def main():
    parser = argparse.ArgumentParser(description="SupportGPT Administrator Provisioning Utility")
    parser.add_argument("--org-name", required=True, help="Organization name (e.g. 'Acme Support')")
    parser.add_argument("--admin-email", required=True, help="Administrator email (e.g. 'admin@acme.com')")
    parser.add_argument("--display-name", default=None, help="Display name for admin")
    parser.add_argument("--password", required=True, help="Administrator password")
    parser.add_argument("--role", default="owner", choices=["owner", "admin", "agent", "viewer"], help="Membership role")
    parser.add_argument("--db-url", default=None, help="Database URL override")
    args = parser.parse_args()

    display_name = args.display_name or args.org_name + " Admin"

    try:
        res = asyncio.run(
            bootstrap_organization_and_admin(
                org_name=args.org_name,
                admin_email=args.admin_email,
                display_name=display_name,
                password=args.password,
                role=args.role,
                db_url_override=args.db_url,
            )
        )
        print("[SUCCESS] Provisioning completed:", res)
    except Exception as e:
        print(f"[ERROR] Provisioning failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
