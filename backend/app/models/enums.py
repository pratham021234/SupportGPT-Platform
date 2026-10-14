"""Domain enumeration definitions and lifecycle transition rules."""

from enum import StrEnum


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class MembershipRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    AGENT = "agent"
    VIEWER = "viewer"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INVITED = "invited"
    REVOKED = "revoked"


class CustomerStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    MERGED = "merged"


class IdentityType(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    EXTERNAL_CHANNEL = "external_channel"
    PROVIDER_SPECIFIC = "provider_specific"


class IdentityVerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    REVOKED = "revoked"


class TicketStatus(StrEnum):
    OPEN = "open"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(StrEnum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TicketChannel(StrEnum):
    EMAIL = "email"
    CHAT = "chat"
    API = "api"
    WEB = "web"
    INTERNAL = "internal"


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"
    CLOSED = "closed"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class AuthorType(StrEnum):
    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"
    AI = "ai"


class AttachmentScanStatus(StrEnum):
    PENDING = "pending"
    SCANNED_CLEAN = "scanned_clean"
    INFECTED = "infected"
    QUARANTINED = "quarantined"
    READY = "ready"


class TicketEventType(StrEnum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    PRIORITY_CHANGED = "priority_changed"
    ASSIGNMENT_CHANGED = "assignment_changed"
    CUSTOMER_LINKED = "customer_linked"
    CUSTOMER_UNLINKED = "customer_unlinked"
    CONVERSATION_LINKED = "conversation_linked"
    CONVERSATION_UNLINKED = "conversation_unlinked"
    COMMENT_ADDED = "comment_added"


class IngestionStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    FAILED = "failed"
    IGNORED = "ignored"


# Domain rule: Valid ticket status transitions
VALID_TICKET_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.OPEN: {
        TicketStatus.PENDING,
        TicketStatus.IN_PROGRESS,
        TicketStatus.RESOLVED,
        TicketStatus.CLOSED,
    },
    TicketStatus.PENDING: {
        TicketStatus.OPEN,
        TicketStatus.IN_PROGRESS,
        TicketStatus.RESOLVED,
        TicketStatus.CLOSED,
    },
    TicketStatus.IN_PROGRESS: {
        TicketStatus.PENDING,
        TicketStatus.RESOLVED,
        TicketStatus.CLOSED,
        TicketStatus.OPEN,
    },
    TicketStatus.RESOLVED: {
        TicketStatus.OPEN,  # Customer re-opens resolved ticket
        TicketStatus.CLOSED,
    },
    TicketStatus.CLOSED: {
        TicketStatus.OPEN,  # Explicit re-open authorized by policy
    },
}


def can_transition_ticket_status(current: TicketStatus, target: TicketStatus) -> bool:
    """Validate whether a ticket status transition is permissible under domain rules."""
    if current == target:
        return True
    allowed = VALID_TICKET_TRANSITIONS.get(current, set())
    return target in allowed
