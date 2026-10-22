"""AI Execution Tracer and Span instrumentation for end-to-end workflow observability."""

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger, trace_id_ctx
from app.models.ai_operation_trace import AIOperationTrace
from app.models.enums import AIOperationType, FailureCategory, TraceOutcome

logger = get_logger("supportgpt.observability.tracer")


@dataclass
class ExecutionSpan:
    """Granular execution stage within an operation trace."""

    stage: str
    start_ms: float
    duration_ms: float = 0.0
    outcome: str = TraceOutcome.SUCCESS.value
    details: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None


class AITraceContext:
    """Context manager capturing stages, timing, and outcomes of an AI operation."""

    def __init__(
        self,
        organization_id: uuid.UUID,
        operation_type: str,
        provider: str = "system",
        model: str = "none",
        request_id: str | None = None,
        user_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        pipeline_version: str | None = "v1.0.0",
        policy_version: str | None = None,
    ) -> None:
        self.trace_id = str(uuid.uuid4())
        self.organization_id = organization_id
        self.operation_type = operation_type
        self.provider = provider
        self.model = model
        self.request_id = request_id
        self.user_id = user_id
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.pipeline_version = pipeline_version
        self.policy_version = policy_version

        self.start_time: datetime = datetime.now(UTC)
        self.start_perf: float = time.perf_counter()
        self.end_time: datetime | None = None
        self.duration_ms: float = 0.0

        self.outcome: str = TraceOutcome.SUCCESS.value
        self.error_category: str | None = None
        self.error_message: str | None = None
        self.retry_count: int = 0
        self.evidence_count: int = 0
        self.token_usage: dict[str, Any] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "embedding_tokens": 0,
            "total_tokens": 0,
        }
        self.estimated_cost_usd: float | None = 0.0
        self.spans: list[ExecutionSpan] = []

    @asynccontextmanager
    async def span(
        self, stage: str, details: dict[str, Any] | None = None
    ) -> AsyncIterator[ExecutionSpan]:
        """Record an execution stage span within this trace."""
        start_ms = (time.perf_counter() - self.start_perf) * 1000
        span_obj = ExecutionSpan(
            stage=stage,
            start_ms=round(start_ms, 2),
            details=details or {},
        )
        stage_start = time.perf_counter()
        try:
            yield span_obj
            span_obj.duration_ms = round((time.perf_counter() - stage_start) * 1000, 2)
            span_obj.outcome = TraceOutcome.SUCCESS.value
        except Exception as exc:
            span_obj.duration_ms = round((time.perf_counter() - stage_start) * 1000, 2)
            span_obj.outcome = TraceOutcome.FAILURE.value
            span_obj.error_message = str(exc)
            raise
        finally:
            self.spans.append(span_obj)

    def set_tokens(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        embedding_tokens: int = 0,
        estimated_cost_usd: float | None = None,
    ) -> None:
        """Update token usage counts and cost."""
        self.token_usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "embedding_tokens": embedding_tokens,
            "total_tokens": input_tokens + output_tokens + embedding_tokens,
        }
        if estimated_cost_usd is not None:
            self.estimated_cost_usd = estimated_cost_usd

    def record_failure(self, category: str, error_msg: str) -> None:
        """Record operational failure."""
        self.outcome = TraceOutcome.FAILURE.value
        self.error_category = category
        self.error_message = error_msg

    def record_abstention(self, reason: str) -> None:
        """Record explicit AI abstention."""
        self.outcome = TraceOutcome.ABSTAINED.value
        self.error_category = FailureCategory.NO_RELEVANT_EVIDENCE.value
        self.error_message = reason

    def record_blocked(self, policy_reason: str) -> None:
        """Record policy or verification block."""
        self.outcome = TraceOutcome.BLOCKED.value
        self.error_category = FailureCategory.POLICY_VIOLATION.value
        self.error_message = policy_reason

    def finalize(self) -> None:
        """Complete timing calculations."""
        self.end_time = datetime.now(UTC)
        self.duration_ms = round((time.perf_counter() - self.start_perf) * 1000, 2)


class AITracer:
    """Service for initiating and persisting execution traces."""

    @staticmethod
    @asynccontextmanager
    async def start_trace(
        session: AsyncSession,
        organization_id: uuid.UUID,
        operation_type: str = AIOperationType.RAG_QUERY.value,
        provider: str = "system",
        model: str = "none",
        request_id: str | None = None,
        user_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        pipeline_version: str | None = "v1.0.0",
        policy_version: str | None = None,
    ) -> AsyncIterator[AITraceContext]:
        """Start an AI operation trace and safely persist it on completion."""
        trace_ctx = AITraceContext(
            organization_id=organization_id,
            operation_type=operation_type,
            provider=provider,
            model=model,
            request_id=request_id,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            pipeline_version=pipeline_version,
            policy_version=policy_version,
        )

        token = trace_id_ctx.set(trace_ctx.trace_id)
        try:
            yield trace_ctx
        finally:
            trace_id_ctx.reset(token)
            trace_ctx.finalize()
            try:
                # Persist trace record without failing the business operation if DB insert fails
                db_trace = AIOperationTrace(
                    id=uuid.UUID(trace_ctx.trace_id),
                    organization_id=trace_ctx.organization_id,
                    trace_id=trace_ctx.trace_id,
                    request_id=trace_ctx.request_id,
                    user_id=trace_ctx.user_id,
                    operation_type=trace_ctx.operation_type,
                    entity_type=trace_ctx.entity_type,
                    entity_id=trace_ctx.entity_id,
                    provider=trace_ctx.provider,
                    model=trace_ctx.model,
                    start_time=trace_ctx.start_time,
                    end_time=trace_ctx.end_time or datetime.now(UTC),
                    duration_ms=trace_ctx.duration_ms,
                    outcome=trace_ctx.outcome,
                    error_category=trace_ctx.error_category,
                    error_message=trace_ctx.error_message,
                    retry_count=trace_ctx.retry_count,
                    evidence_count=trace_ctx.evidence_count,
                    token_usage=trace_ctx.token_usage,
                    estimated_cost_usd=trace_ctx.estimated_cost_usd,
                    pipeline_version=trace_ctx.pipeline_version,
                    policy_version=trace_ctx.policy_version,
                    spans=[
                        {
                            "stage": s.stage,
                            "start_ms": s.start_ms,
                            "duration_ms": s.duration_ms,
                            "outcome": s.outcome,
                            "details": s.details,
                            "error_message": s.error_message,
                        }
                        for s in trace_ctx.spans
                    ],
                    created_at=datetime.now(UTC),
                )
                session.add(db_trace)
                await session.flush()
            except Exception as exc:
                logger.warning(
                    f"Failed to persist AI operation trace [{trace_ctx.trace_id}]: {exc}"
                )
