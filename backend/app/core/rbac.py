"""Role-Based Access Control (RBAC) definition, permission matrix, and policy evaluation."""

from enum import StrEnum

from app.models.enums import MembershipRole


class Permission(StrEnum):
    """Authoritative system permissions for tenant operations."""

    # Organization management
    ORG_READ = "org:read"
    ORG_UPDATE = "org:update"
    ORG_MEMBERS_READ = "org:members:read"
    ORG_MEMBERS_MANAGE = "org:members:manage"

    # Ticket & Customer support operations
    TICKETS_READ = "tickets:read"
    TICKETS_WRITE = "tickets:write"
    TICKETS_ASSIGN = "tickets:assign"
    CUSTOMERS_READ = "customers:read"
    CUSTOMERS_WRITE = "customers:write"

    # External Sources & Ingestion Operations
    SOURCES_READ = "sources:read"
    SOURCES_MANAGE = "sources:manage"
    INGESTION_READ = "ingestion:read"
    INGESTION_MANAGE = "ingestion:manage"

    # Knowledge Base & Document Management
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_WRITE = "knowledge:write"
    KNOWLEDGE_MANAGE = "knowledge:manage"

    # Response Verification, Policy & Human Approval (Phase 07)
    VERIFICATION_READ = "verification:read"
    VERIFICATION_WRITE = "verification:write"
    VERIFICATION_APPROVE = "verification:approve"
    POLICIES_MANAGE = "policies:manage"

    # AI Observability, Traces, Investigations & Evaluation (Phase 08)
    OBSERVABILITY_READ = "observability:read"
    OBSERVABILITY_MANAGE = "observability:manage"


# Explicit Role-Permission Matrix (Least Privilege)
ROLE_PERMISSIONS: dict[MembershipRole, set[Permission]] = {
    MembershipRole.OWNER: {
        Permission.ORG_READ,
        Permission.ORG_UPDATE,
        Permission.ORG_MEMBERS_READ,
        Permission.ORG_MEMBERS_MANAGE,
        Permission.TICKETS_READ,
        Permission.TICKETS_WRITE,
        Permission.TICKETS_ASSIGN,
        Permission.CUSTOMERS_READ,
        Permission.CUSTOMERS_WRITE,
        Permission.SOURCES_READ,
        Permission.SOURCES_MANAGE,
        Permission.INGESTION_READ,
        Permission.INGESTION_MANAGE,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.KNOWLEDGE_MANAGE,
        Permission.VERIFICATION_READ,
        Permission.VERIFICATION_WRITE,
        Permission.VERIFICATION_APPROVE,
        Permission.POLICIES_MANAGE,
        Permission.OBSERVABILITY_READ,
        Permission.OBSERVABILITY_MANAGE,
    },
    MembershipRole.ADMIN: {
        Permission.ORG_READ,
        Permission.ORG_UPDATE,
        Permission.ORG_MEMBERS_READ,
        Permission.ORG_MEMBERS_MANAGE,
        Permission.TICKETS_READ,
        Permission.TICKETS_WRITE,
        Permission.TICKETS_ASSIGN,
        Permission.CUSTOMERS_READ,
        Permission.CUSTOMERS_WRITE,
        Permission.SOURCES_READ,
        Permission.SOURCES_MANAGE,
        Permission.INGESTION_READ,
        Permission.INGESTION_MANAGE,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.KNOWLEDGE_MANAGE,
        Permission.VERIFICATION_READ,
        Permission.VERIFICATION_WRITE,
        Permission.VERIFICATION_APPROVE,
        Permission.POLICIES_MANAGE,
        Permission.OBSERVABILITY_READ,
        Permission.OBSERVABILITY_MANAGE,
    },
    MembershipRole.AGENT: {
        Permission.ORG_READ,
        Permission.TICKETS_READ,
        Permission.TICKETS_WRITE,
        Permission.TICKETS_ASSIGN,
        Permission.CUSTOMERS_READ,
        Permission.CUSTOMERS_WRITE,
        Permission.SOURCES_READ,
        Permission.INGESTION_READ,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.VERIFICATION_READ,
        Permission.VERIFICATION_WRITE,
        Permission.VERIFICATION_APPROVE,
        Permission.OBSERVABILITY_READ,
    },
    MembershipRole.VIEWER: {
        Permission.ORG_READ,
        Permission.TICKETS_READ,
        Permission.CUSTOMERS_READ,
        Permission.KNOWLEDGE_READ,
        Permission.VERIFICATION_READ,
        Permission.OBSERVABILITY_READ,
    },
}

# Role hierarchy levels for escalation prevention (higher numerical value = higher privilege)
ROLE_HIERARCHY: dict[MembershipRole, int] = {
    MembershipRole.VIEWER: 10,
    MembershipRole.AGENT: 20,
    MembershipRole.ADMIN: 30,
    MembershipRole.OWNER: 40,
}


def has_permission(role: MembershipRole, permission: Permission) -> bool:
    """Evaluate whether a membership role possesses a specific permission."""
    allowed = ROLE_PERMISSIONS.get(role, set())
    return permission in allowed


def can_assign_role(caller_role: MembershipRole, target_role: MembershipRole) -> bool:
    """Enforce privilege escalation prevention.

    - Only an OWNER can assign OWNER or ADMIN roles.
    - An ADMIN can only assign AGENT or VIEWER roles.
    - AGENT and VIEWER cannot manage members or assign roles.
    """
    if caller_role == MembershipRole.OWNER:
        return True
    if caller_role == MembershipRole.ADMIN:
        # Admins cannot grant OWNER or ADMIN roles (prevents self-promotion and unauthorized admin creation)
        return target_role in (MembershipRole.AGENT, MembershipRole.VIEWER)
    return False


def can_manage_membership(caller_role: MembershipRole, target_current_role: MembershipRole) -> bool:
    """Determine whether the caller can modify or revoke a target member's role.

    - Only an OWNER can modify or revoke an OWNER or ADMIN membership.
    - An ADMIN can only modify or revoke AGENT or VIEWER memberships.
    - An ADMIN cannot modify or revoke an OWNER or another ADMIN.
    """
    if caller_role == MembershipRole.OWNER:
        return True
    if caller_role == MembershipRole.ADMIN:
        return target_current_role in (MembershipRole.AGENT, MembershipRole.VIEWER)
    return False
