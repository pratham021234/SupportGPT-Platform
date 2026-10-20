"""Model package exporting all authoritative domain and system models for SupportGPT AI."""

from app.models.approval_request import ApprovalRequest
from app.models.attachment import Attachment
from app.models.claim_finding import ClaimFinding
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.customer_identity import CustomerIdentity, normalize_identity_value
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.enums import (
    ApprovalDecisionType,
    ApprovalStatus,
    AttachmentScanStatus,
    AuthorType,
    ClaimCategory,
    ClaimSupportStatus,
    ClaimVerificationMethod,
    ConversationStatus,
    CustomerStatus,
    DocumentLifecycleStatus,
    DocumentMediaType,
    DocumentProcessingStatus,
    DocumentSourceType,
    DraftLifecycleStatus,
    IdentityType,
    IdentityVerificationStatus,
    IngestionStatus,
    KnowledgeBaseStatus,
    MembershipRole,
    MembershipStatus,
    MessageDirection,
    OrganizationStatus,
    PolicyCategory,
    PolicyRuleType,
    PolicySeverity,
    RiskLevel,
    SourceProvider,
    SourceStatus,
    TicketChannel,
    TicketEventType,
    TicketPriority,
    TicketStatus,
    UserStatus,
    VerificationAuditEventType,
    VerificationStatus,
    can_transition_ticket_status,
)
from app.models.event_source import EventSource
from app.models.foundation import SystemEventLog
from app.models.ingestion_receipt import IngestionReceipt
from app.models.knowledge_base import KnowledgeBase
from app.models.membership import OrganizationMembership
from app.models.message import Message
from app.models.organization import (
    Organization,
    OrganizationTicketCounter,
    allocate_next_ticket_number,
    normalize_organization_slug,
)
from app.models.policy_rule import PolicyRule
from app.models.response_draft import ResponseDraft
from app.models.session import UserSession
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.models.user import User
from app.models.verification_audit_event import VerificationAuditEvent
from app.models.verification_run import VerificationRun

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
    "EventSource",
    # Knowledge Base & Documents
    "KnowledgeBase",
    "Document",
    "DocumentVersion",
    "DocumentChunk",
    # Identity, Accounts & Memberships
    "User",
    "OrganizationMembership",
    "UserSession",
    # Phase 07: Response Verification & Approvals
    "ResponseDraft",
    "VerificationRun",
    "ClaimFinding",
    "PolicyRule",
    "ApprovalRequest",
    "VerificationAuditEvent",
    # Enums & Domain Rules
    "OrganizationStatus",
    "CustomerStatus",
    "UserStatus",
    "MembershipRole",
    "MembershipStatus",
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
    "SourceStatus",
    "SourceProvider",
    "KnowledgeBaseStatus",
    "DocumentSourceType",
    "DocumentMediaType",
    "DocumentProcessingStatus",
    "DocumentLifecycleStatus",
    "DraftLifecycleStatus",
    "VerificationStatus",
    "RiskLevel",
    "ClaimCategory",
    "ClaimSupportStatus",
    "ClaimVerificationMethod",
    "PolicyCategory",
    "PolicyRuleType",
    "PolicySeverity",
    "ApprovalStatus",
    "ApprovalDecisionType",
    "VerificationAuditEventType",
    "can_transition_ticket_status",
]
