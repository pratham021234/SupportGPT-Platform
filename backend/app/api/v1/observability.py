"""FastAPI router for AI Observability, Traces, Investigations, Evaluations, and Usage."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    status,
)
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import OrganizationContext, require_permission
from app.core.errors import (
    EvaluationRunNotFoundException,
    InvestigationNotFoundException,
    TraceNotFoundException,
)
from app.core.rbac import Permission
from app.db.session import get_db_session
from app.models.ai_operation_trace import AIOperationTrace
from app.schemas.observability import (
    EvaluationCompareResponse,
    EvaluationDetailResponse,
    EvaluationListResponse,
    EvaluationRunResponse,
    InvestigationListResponse,
    InvestigationResponse,
    InvestigationUpdatePayload,
    SystemDiagnosticsResponse,
    TraceDetailResponse,
    TraceListResponse,
    TraceSummaryResponse,
    UsageSummaryResponse,
)
from app.services.observability.diagnostics_service import DiagnosticsService
from app.services.observability.evaluation_service import EvaluationService
from app.services.observability.investigation_service import InvestigationService
from app.services.observability.usage_service import UsageAccountingService

router = APIRouter(
    prefix="/organizations/{organization_id}/observability",
    tags=["AI Observability & Diagnostics"],
)


# =====================================================================
# 1. Platform & Dependency Diagnostics
# =====================================================================


@router.get(
    "/diagnostics",
    response_model=SystemDiagnosticsResponse,
    summary="Platform Readiness & Deep Dependency Diagnostics",
)
async def get_system_diagnostics(
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.OBSERVABILITY_READ))
    ],
) -> SystemDiagnosticsResponse:
    """Return live dependency statuses (PostgreSQL, Redis, Qdrant, Workers, AI Providers)."""
    diag = await DiagnosticsService.get_system_diagnostics()
    return SystemDiagnosticsResponse.model_validate(diag)


# =====================================================================
# 2. AI Execution Traces
# =====================================================================


@router.get(
    "/traces",
    response_model=TraceListResponse,
    summary="List AI workflow execution traces",
)
async def list_execution_traces(
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.OBSERVABILITY_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    operation_type: str | None = Query(None, description="Filter by AI operation type"),
    outcome: str | None = Query(
        None, description="Filter by outcome: success, failure, abstained, blocked"
    ),
    error_category: str | None = Query(None, description="Filter by error category"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> TraceListResponse:
    """List execution traces within organization with filtering."""
    query = select(AIOperationTrace).where(
        AIOperationTrace.organization_id == org_ctx.organization_id
    )

    if operation_type:
        query = query.where(AIOperationTrace.operation_type == operation_type)
    if outcome:
        query = query.where(AIOperationTrace.outcome == outcome)
    if error_category:
        query = query.where(AIOperationTrace.error_category == error_category)

    count_res = await session.execute(query)
    total = len(count_res.scalars().all())

    query = query.order_by(desc(AIOperationTrace.created_at)).limit(limit).offset(offset)
    result = await session.execute(query)
    traces = list(result.scalars().all())

    return TraceListResponse(
        items=[TraceSummaryResponse.model_validate(t, from_attributes=True) for t in traces],
        total=total,
    )


@router.get(
    "/traces/{trace_id}",
    response_model=TraceDetailResponse,
    summary="Get detailed execution trace with spans",
)
async def get_execution_trace(
    trace_id: str,
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.OBSERVABILITY_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TraceDetailResponse:
    """Retrieve single execution trace with spans timeline."""
    query = select(AIOperationTrace).where(
        AIOperationTrace.organization_id == org_ctx.organization_id,
        AIOperationTrace.trace_id == trace_id,
    )
    result = await session.execute(query)
    trace = result.scalar_one_or_none()

    if not trace:
        raise TraceNotFoundException(trace_id)

    return TraceDetailResponse.model_validate(trace, from_attributes=True)


# =====================================================================
# 3. Failure Investigations
# =====================================================================


@router.get(
    "/investigations",
    response_model=InvestigationListResponse,
    summary="List failure investigations",
)
async def list_failure_investigations(
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.OBSERVABILITY_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(
        None, description="Filter by status: open, investigating, resolved, ignored"
    ),
    severity: str | None = Query(
        None, description="Filter by severity: low, medium, high, critical"
    ),
    category: str | None = Query(None, description="Filter by failure category"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> InvestigationListResponse:
    """List operational failure investigations."""
    items, total = await InvestigationService.list_investigations(
        session=session,
        organization_id=org_ctx.organization_id,
        status=status,
        severity=severity,
        category=category,
        limit=limit,
        offset=offset,
    )
    return InvestigationListResponse(
        items=[InvestigationResponse.model_validate(i, from_attributes=True) for i in items],
        total=total,
    )


@router.get(
    "/investigations/{investigation_id}",
    response_model=InvestigationResponse,
    summary="Get failure investigation details",
)
async def get_failure_investigation(
    investigation_id: str,
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.OBSERVABILITY_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> InvestigationResponse:
    """Retrieve single failure investigation with diagnostic hypotheses."""
    item = await InvestigationService.get_investigation(
        session=session,
        organization_id=org_ctx.organization_id,
        investigation_id=investigation_id,
    )
    if not item:
        raise InvestigationNotFoundException(investigation_id)

    return InvestigationResponse.model_validate(item, from_attributes=True)


@router.patch(
    "/investigations/{investigation_id}",
    response_model=InvestigationResponse,
    summary="Update failure investigation status or notes",
)
async def update_failure_investigation(
    investigation_id: str,
    payload: InvestigationUpdatePayload,
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.OBSERVABILITY_MANAGE))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> InvestigationResponse:
    """Update investigation status, assign engineer, or add resolution notes."""
    item = await InvestigationService.update_investigation(
        session=session,
        organization_id=org_ctx.organization_id,
        investigation_id=investigation_id,
        status=payload.status,
        resolution_notes=payload.resolution_notes,
        assigned_to_user_id=payload.assigned_to_user_id,
    )
    if not item:
        raise InvestigationNotFoundException(investigation_id)

    return InvestigationResponse.model_validate(item, from_attributes=True)


# =====================================================================
# 4. Benchmark Evaluations & Regression Analysis
# =====================================================================


@router.get(
    "/evaluations",
    response_model=EvaluationListResponse,
    summary="List benchmark evaluation runs",
)
async def list_evaluations(
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.OBSERVABILITY_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> EvaluationListResponse:
    """List benchmark evaluation runs."""
    items, total = await EvaluationService.list_evaluations(
        session=session,
        organization_id=org_ctx.organization_id,
        limit=limit,
        offset=offset,
    )
    return EvaluationListResponse(
        items=[EvaluationRunResponse.model_validate(e, from_attributes=True) for e in items],
        total=total,
    )


@router.post(
    "/evaluations/run",
    response_model=EvaluationDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger a new benchmark evaluation run",
)
async def run_evaluation_benchmark(
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.OBSERVABILITY_MANAGE))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EvaluationDetailResponse:
    """Execute evaluation benchmark, calculate metrics, and detect regressions against baseline."""
    record = await EvaluationService.run_benchmark(
        session=session,
        organization_id=org_ctx.organization_id,
        user_id=org_ctx.user.id,
    )
    return EvaluationDetailResponse.model_validate(record, from_attributes=True)


@router.get(
    "/evaluations/compare",
    response_model=EvaluationCompareResponse,
    summary="Compare two evaluation runs for quality regressions",
)
async def compare_evaluation_runs(
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.OBSERVABILITY_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    baseline_id: Annotated[uuid.UUID, Query(..., description="Baseline evaluation run ID")],
    candidate_id: Annotated[uuid.UUID, Query(..., description="Candidate evaluation run ID")],
) -> EvaluationCompareResponse:
    """Compare metrics between two runs."""
    comparison = await EvaluationService.compare_runs(
        session=session,
        organization_id=org_ctx.organization_id,
        baseline_id=baseline_id,
        candidate_id=candidate_id,
    )
    if not comparison:
        raise EvaluationRunNotFoundException("comparison_pair")

    return EvaluationCompareResponse.model_validate(comparison)


@router.get(
    "/evaluations/{run_id}",
    response_model=EvaluationDetailResponse,
    summary="Get evaluation run details with per-query findings",
)
async def get_evaluation_run(
    run_id: uuid.UUID,
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.OBSERVABILITY_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EvaluationDetailResponse:
    """Retrieve single evaluation benchmark run."""
    run = await EvaluationService.get_evaluation(
        session=session,
        organization_id=org_ctx.organization_id,
        run_id=run_id,
    )
    if not run:
        raise EvaluationRunNotFoundException(str(run_id))

    return EvaluationDetailResponse.model_validate(run, from_attributes=True)


# =====================================================================
# 5. Usage & Cost Accounting
# =====================================================================


@router.get(
    "/usage",
    response_model=UsageSummaryResponse,
    summary="Get organization AI token usage and estimated cost",
)
async def get_usage_summary(
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.OBSERVABILITY_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    start_date: datetime | None = Query(None, description="Start timestamp filter"),
    end_date: datetime | None = Query(None, description="End timestamp filter"),
) -> UsageSummaryResponse:
    """Aggregate token consumption and estimated cost across models and operations."""
    summary = await UsageAccountingService.get_usage_summary(
        session=session,
        organization_id=org_ctx.organization_id,
        start_date=start_date,
        end_date=end_date,
    )
    return UsageSummaryResponse.model_validate(summary)
