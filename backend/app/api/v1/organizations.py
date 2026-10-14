"""Organization workspace and membership administration endpoints."""

import uuid

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import (
    OrganizationContext,
    get_current_user,
    get_organization_context,
    require_permission,
)
from app.core.errors import (
    ConflictException,
    ForbiddenException,
    ResourceNotFoundException,
)
from app.core.logging import get_logger
from app.core.rbac import (
    ROLE_PERMISSIONS,
    Permission,
    can_assign_role,
    can_manage_membership,
)
from app.core.security import hash_password, normalize_email
from app.db.session import get_db_session
from app.models.enums import MembershipRole, MembershipStatus, UserStatus
from app.models.membership import OrganizationMembership
from app.models.user import User
from app.schemas.auth import UserOrganizationSummary
from app.schemas.membership import (
    AddMemberRequest,
    MemberResponse,
    MembershipDetailResponse,
    UpdateMemberRoleRequest,
)

logger = get_logger("supportgpt.organizations")
router = APIRouter(prefix="/organizations", tags=["Organizations & Memberships"])


@router.get(
    "",
    response_model=list[UserOrganizationSummary],
    status_code=status.HTTP_200_OK,
    summary="List organizations accessible to the current user",
)
async def list_user_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[UserOrganizationSummary]:
    """Retrieve all organizations where the caller holds an active membership."""
    query = (
        select(OrganizationMembership)
        .options(selectinload(OrganizationMembership.organization))
        .where(
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.status == MembershipStatus.ACTIVE,
        )
    )
    result = await db.execute(query)
    memberships = result.scalars().all()

    return [
        UserOrganizationSummary(
            organization_id=m.organization_id,
            name=m.organization.name,
            slug=m.organization.slug,
            role=m.role,
            status=m.status,
        )
        for m in memberships
        if m.organization and m.organization.deleted_at is None
    ]


@router.get(
    "/{organization_id}/memberships/me",
    response_model=MembershipDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve caller's membership details and permissions for target organization",
)
async def get_my_membership(
    context: OrganizationContext = Depends(get_organization_context),
) -> MembershipDetailResponse:
    """Return caller's role, status, and permissions within the authorized organization."""
    permissions = [p.value for p in ROLE_PERMISSIONS.get(context.role, set())]

    return MembershipDetailResponse(
        id=context.membership.id,
        organization_id=context.organization.id,
        organization_name=context.organization.name,
        organization_slug=context.organization.slug,
        user_id=context.user.id,
        role=context.role,
        status=context.membership.status,
        permissions=permissions,
        created_at=context.membership.created_at,
    )


@router.get(
    "/{organization_id}/members",
    response_model=list[MemberResponse],
    status_code=status.HTTP_200_OK,
    summary="List members of an organization",
)
async def list_organization_members(
    context: OrganizationContext = Depends(require_permission(Permission.ORG_MEMBERS_READ)),
    db: AsyncSession = Depends(get_db_session),
) -> list[MemberResponse]:
    """List all registered members within the active organization."""
    query = (
        select(OrganizationMembership)
        .options(selectinload(OrganizationMembership.user))
        .where(OrganizationMembership.organization_id == context.organization.id)
        .order_by(OrganizationMembership.created_at.asc())
    )
    result = await db.execute(query)
    members = result.scalars().all()

    return [
        MemberResponse(
            id=m.id,
            organization_id=m.organization_id,
            user_id=m.user_id,
            email=m.user.email,
            display_name=m.user.display_name,
            role=m.role,
            status=m.status,
            created_at=m.created_at,
        )
        for m in members
        if m.user is not None
    ]


@router.post(
    "/{organization_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add or invite a new member to the organization",
)
async def add_organization_member(
    payload: AddMemberRequest,
    context: OrganizationContext = Depends(require_permission(Permission.ORG_MEMBERS_MANAGE)),
    db: AsyncSession = Depends(get_db_session),
) -> MemberResponse:
    """Provision a membership for a user under strict role-escalation checks."""
    # 1. Enforce role escalation prevention
    if not can_assign_role(context.role, payload.role):
        raise ForbiddenException(
            f"Role '{context.role}' is not authorized to assign the privileged '{payload.role}' role."
        )

    normalized_email = normalize_email(payload.email)

    # 2. Find or create user account
    user_query = select(User).where(User.email == normalized_email)
    user_res = await db.execute(user_query)
    target_user = user_res.scalar_one_or_none()

    if not target_user:
        # Create uninitialized user with randomized temporary credential
        random_temp_password = uuid.uuid4().hex + uuid.uuid4().hex
        target_user = User(
            email=normalized_email,
            password_hash=hash_password(random_temp_password),
            display_name=payload.display_name,
            status=UserStatus.ACTIVE,
        )
        db.add(target_user)
        await db.flush()

    # 3. Check for existing membership
    existing_query = select(OrganizationMembership).where(
        OrganizationMembership.organization_id == context.organization.id,
        OrganizationMembership.user_id == target_user.id,
    )
    existing_res = await db.execute(existing_query)
    existing_membership = existing_res.scalar_one_or_none()

    if existing_membership:
        if existing_membership.status == MembershipStatus.ACTIVE:
            raise ConflictException(
                f"User '{normalized_email}' is already an active member of this organization."
            )
        # Reactivate existing revoked/suspended membership
        existing_membership.role = payload.role
        existing_membership.status = MembershipStatus.ACTIVE
        await db.flush()
        return MemberResponse(
            id=existing_membership.id,
            organization_id=context.organization.id,
            user_id=target_user.id,
            email=target_user.email,
            display_name=target_user.display_name,
            role=existing_membership.role,
            status=existing_membership.status,
            created_at=existing_membership.created_at,
        )

    # 4. Create new membership
    membership = OrganizationMembership(
        organization_id=context.organization.id,
        user_id=target_user.id,
        role=payload.role,
        status=MembershipStatus.ACTIVE,
        invited_by_user_id=context.user.id,
    )
    db.add(membership)
    await db.flush()

    logger.info(
        f"Member added: user={target_user.id} org={context.organization.id} role={payload.role} by={context.user.id}"
    )

    return MemberResponse(
        id=membership.id,
        organization_id=context.organization.id,
        user_id=target_user.id,
        email=target_user.email,
        display_name=target_user.display_name,
        role=membership.role,
        status=membership.status,
        created_at=membership.created_at,
    )


