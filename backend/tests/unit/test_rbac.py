"""Unit tests verifying Role-Based Access Control (RBAC) matrix and privilege escalation guards."""

from app.core.rbac import (
    Permission,
    can_assign_role,
    can_manage_membership,
    has_permission,
)
from app.models.enums import MembershipRole


def test_owner_role_permissions():
    """Verify OWNER role possesses all administrative and operational permissions."""
    for perm in Permission:
        assert has_permission(MembershipRole.OWNER, perm) is True


def test_admin_role_permissions():
    """Verify ADMIN role possesses member management and support permissions."""
    assert has_permission(MembershipRole.ADMIN, Permission.ORG_READ) is True
    assert has_permission(MembershipRole.ADMIN, Permission.ORG_MEMBERS_READ) is True
    assert has_permission(MembershipRole.ADMIN, Permission.ORG_MEMBERS_MANAGE) is True
    assert has_permission(MembershipRole.ADMIN, Permission.TICKETS_WRITE) is True
    assert has_permission(MembershipRole.ADMIN, Permission.TICKETS_ASSIGN) is True
    assert has_permission(MembershipRole.ADMIN, Permission.CUSTOMERS_WRITE) is True


def test_agent_role_least_privilege():
    """Verify AGENT role can operate tickets and customers, but cannot manage members."""
    assert has_permission(MembershipRole.AGENT, Permission.ORG_READ) is True
    assert has_permission(MembershipRole.AGENT, Permission.TICKETS_READ) is True
    assert has_permission(MembershipRole.AGENT, Permission.TICKETS_WRITE) is True
    assert has_permission(MembershipRole.AGENT, Permission.TICKETS_ASSIGN) is True
    assert has_permission(MembershipRole.AGENT, Permission.CUSTOMERS_READ) is True
    assert has_permission(MembershipRole.AGENT, Permission.CUSTOMERS_WRITE) is True

    # Denied administrative permissions
    assert has_permission(MembershipRole.AGENT, Permission.ORG_MEMBERS_READ) is False
    assert has_permission(MembershipRole.AGENT, Permission.ORG_MEMBERS_MANAGE) is False


def test_viewer_role_read_only_privilege():
    """Verify VIEWER role has strictly read-only access."""
    assert has_permission(MembershipRole.VIEWER, Permission.ORG_READ) is True
    assert has_permission(MembershipRole.VIEWER, Permission.TICKETS_READ) is True
    assert has_permission(MembershipRole.VIEWER, Permission.CUSTOMERS_READ) is True

    # Denied state-changing permissions
    assert has_permission(MembershipRole.VIEWER, Permission.TICKETS_WRITE) is False
    assert has_permission(MembershipRole.VIEWER, Permission.TICKETS_ASSIGN) is False
    assert has_permission(MembershipRole.VIEWER, Permission.CUSTOMERS_WRITE) is False
    assert has_permission(MembershipRole.VIEWER, Permission.ORG_MEMBERS_MANAGE) is False


def test_privilege_escalation_prevention_on_assignment():
    """Verify that roles cannot assign permissions higher than their authorized tier."""
    # Owner can assign any role
    assert can_assign_role(MembershipRole.OWNER, MembershipRole.OWNER) is True
    assert can_assign_role(MembershipRole.OWNER, MembershipRole.ADMIN) is True
    assert can_assign_role(MembershipRole.OWNER, MembershipRole.AGENT) is True
    assert can_assign_role(MembershipRole.OWNER, MembershipRole.VIEWER) is True

    # Admin CANNOT assign OWNER or ADMIN (prevents self-promotion or creating co-admins)
    assert can_assign_role(MembershipRole.ADMIN, MembershipRole.OWNER) is False
    assert can_assign_role(MembershipRole.ADMIN, MembershipRole.ADMIN) is False
    assert can_assign_role(MembershipRole.ADMIN, MembershipRole.AGENT) is True
    assert can_assign_role(MembershipRole.ADMIN, MembershipRole.VIEWER) is True

    # Agent and Viewer cannot assign any role
    assert can_assign_role(MembershipRole.AGENT, MembershipRole.VIEWER) is False
    assert can_assign_role(MembershipRole.VIEWER, MembershipRole.VIEWER) is False


def test_membership_management_hierarchy():
    """Verify that roles cannot modify peers or superiors."""
    # Owner can manage anyone
    assert can_manage_membership(MembershipRole.OWNER, MembershipRole.OWNER) is True
    assert can_manage_membership(MembershipRole.OWNER, MembershipRole.ADMIN) is True
    assert can_manage_membership(MembershipRole.OWNER, MembershipRole.AGENT) is True

    # Admin can only manage Agent and Viewer
    assert can_manage_membership(MembershipRole.ADMIN, MembershipRole.OWNER) is False
    assert can_manage_membership(MembershipRole.ADMIN, MembershipRole.ADMIN) is False
    assert can_manage_membership(MembershipRole.ADMIN, MembershipRole.AGENT) is True
    assert can_manage_membership(MembershipRole.ADMIN, MembershipRole.VIEWER) is True

    # Agent cannot manage anyone
    assert can_manage_membership(MembershipRole.AGENT, MembershipRole.AGENT) is False
    assert can_manage_membership(MembershipRole.AGENT, MembershipRole.VIEWER) is False
