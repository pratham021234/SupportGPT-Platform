"""Failure Investigation service for incident deduplication, diagnosis, and workflow management."""

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger, redact_sensitive_data
from app.models.enums import FailureCategory, InvestigationStatus, RiskLevel
from app.models.failure_investigation import FailureInvestigation

logger = get_logger("supportgpt.observability.investigation")


class InvestigationService:
    """Manages failure classification, deduplication, and investigation state machine."""

    @staticmethod
    def classify_failure(exc: Exception | str) -> str:
        """Map exception or error message to a normalized FailureCategory."""
        msg = str(exc).lower()

        if "authentication" in msg or "unauthorized" in msg or "token invalid" in msg:
            return FailureCategory.AUTHENTICATION_ERROR.value
        elif "forbidden" in msg or "permission" in msg or "separation of duties" in msg:
            return FailureCategory.AUTHORIZATION_ERROR.value
        elif "validation" in msg or "unprocessable" in msg or "invalid input" in msg:
            return FailureCategory.INPUT_VALIDATION_ERROR.value
        elif "fastembed" in msg or "embedding" in msg or "dimension" in msg:
            return FailureCategory.EMBEDDING_FAILURE.value
        elif "qdrant" in msg or "vector search" in msg:
            return FailureCategory.RETRIEVAL_FAILURE.value
        elif "no relevant evidence" in msg or "abstention" in msg or "evidence insufficient" in msg:
            return FailureCategory.NO_RELEVANT_EVIDENCE.value
        elif "citation" in msg or "hallucinated citation" in msg:
            return FailureCategory.CITATION_VALIDATION_FAILURE.value
        elif "verification" in msg or "unsupported claim" in msg:
            return FailureCategory.VERIFICATION_FAILURE.value
        elif "prohibited" in msg or "policy" in msg or "violat" in msg:
            return FailureCategory.POLICY_VIOLATION.value
        elif "version mismatch" in msg or "approval" in msg or "conflict" in msg:
            return FailureCategory.APPROVAL_CONFLICT.value
        elif "pypdf" in msg or "docx" in msg or "ocr_unavailable" in msg or "chunk" in msg:
            return FailureCategory.DOCUMENT_PROCESSING_FAILURE.value
        elif "indexing" in msg or "point" in msg:
            return FailureCategory.INDEXING_FAILURE.value
        elif "database" in msg or "postgres" in msg or "asyncpg" in msg:
            return FailureCategory.DATABASE_FAILURE.value
        elif "redis" in msg or "queue" in msg or "worker" in msg:
            return FailureCategory.QUEUE_FAILURE.value
        elif "config" in msg or "missing" in msg or "environ" in msg:
            return FailureCategory.CONFIGURATION_ERROR.value
        return FailureCategory.UNKNOWN_ERROR.value

    @staticmethod
    def generate_hypotheses(category: str, error_summary: str) -> list[dict[str, Any]]:
        """Generate structured diagnostic hypotheses and remediation suggestions based on failure type."""
        hypotheses: list[dict[str, Any]] = []

        if category == FailureCategory.NO_RELEVANT_EVIDENCE.value:
            hypotheses.append(
                {
                    "hypothesis": "Knowledge base collection lacks indexed documents covering the queried topic.",
                    "confidence": "high",
                    "recommended_action": "Verify document upload and ensure processing status is INDEXED.",
                }
            )
            hypotheses.append(
                {
                    "hypothesis": "Retrieval score threshold is configured higher than similarity scores.",
                    "confidence": "medium",
                    "recommended_action": "Inspect hybrid search configuration and relevance score threshold.",
                }
            )
        elif category == FailureCategory.EMBEDDING_FAILURE.value:
            hypotheses.append(
                {
                    "hypothesis": "Local FastEmbed ONNX runtime or model cache failure.",
                    "confidence": "high",
                    "recommended_action": "Check disk space and ONNX runtime library availability.",
                }
            )
        elif category == FailureCategory.POLICY_VIOLATION.value:
            hypotheses.append(
                {
                    "hypothesis": "Generated response text triggered a mandatory prohibited term or phrase check.",
                    "confidence": "high",
                    "recommended_action": "Review organization policy rules and adjust response draft wording.",
                }
            )
        elif category == FailureCategory.VERIFICATION_FAILURE.value:
            hypotheses.append(
                {
                    "hypothesis": "Atomic claims in the draft are not supported by retrieved document evidence.",
                    "confidence": "high",
                    "recommended_action": "Add authoritative source documents or revise response claims.",
                }
            )
        elif category == FailureCategory.CITATION_VALIDATION_FAILURE.value:
            hypotheses.append(
                {
                    "hypothesis": "Generated answer fabricated a citation marker not present in retrieved evidence.",
                    "confidence": "high",
                    "recommended_action": "Enforce strict evidence-grounded answering directives in prompt.",
                }
            )
        elif category == FailureCategory.APPROVAL_CONFLICT.value:
            hypotheses.append(
                {
                    "hypothesis": "Draft was revised concurrently, invalidating prior approval requests.",
                    "confidence": "high",
                    "recommended_action": "Reload latest draft version before submitting approval decision.",
                }
            )
        else:
            hypotheses.append(
                {
                    "hypothesis": f"Operational failure in subsystem: {category}",
                    "confidence": "low",
                    "recommended_action": "Inspect execution trace and application logs for detailed diagnostics.",
                }
            )

        return hypotheses

    @classmethod
    async def record_failure(
        cls,
        session: AsyncSession,
        organization_id: uuid.UUID,
        error: Exception | str,
        category: str | None = None,
        severity: str = RiskLevel.MEDIUM.value,
        trace_id: str | None = None,
        request_id: str | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        provider: str | None = None,
        pipeline_version: str | None = "v1.0.0",
    ) -> FailureInvestigation:
        """Record or deduplicate an operational failure investigation."""
        raw_error_str = str(error)
        sanitized_summary = redact_sensitive_data(raw_error_str)
        if not isinstance(sanitized_summary, str):
            sanitized_summary = str(sanitized_summary)

        # Truncate summary to safe length
        sanitized_summary = sanitized_summary[:1000]

        resolved_category = category or cls.classify_failure(raw_error_str)

        # Generate stable fingerprint for deduplication
        # Normalized error key strips numbers and UUIDs for grouping
        normalized_error = "".join(c for c in sanitized_summary if c.isalpha() or c.isspace())[:64]
        fingerprint_input = (
            f"{organization_id}:{resolved_category}:{normalized_error.strip().lower()}"
        )
        fingerprint = hashlib.sha256(fingerprint_input.encode()).hexdigest()[:32]

        now = datetime.now(UTC)

        # Check for existing active investigation with identical fingerprint
        query = select(FailureInvestigation).where(
            FailureInvestigation.organization_id == organization_id,
            FailureInvestigation.fingerprint == fingerprint,
            FailureInvestigation.status.in_(
                [
                    InvestigationStatus.OPEN.value,
                    InvestigationStatus.INVESTIGATING.value,
                ]
            ),
        )
        result = await session.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            existing.occurrence_count += 1
            existing.last_seen_at = now
            if trace_id:
                existing.trace_id = trace_id
            if request_id:
                existing.request_id = request_id
            existing.updated_at = now
            await session.flush()
            return existing

        # Create new investigation
        inv_id_suffix = uuid.uuid4().hex[:6].upper()
        investigation_id = f"INV-{inv_id_suffix}"
        hypotheses = cls.generate_hypotheses(resolved_category, sanitized_summary)

        investigation = FailureInvestigation(
            id=uuid.uuid4(),
            organization_id=organization_id,
            investigation_id=investigation_id,
            fingerprint=fingerprint,
            failure_category=resolved_category,
            severity=severity,
            status=InvestigationStatus.OPEN.value,
            trace_id=trace_id,
            request_id=request_id,
            entity_type=entity_type,
            entity_id=entity_id,
            provider=provider,
            sanitized_error_summary=sanitized_summary,
            first_seen_at=now,
            last_seen_at=now,
            occurrence_count=1,
            pipeline_version=pipeline_version,
            diagnostic_hypotheses=hypotheses,
            created_at=now,
            updated_at=now,
        )
        session.add(investigation)
        await session.flush()
        return investigation

    @staticmethod
    async def list_investigations(
        session: AsyncSession,
        organization_id: uuid.UUID,
        status: str | None = None,
        severity: str | None = None,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[FailureInvestigation], int]:
        """List tenant failure investigations with filtering."""
        query = select(FailureInvestigation).where(
            FailureInvestigation.organization_id == organization_id
        )

        if status:
            query = query.where(FailureInvestigation.status == status)
        if severity:
            query = query.where(FailureInvestigation.severity == severity)
        if category:
            query = query.where(FailureInvestigation.failure_category == category)

        # Count total
        count_res = await session.execute(query)
        total = len(count_res.scalars().all())

        # Paginate
        query = query.order_by(desc(FailureInvestigation.last_seen_at)).limit(limit).offset(offset)
        result = await session.execute(query)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_investigation(
        session: AsyncSession,
        organization_id: uuid.UUID,
        investigation_id: str,
    ) -> FailureInvestigation | None:
        """Retrieve single investigation by ID with tenant isolation."""
        query = select(FailureInvestigation).where(
            FailureInvestigation.organization_id == organization_id,
            FailureInvestigation.investigation_id == investigation_id,
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_investigation(
        session: AsyncSession,
        organization_id: uuid.UUID,
        investigation_id: str,
        status: str,
        resolution_notes: str | None = None,
        assigned_to_user_id: uuid.UUID | None = None,
    ) -> FailureInvestigation | None:
        """Update investigation status, resolution notes, or assigned user."""
        query = select(FailureInvestigation).where(
            FailureInvestigation.organization_id == organization_id,
            FailureInvestigation.investigation_id == investigation_id,
        )
        result = await session.execute(query)
        investigation = result.scalar_one_or_none()

        if not investigation:
            return None

        investigation.status = status
        if resolution_notes is not None:
            investigation.resolution_notes = resolution_notes
        if assigned_to_user_id is not None:
            investigation.assigned_to_user_id = assigned_to_user_id

        now = datetime.now(UTC)
        if status in (InvestigationStatus.RESOLVED.value, InvestigationStatus.IGNORED.value):
            investigation.resolved_at = now
        investigation.updated_at = now

        await session.flush()
        return investigation
