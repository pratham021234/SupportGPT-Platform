"""Pydantic schemas for Response Verification, Policy Enforcement, and Human Approval."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import (
    ApprovalDecisionType,
    ApprovalStatus,
    ClaimCategory,
    ClaimSupportStatus,
    ClaimVerificationMethod,
    DraftLifecycleStatus,
    PolicyCategory,
    PolicyRuleType,
    PolicySeverity,
    RiskLevel,
    VerificationStatus,
)

# --- Response Draft Schemas ---


class ResponseDraftCreateRequest(BaseModel):
    """Payload to create a new response draft candidate."""

    original_query: str = Field(
        ..., min_length=2, max_length=5000, description="Customer question or context"
    )
    draft_text: str = Field(
        ..., min_length=2, max_length=10000, description="Proposed response text"
    )
    ticket_id: uuid.UUID | None = Field(default=None, description="Optional associated ticket ID")
    conversation_id: uuid.UUID | None = Field(
        default=None, description="Optional associated conversation ID"
    )
    evidence_references: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Retrieved evidence chunks used to generate or ground the draft",
    )


class ResponseDraftUpdateRequest(BaseModel):
    """Payload to revise an existing response draft, creating an incremented version."""

    draft_text: str = Field(
        ..., min_length=2, max_length=10000, description="Revised draft content"
    )
    evidence_references: list[dict[str, Any]] | None = Field(
        default=None,
        description="Updated evidence references, if altered during revision",
    )


class ResponseDraftResponse(BaseModel):
    """Representation of an authoritative response draft version."""

    id: uuid.UUID
    organization_id: uuid.UUID
    ticket_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    original_query: str
    draft_text: str
    version_number: int
    lifecycle_status: DraftLifecycleStatus
    evidence_references: list[dict[str, Any]]
    created_by_user_id: uuid.UUID | None
    lock_version: int
    created_at: datetime
    updated_at: datetime


class ResponseDraftListResponse(BaseModel):
    """Paginated collection of response drafts."""

    items: list[ResponseDraftResponse]
    total: int


# --- Verification Findings Schemas ---


class ClaimFindingResponse(BaseModel):
    """Individual atomic claim finding from verification."""

    id: uuid.UUID | None = None
    claim_text: str
    claim_category: ClaimCategory
    support_status: ClaimSupportStatus
    evidence_chunk_ids: list[str]
    confidence_score: float | None
    reason: str
    verification_method: ClaimVerificationMethod


class PolicyFindingResponse(BaseModel):
    """Result of evaluating a single policy rule against a draft."""

    policy_id: str | None = None
    rule_name: str
    policy_category: PolicyCategory
    rule_type: PolicyRuleType
    severity: PolicySeverity
    passed: bool
    requires_approval: bool
    details: str


class VerificationRunResponse(BaseModel):
    """Details and findings of a verification pipeline execution."""

    id: uuid.UUID
    organization_id: uuid.UUID
    draft_id: uuid.UUID
    draft_version: int
    verification_pipeline_version: str
    policy_set_version: int
    status: VerificationStatus
    risk_level: RiskLevel
    requires_human_approval: bool
    machine_readable_findings: dict[str, Any]
    claim_findings: list[ClaimFindingResponse]
    policy_findings: list[PolicyFindingResponse] = []
    started_at: datetime
    completed_at: datetime | None
    execution_time_ms: int | None
    request_id: str | None
    error_message: str | None


class VerificationRunListResponse(BaseModel):
    """List of verification runs for a draft."""

    items: list[VerificationRunResponse]
    total: int


# --- Policy Management Schemas ---


class PolicyRuleCreateRequest(BaseModel):
    """Configuration to declare a new response compliance rule."""

    name: str = Field(..., min_length=2, max_length=128)
    description: str = Field(default="", max_length=1000)
    policy_category: PolicyCategory
    severity: PolicySeverity = PolicySeverity.HIGH
    rule_type: PolicyRuleType
    rule_config: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True


class PolicyRuleUpdateRequest(BaseModel):
    """Update payload for a policy rule, generating an incremented version."""

    name: str | None = Field(default=None, min_length=2, max_length=128)
    description: str | None = Field(default=None, max_length=1000)
    severity: PolicySeverity | None = None
    rule_config: dict[str, Any] | None = None
    is_enabled: bool | None = None


class PolicyRuleResponse(BaseModel):
    """Representation of an active or historical policy rule."""

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str
    policy_category: PolicyCategory
    severity: PolicySeverity
    is_enabled: bool
    version_number: int
    rule_type: PolicyRuleType
    rule_config: dict[str, Any]
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PolicyRuleListResponse(BaseModel):
    """List of configured policy rules."""

    items: list[PolicyRuleResponse]
    total: int


# --- Approval Schemas ---


class ApprovalRequestCreateRequest(BaseModel):
    """Payload to initiate a human approval workflow."""

    draft_version: int = Field(..., ge=1, description="Target draft version")
    verification_run_id: uuid.UUID = Field(
        ..., description="Run ID informing this approval request"
    )
    required_role: str = Field(default="agent", description="Minimum role required to review")
    separation_of_duties: bool = Field(
        default=True, description="Prohibit self-approval by requester"
    )


class ApprovalDecisionRequest(BaseModel):
    """Payload representing a human approver's explicit decision."""

    decision: ApprovalDecisionType = Field(
        ..., description="Action: approve, reject, or request_revision"
    )
    reason: str | None = Field(
        default=None, max_length=2000, description="Mandatory or optional rationale"
    )


class ApprovalRequestResponse(BaseModel):
    """Detailed state of a human approval request."""

    id: uuid.UUID
    organization_id: uuid.UUID
    draft_id: uuid.UUID
    draft_version: int
    verification_run_id: uuid.UUID
    status: ApprovalStatus
    required_role: str
    separation_of_duties: bool
    requested_by_user_id: uuid.UUID | None
    decision_by_user_id: uuid.UUID | None
    decision_reason: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApprovalRequestListResponse(BaseModel):
    """List of approval requests."""

    items: list[ApprovalRequestResponse]
    total: int


# --- Audit Schemas ---


class VerificationAuditEventResponse(BaseModel):
    """Single immutable audit log entry."""

    id: uuid.UUID
    organization_id: uuid.UUID
    event_type: str
    entity_type: str
    entity_id: uuid.UUID
    actor_id: uuid.UUID | None
    request_id: str | None
    event_summary: str
    metadata_json: dict[str, Any]
    created_at: datetime


class VerificationAuditEventListResponse(BaseModel):
    """List of audit events."""

    items: list[VerificationAuditEventResponse]
    total: int
