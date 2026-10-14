"""Model package exporting all authoritative domain and system models for SupportGPT AI."""

from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.customer_identity import CustomerIdentity, normalize_identity_value
from app.models.enums import (
    AttachmentScanStatus,
    AuthorType,
    ConversationStatus,
    CustomerStatus,
    IdentityType,
    IdentityVerificationStatus,
    IngestionStatus,
    MessageDirection,
    OrganizationStatus,
    TicketChannel,
    TicketEventType,
    TicketPriority,
    TicketStatus,
    can_transition_ticket_status,
)
from app.models.foundation import SystemEventLog
from app.models.ingestion_receipt import IngestionReceipt
from app.models.message import Message
from app.models.organization import (
    Organization,
    OrganizationTicketCounter,
    allocate_next_ticket_number,
    normalize_organization_slug,
)
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent

__all__ = [
    # System & Audit
    "SystemEventLog",
    # Organization Workspace & Counter
    "Organization",
    "OrganizationTicketCounter",
    "allocate_next_ticket_number",
    "normalize_organization_slug",
    # Customer & Contact Identities
    "Customer",
    "CustomerIdentity",
    "normalize_identity_value",
    # Core Support Case & Threads
    "Ticket",
    "Conversation",
    "Message",
    "Attachment",
    "TicketEvent",
    "IngestionReceipt",
    # Enums & Domain Rules
    "OrganizationStatus",
    "CustomerStatus",
    "IdentityType",
    "IdentityVerificationStatus",
    "TicketStatus",
    "TicketPriority",
    "TicketChannel",
    "ConversationStatus",
    "MessageDirection",
    "AuthorType",
    "AttachmentScanStatus",
    "TicketEventType",
    "IngestionStatus",
    "can_transition_ticket_status",
]
