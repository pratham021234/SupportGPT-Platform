"""Pydantic schemas for AI observability, traces, investigations, evaluations, and usage."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SpanResponse(BaseModel):
    """Execution span detailing an individual stage of an AI workflow."""

    stage: str
    start_ms: float
    duration_ms: float
    outcome: str
    details: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None


class TraceSummaryResponse(BaseModel):
    """Summary of an AI execution trace for list views."""

    id: uuid.UUID
    trace_id: str
    request_id: str | None = None
    operation_type: str
    provider: str
    model: str
    start_time: datetime
    end_time: datetime
    duration_ms: float
    outcome: str
    error_category: str | None = None
    retry_count: int = 0
    evidence_count: int = 0
    token_usage: dict[str, Any] = Field(default_factory=dict)
    estimated_cost_usd: float | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TraceDetailResponse(TraceSummaryResponse):
    """Detailed AI execution trace including granular execution spans and versions."""

    pipeline_version: str | None = None
    policy_version: str | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    spans: list[SpanResponse] = Field(default_factory=list)


class TraceListResponse(BaseModel):
    """Paginated list of execution traces."""

    items: list[TraceSummaryResponse]
    total: int


class DiagnosticHypothesis(BaseModel):
    """Structured diagnostic finding and remediation suggestion."""

    hypothesis: str
    confidence: str
    recommended_action: str


class InvestigationResponse(BaseModel):
    """Canonical failure investigation record."""

    id: uuid.UUID
    investigation_id: str
    fingerprint: str
    failure_category: str
    severity: str
    status: str
    trace_id: str | None = None
    request_id: str | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    provider: str | None = None
    sanitized_error_summary: str
    first_seen_at: datetime
    last_seen_at: datetime
    occurrence_count: int
    pipeline_version: str | None = None
    diagnostic_hypotheses: list[DiagnosticHypothesis] = Field(default_factory=list)
    resolution_notes: str | None = None
    assigned_to_user_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvestigationUpdatePayload(BaseModel):
    """Payload for updating an investigation's status and resolution notes."""

    status: str = Field(description="New status: open, investigating, resolved, or ignored")
    resolution_notes: str | None = Field(
        default=None, description="Operator root cause or remediation notes"
    )
    assigned_to_user_id: uuid.UUID | None = Field(default=None, description="Assign to an engineer")


class InvestigationListResponse(BaseModel):
    """Paginated list of failure investigations."""

    items: list[InvestigationResponse]
    total: int


class EvaluationRunResponse(BaseModel):
    """Benchmark evaluation run overview."""

    id: uuid.UUID
    dataset_id: str
    dataset_version: str
    total_cases: int
    answerable_cases: int
    unanswerable_cases: int
    embedding_provider: str
    embedding_model: str
    generation_provider: str | None = None
    generation_model: str | None = None
    mean_recall_at_k: float
    mean_reciprocal_rank: float
    citation_validity_rate: float
    abstention_accuracy: float
    status: str
    error_message: str | None = None
    regressions: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class EvaluationDetailResponse(EvaluationRunResponse):
    """Detailed evaluation run including all evaluated test query findings."""

    retrieval_config: dict[str, Any] = Field(default_factory=dict)
    verification_pipeline_version: str | None = None
    policy_version: str | None = None
    case_results: list[dict[str, Any]] = Field(default_factory=list)


class EvaluationListResponse(BaseModel):
    """Paginated list of benchmark evaluation runs."""

    items: list[EvaluationRunResponse]
    total: int


class EvaluationCompareResponse(BaseModel):
    """Comparison results between a baseline and candidate evaluation run."""

    baseline_id: str
    baseline_date: str
    candidate_id: str
    candidate_date: str
    comparison: dict[str, dict[str, float]]
    is_regression: bool


class UsageModelBreakdown(BaseModel):
    """Token consumption and cost aggregated per provider and model."""

    provider: str
    model: str
    total_tokens: int
    estimated_cost_usd: float
    request_count: int
    is_provider_reported: bool


class UsageOperationBreakdown(BaseModel):
    """Token consumption and cost aggregated per operation type."""

    operation_type: str
    total_tokens: int
    estimated_cost_usd: float
    request_count: int


class UsageSummaryResponse(BaseModel):
    """Aggregated organization token consumption and estimated cost."""

    organization_id: str
    total_tokens: int
    total_input_tokens: int
    total_output_tokens: int
    total_embedding_tokens: int
    total_estimated_cost_usd: float
    total_operations: int
    by_model: list[UsageModelBreakdown]
    by_operation: list[UsageOperationBreakdown]


class SystemDiagnosticsResponse(BaseModel):
    """Platform infrastructure readiness and deep dependency diagnostics."""

    environment: str
    version: str
    timestamp: float
    status: str
    dependencies: dict[str, Any]
    workers: dict[str, Any]
    ai_providers: dict[str, Any]