@router.patch(
    "/{organization_id}/members/{membership_id}",
    response_model=MemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an organization member's role",
)
async def update_member_role(
    payload: UpdateMemberRoleRequest,
    membership_id: uuid.UUID = Path(..., description="UUID of the membership to modify"),
    context: OrganizationContext = Depends(require_permission(Permission.ORG_MEMBERS_MANAGE)),
    db: AsyncSession = Depends(get_db_session),
) -> MemberResponse:
    """Modify role with owner protections and escalation guards."""
    mem_query = (
        select(OrganizationMembership)
        .options(selectinload(OrganizationMembership.user))
        .where(
            OrganizationMembership.id == membership_id,
            OrganizationMembership.organization_id == context.organization.id,
        )
    )
    mem_res = await db.execute(mem_query)
    target_membership = mem_res.scalar_one_or_none()

    if not target_membership:
        raise ResourceNotFoundException("OrganizationMembership", membership_id)

    # Check caller authority over target member's current role
    if not can_manage_membership(context.role, target_membership.role):
        raise ForbiddenException(
            f"Role '{context.role}' is not authorized to modify a member with role '{target_membership.role}'."
        )

    # Check caller authority to assign target role
    if not can_assign_role(context.role, payload.role):
        raise ForbiddenException(
            f"Role '{context.role}' is not authorized to assign the privileged '{payload.role}' role."
        )

    # Protect against demoting the last active owner
    if target_membership.role == MembershipRole.OWNER and payload.role != MembershipRole.OWNER:
        owner_count_query = select(func.count(OrganizationMembership.id)).where(
            OrganizationMembership.organization_id == context.organization.id,
            OrganizationMembership.role == MembershipRole.OWNER,
            OrganizationMembership.status == MembershipStatus.ACTIVE,
        )
        owner_count = await db.scalar(owner_count_query)
        if (owner_count or 0) <= 1:
            raise ForbiddenException(
                "Cannot demote the last remaining active owner in the organization."
            )

    target_membership.role = payload.role
    await db.flush()

    logger.info(
        f"Member role updated: membership={membership_id} new_role={payload.role} by={context.user.id}"
    )

    return MemberResponse(
        id=target_membership.id,
        organization_id=context.organization.id,
        user_id=target_membership.user_id,
        email=target_membership.user.email,
        display_name=target_membership.user.display_name,
        role=target_membership.role,
        status=target_membership.status,
        created_at=target_membership.created_at,
    )


@router.delete(
    "/{organization_id}/members/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an organization membership",
)
async def revoke_membership(
    membership_id: uuid.UUID = Path(..., description="UUID of the membership to revoke"),
    context: OrganizationContext = Depends(require_permission(Permission.ORG_MEMBERS_MANAGE)),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Revoke membership, with last-owner protections."""
    mem_query = select(OrganizationMembership).where(
        OrganizationMembership.id == membership_id,
        OrganizationMembership.organization_id == context.organization.id,
    )
    mem_res = await db.execute(mem_query)
    target_membership = mem_res.scalar_one_or_none()

    if not target_membership:
        raise ResourceNotFoundException("OrganizationMembership", membership_id)

    # Check caller authority over target member
    if not can_manage_membership(context.role, target_membership.role):
        raise ForbiddenException(
            f"Role '{context.role}' is not authorized to revoke a member with role '{target_membership.role}'."
        )

    # Protect against removing the last active owner
    if target_membership.role == MembershipRole.OWNER:
        owner_count_query = select(func.count(OrganizationMembership.id)).where(
            OrganizationMembership.organization_id == context.organization.id,
            OrganizationMembership.role == MembershipRole.OWNER,
            OrganizationMembership.status == MembershipStatus.ACTIVE,
        )
        owner_count = await db.scalar(owner_count_query)
        if (owner_count or 0) <= 1:
            raise ForbiddenException(
                "Cannot remove the last remaining active owner in the organization."
            )

    target_membership.status = MembershipStatus.REVOKED
    await db.flush()

    logger.info(f"Membership revoked: membership={membership_id} by={context.user.id}")
