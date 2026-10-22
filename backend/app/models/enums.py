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


class SourceStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    REVOKED = "revoked"


class SourceProvider(StrEnum):
    GENERIC_WEBHOOK = "generic_webhook"
    CUSTOM_API = "custom_api"
    EMAIL_POSTMARK = "email_postmark"
    EMAIL_SENDGRID = "email_sendgrid"
    ZENDESK = "zendesk"


class IngestionStatus(StrEnum):
    RECEIVED = "received"
    QUEUED = "queued"
    PROCESSING = "processing"
    RETRY_WAIT = "retry_wait"
    PROCESSED = "processed"
    DEAD_LETTER = "dead_letter"
    QUARANTINED = "quarantined"
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


class KnowledgeBaseStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class DocumentSourceType(StrEnum):
    FILE_UPLOAD = "file_upload"
    MANUAL_ENTRY = "manual_entry"
    API = "api"


class DocumentMediaType(StrEnum):
    PDF = "application/pdf"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    TXT = "text/plain"
    MARKDOWN = "text/markdown"


class DocumentProcessingStatus(StrEnum):
    UPLOADED = "uploaded"
    STORED = "stored"
    QUEUED = "queued"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    NORMALIZING = "normalizing"
    NORMALIZED = "normalized"
    CHUNKING = "chunking"
    CHUNKED = "chunked"
    READY_FOR_INDEXING = "ready_for_indexing"
    INDEXED = "indexed"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"
    QUARANTINED = "quarantined"


class DocumentLifecycleStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


# Phase 07: Response Verification, Policy Enforcement & Approval Enums


class DraftLifecycleStatus(StrEnum):
    DRAFT = "draft"
    VERIFICATION_PENDING = "verification_pending"
    VERIFICATION_FAILED = "verification_failed"
    VERIFIED = "verified"
    APPROVAL_PENDING = "approval_pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUIRED = "revision_required"
    SUPERSEDED = "superseded"


class VerificationStatus(StrEnum):
    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    NEEDS_REVISION = "needs_revision"
    BLOCKED = "blocked"
    FAILED = "failed"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ClaimCategory(StrEnum):
    POLICY = "policy"
    PRODUCT_FACT = "product_fact"
    PRICING_REFUND = "pricing_refund"
    SLA_COMMITMENT = "sla_commitment"
    GENERAL = "general"


class ClaimSupportStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    NOT_VERIFIABLE = "not_verifiable"


class ClaimVerificationMethod(StrEnum):
    DETERMINISTIC_LEXICAL = "deterministic_lexical"
    SEMANTIC_NLI = "semantic_nli"
    EVIDENCE_GROUNDING = "evidence_grounding"
    RULE_ENGINE = "rule_engine"


class PolicyCategory(StrEnum):
    FACTUAL_GROUNDING = "factual_grounding"
    PROHIBITED_TERMS = "prohibited_terms"
    MANDATORY_DISCLAIMERS = "mandatory_disclaimers"
    RESTRICTED_COMMITMENTS = "restricted_commitments"
    REFUND_POLICY = "refund_policy"
    SENSITIVE_DATA = "sensitive_data"
    APPROVAL_GATE = "approval_gate"


class PolicyRuleType(StrEnum):
    UNSUPPORTED_CLAIM_BLOCK = "unsupported_claim_block"
    KEYWORD_PROHIBITION = "keyword_prohibition"
    REQUIRED_PHRASE = "required_phrase"
    MAX_LENGTH = "max_length"
    REFUND_LIMIT = "refund_limit"
    MANDATORY_APPROVAL_ON_RISK = "mandatory_approval_on_risk"


class PolicySeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"
    INVALIDATED = "invalidated"
    CANCELLED = "cancelled"


class ApprovalDecisionType(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_REVISION = "request_revision"


class VerificationAuditEventType(StrEnum):
    DRAFT_CREATED = "draft_created"
    DRAFT_REVISED = "draft_revised"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"
    VERIFICATION_FAILED = "verification_failed"
    POLICY_CREATED = "policy_created"
    POLICY_UPDATED = "policy_updated"
    POLICY_TOGGLED = "policy_toggled"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"
    REVISION_REQUESTED = "revision_requested"
    APPROVAL_INVALIDATED = "approval_invalidated"


class AIOperationType(StrEnum):
    RAG_QUERY = "rag_query"
    ANSWER_GENERATION = "answer_generation"
    RESPONSE_VERIFICATION = "response_verification"
    CLAIM_GROUNDING = "claim_grounding"
    DOCUMENT_INDEXING = "document_indexing"
    POLICY_EVALUATION = "policy_evaluation"


class TraceOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    ABSTAINED = "abstained"
    BLOCKED = "blocked"


class FailureCategory(StrEnum):
    CONFIGURATION_ERROR = "configuration_error"
    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"
    INPUT_VALIDATION_ERROR = "input_validation_error"
    EMBEDDING_FAILURE = "embedding_failure"
    RETRIEVAL_FAILURE = "retrieval_failure"
    NO_RELEVANT_EVIDENCE = "no_relevant_evidence"
    GENERATION_FAILURE = "generation_failure"
    CITATION_VALIDATION_FAILURE = "citation_validation_failure"
    VERIFICATION_FAILURE = "verification_failure"
    POLICY_VIOLATION = "policy_violation"
    APPROVAL_CONFLICT = "approval_conflict"
    DOCUMENT_PROCESSING_FAILURE = "document_processing_failure"
    INDEXING_FAILURE = "indexing_failure"
    DATABASE_FAILURE = "database_failure"
    QUEUE_FAILURE = "queue_failure"
    UNKNOWN_ERROR = "unknown_error"


class InvestigationStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class EvaluationStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
