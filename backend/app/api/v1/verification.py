"""FastAPI router for Response Verification, Policy Enforcement, and Human Approvals."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Path,
    Query,
    status,
)
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import OrganizationContext, require_permission
from app.core.errors import (
    ApprovalNotFoundException,
    DraftNotFoundException,
    PolicyNotFoundException,
)
from app.core.rbac import Permission
from app.db.session import get_db_session
from app.models.approval_request import ApprovalRequest
from app.models.claim_finding import ClaimFinding
from app.models.enums import (
    DraftLifecycleStatus,
    RiskLevel,
    VerificationAuditEventType,
    VerificationStatus,
)
from app.models.policy_rule import PolicyRule
from app.models.response_draft import ResponseDraft
from app.models.verification_run import VerificationRun
from app.schemas.verification import (
    ApprovalDecisionRequest,
    ApprovalRequestCreateRequest,
    ApprovalRequestListResponse,
    ApprovalRequestResponse,
    ClaimFindingResponse,
    PolicyFindingResponse,
    PolicyRuleCreateRequest,
    PolicyRuleListResponse,
    PolicyRuleResponse,
    PolicyRuleUpdateRequest,
    ResponseDraftCreateRequest,
    ResponseDraftListResponse,
    ResponseDraftResponse,
    ResponseDraftUpdateRequest,
    VerificationAuditEventListResponse,
    VerificationAuditEventResponse,
    VerificationRunListResponse,
    VerificationRunResponse,
)
from app.services.verification.approval_service import ApprovalService
from app.services.verification.audit_service import VerificationAuditService
from app.services.verification.pipeline import ResponseVerificationPipeline

router = APIRouter(prefix="/organizations/{organization_id}", tags=["Verification & Governance"])


# =====================================================================
# 1. Response Drafts
# =====================================================================


@router.post(
    "/drafts",
    response_model=ResponseDraftResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new response draft candidate",
)
async def create_response_draft(
    payload: ResponseDraftCreateRequest,
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.VERIFICATION_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseDraftResponse:
    now = datetime.now(UTC)
    draft = ResponseDraft(
        organization_id=org_ctx.organization_id,
        ticket_id=payload.ticket_id,
        conversation_id=payload.conversation_id,
        original_query=payload.original_query,
        draft_text=payload.draft_text,
        version_number=1,
        lifecycle_status=DraftLifecycleStatus.DRAFT.value,
        evidence_references=payload.evidence_references,
        created_by_user_id=org_ctx.user.id,
        created_at=now,
        updated_at=now,
    )
    session.add(draft)
    await session.flush()

    await VerificationAuditService.record_event(
        session=session,
        organization_id=org_ctx.organization_id,
        event_type=VerificationAuditEventType.DRAFT_CREATED,
        entity_type="draft",
        entity_id=draft.id,
        actor_id=org_ctx.user.id,
        event_summary=f"Created response draft v1 (length: {len(draft.draft_text)} chars)",
        metadata_json={"ticket_id": str(payload.ticket_id) if payload.ticket_id else None},
    )

    return ResponseDraftResponse.model_validate(draft, from_attributes=True)


@router.get(
    "/drafts",
    response_model=ResponseDraftListResponse,
    summary="List response drafts within organization",
)
async def list_response_drafts(
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.VERIFICATION_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    ticket_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ResponseDraftListResponse:
    stmt = (
        select(ResponseDraft)
        .where(ResponseDraft.organization_id == org_ctx.organization_id)
        .order_by(desc(ResponseDraft.created_at))
        .limit(limit)
        .offset(offset)
    )
    if ticket_id:
        stmt = stmt.where(ResponseDraft.ticket_id == ticket_id)
    if status:
        stmt = stmt.where(ResponseDraft.lifecycle_status == status)

    res = await session.execute(stmt)
    drafts = list(res.scalars().all())

    return ResponseDraftListResponse(
        items=[ResponseDraftResponse.model_validate(d, from_attributes=True) for d in drafts],
        total=len(drafts),
    )


@router.get(
    "/drafts/{draft_id}",
    response_model=ResponseDraftResponse,
    summary="Get single response draft by ID",
)
async def get_response_draft(
    draft_id: Annotated[uuid.UUID, Path(...)],
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.VERIFICATION_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseDraftResponse:
    stmt = select(ResponseDraft).where(
        ResponseDraft.id == draft_id,
        ResponseDraft.organization_id == org_ctx.organization_id,
    )
    res = await session.execute(stmt)
    draft = res.scalar_one_or_none()
    if not draft:
        raise DraftNotFoundException(draft_id)

    return ResponseDraftResponse.model_validate(draft, from_attributes=True)


@router.put(
    "/drafts/{draft_id}",
    response_model=ResponseDraftResponse,
    summary="Revise a response draft (increments version and invalidates existing approvals)",
)
async def revise_response_draft(
    draft_id: Annotated[uuid.UUID, Path(...)],
    payload: ResponseDraftUpdateRequest,
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.VERIFICATION_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseDraftResponse:
    stmt = select(ResponseDraft).where(
        ResponseDraft.id == draft_id,
        ResponseDraft.organization_id == org_ctx.organization_id,
    )
    res = await session.execute(stmt)
    draft = res.scalar_one_or_none()
    if not draft:
        raise DraftNotFoundException(draft_id)

    old_version = draft.version_number
    new_version = old_version + 1

    draft.draft_text = payload.draft_text
    draft.version_number = new_version
    draft.lifecycle_status = DraftLifecycleStatus.DRAFT.value
    if payload.evidence_references is not None:
        draft.evidence_references = payload.evidence_references

    draft.updated_at = datetime.now(UTC)
    await session.flush()

    # Automatically invalidate any prior approval requests for previous versions
    await ApprovalService.invalidate_prior_approvals_for_draft(
        session=session,
        organization_id=org_ctx.organization_id,
        draft_id=draft.id,
        new_version_number=new_version,
        actor_id=org_ctx.user.id,
    )

    # Record revision audit event
    await VerificationAuditService.record_event(
        session=session,
        organization_id=org_ctx.organization_id,
        event_type=VerificationAuditEventType.DRAFT_REVISED,
        entity_type="draft",
        entity_id=draft.id,
        actor_id=org_ctx.user.id,
        event_summary=f"Revised draft from v{old_version} to v{new_version}",
        metadata_json={"old_version": old_version, "new_version": new_version},
    )

    return ResponseDraftResponse.model_validate(draft, from_attributes=True)


# =====================================================================
# 2. Verification Execution & Runs
# =====================================================================


@router.post(
    "/drafts/{draft_id}/verify",
    response_model=VerificationRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute verification pipeline on response draft",
)
async def verify_response_draft(
    draft_id: Annotated[uuid.UUID, Path(...)],
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.VERIFICATION_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> VerificationRunResponse:
    # 1. Fetch draft under tenant check
    stmt = select(ResponseDraft).where(
        ResponseDraft.id == draft_id,
        ResponseDraft.organization_id == org_ctx.organization_id,
    )
    res = await session.execute(stmt)
    draft = res.scalar_one_or_none()
    if not draft:
        raise DraftNotFoundException(draft_id)

    # 2. Fetch active policies for organization
    policy_stmt = (
        select(PolicyRule)
        .where(
            PolicyRule.organization_id == org_ctx.organization_id,
            PolicyRule.is_enabled == True,  # noqa: E712
        )
        .order_by(PolicyRule.created_at)
    )
    policy_res = await session.execute(policy_stmt)
    policies = list(policy_res.scalars().all())

    # 3. Execute pipeline with distributed execution tracing
    from app.models.enums import AIOperationType, FailureCategory
    from app.services.observability.investigation_service import InvestigationService
    from app.services.observability.tracer import AITracer
    from app.services.observability.usage_service import UsageAccountingService

    async with AITracer.start_trace(
        session=session,
        organization_id=org_ctx.organization_id,
        operation_type=AIOperationType.RESPONSE_VERIFICATION.value,
        provider="deterministic",
        model="rules-v1",
        user_id=org_ctx.user.id,
        entity_type="draft",
        entity_id=draft.id,
        pipeline_version="v1.0.0",
    ) as trace:
        pipeline = ResponseVerificationPipeline()
        async with trace.span("verification_pipeline"):
            result = await pipeline.verify_draft(draft, policies)

        trace.evidence_count = len(draft.evidence_references or [])
        claim_tokens = sum(len(c.claim_text.split()) for c in result.claim_results) * 2
        trace.set_tokens(input_tokens=claim_tokens, output_tokens=0, embedding_tokens=0)

        if result.status == VerificationStatus.BLOCKED:
            failed_rules = result.machine_readable_findings.get("failed_policies", [])
            trace.record_blocked(f"Blocked by policy or contradiction: {failed_rules}")
            await InvestigationService.record_failure(
                session=session,
                organization_id=org_ctx.organization_id,
                error=f"Draft v{draft.version_number} verification blocked: {failed_rules}",
                category=FailureCategory.POLICY_VIOLATION.value,
                severity=result.risk_level.value,
                trace_id=trace.trace_id,
                entity_type="draft",
                entity_id=draft.id,
            )
        elif result.status == VerificationStatus.FAILED:
            trace.record_failure(
                FailureCategory.VERIFICATION_FAILURE.value,
                result.error_message or "Verification failed",
            )
            await InvestigationService.record_failure(
                session=session,
                organization_id=org_ctx.organization_id,
                error=result.error_message or "Verification failed",
                category=FailureCategory.VERIFICATION_FAILURE.value,
                severity=result.risk_level.value,
                trace_id=trace.trace_id,
                entity_type="draft",
                entity_id=draft.id,
            )

        # Record usage
        await UsageAccountingService.record_usage(
            session=session,
            organization_id=org_ctx.organization_id,
            operation_type=AIOperationType.RESPONSE_VERIFICATION.value,
            provider="deterministic",
            model="rules-v1",
            input_tokens=claim_tokens,
            output_tokens=0,
            trace_id=trace.trace_id,
        )

    # 4. Determine policy set version
    policy_version = max([p.version_number for p in policies], default=1)

    # 5. Persist VerificationRun
    now = datetime.now(UTC)
    run_id = uuid.uuid4()
    run = VerificationRun(
        id=run_id,
        organization_id=org_ctx.organization_id,
        draft_id=draft.id,
        draft_version=draft.version_number,
        verification_pipeline_version="v1.0.0",
        policy_set_version=policy_version,
        status=result.status.value,
        risk_level=result.risk_level.value,
        requires_human_approval=result.requires_human_approval,
        machine_readable_findings=result.machine_readable_findings,
        evidence_references=draft.evidence_references,
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
        execution_time_ms=result.execution_time_ms,
        error_message=result.error_message,
    )
    session.add(run)
    await session.flush()

    # 6. Persist ClaimFinding records
    claim_responses = []
    for c in result.claim_results:
        finding_id = uuid.uuid4()
        finding = ClaimFinding(
            id=finding_id,
            organization_id=org_ctx.organization_id,
            verification_run_id=run.id,
            claim_text=c.claim_text,
            claim_category=c.claim_category.value,
            support_status=c.support_status.value,
            evidence_chunk_ids=c.evidence_chunk_ids,
            confidence_score=c.confidence_score,
            reason=c.reason,
            verification_method=c.verification_method.value,
            created_at=now,
        )
        session.add(finding)
        claim_responses.append(
            ClaimFindingResponse(
                id=finding_id,
                claim_text=c.claim_text,
                claim_category=c.claim_category,
                support_status=c.support_status,
                evidence_chunk_ids=c.evidence_chunk_ids,
                confidence_score=c.confidence_score,
                reason=c.reason,
                verification_method=c.verification_method,
            )
        )

    # 7. Update draft lifecycle status
    if result.status == VerificationStatus.BLOCKED:
        draft.lifecycle_status = DraftLifecycleStatus.VERIFICATION_FAILED.value
    elif result.status == VerificationStatus.NEEDS_REVISION:
        draft.lifecycle_status = DraftLifecycleStatus.REVISION_REQUIRED.value
    elif result.requires_human_approval:
        draft.lifecycle_status = DraftLifecycleStatus.APPROVAL_PENDING.value
    else:
        draft.lifecycle_status = DraftLifecycleStatus.VERIFIED.value

    draft.updated_at = now
    await session.flush()

    # 8. Record audit event
    await VerificationAuditService.record_event(
        session=session,
        organization_id=org_ctx.organization_id,
        event_type=VerificationAuditEventType.VERIFICATION_COMPLETED,
        entity_type="verification_run",
        entity_id=run.id,
        actor_id=org_ctx.user.id,
        event_summary=f"Verification run finished: {result.status.value.upper()} (Risk: {result.risk_level.value})",
        metadata_json={
            "draft_id": str(draft.id),
            "draft_version": draft.version_number,
            "status": result.status.value,
            "risk_level": result.risk_level.value,
            "requires_approval": result.requires_human_approval,
        },
    )

    policy_finding_responses = [
        PolicyFindingResponse(
            policy_id=p.policy_id,
            rule_name=p.rule_name,
            policy_category=p.policy_category,
            rule_type=p.rule_type,
            severity=p.severity,
            passed=p.passed,
            requires_approval=p.requires_approval,
            details=p.details,
        )
        for p in result.policy_findings
    ]

    return VerificationRunResponse(
        id=run.id,
        organization_id=run.organization_id,
        draft_id=run.draft_id,
        draft_version=run.draft_version,
        verification_pipeline_version=run.verification_pipeline_version,
        policy_set_version=run.policy_set_version,
        status=result.status,
        risk_level=result.risk_level,
        requires_human_approval=result.requires_human_approval,
        machine_readable_findings=result.machine_readable_findings,
        claim_findings=claim_responses,
        policy_findings=policy_finding_responses,
        started_at=run.started_at,
        completed_at=run.completed_at,
        execution_time_ms=run.execution_time_ms,
        request_id=run.request_id,
        error_message=run.error_message,
    )


@router.get(
    "/drafts/{draft_id}/verification-runs",
    response_model=VerificationRunListResponse,
    summary="List verification runs for a draft",
)
async def list_verification_runs(
    draft_id: Annotated[uuid.UUID, Path(...)],
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.VERIFICATION_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> VerificationRunListResponse:
    stmt = (
        select(VerificationRun)
        .where(
            VerificationRun.draft_id == draft_id,
            VerificationRun.organization_id == org_ctx.organization_id,
        )
        .order_by(desc(VerificationRun.started_at))
    )
    res = await session.execute(stmt)
    runs = list(res.scalars().all())

    items = []
    for r in runs:
        # Load claim findings
        cf_stmt = select(ClaimFinding).where(ClaimFinding.verification_run_id == r.id)
        cf_res = await session.execute(cf_stmt)
        cfs = list(cf_res.scalars().all())

        items.append(
            VerificationRunResponse(
                id=r.id,
                organization_id=r.organization_id,
                draft_id=r.draft_id,
                draft_version=r.draft_version,
                verification_pipeline_version=r.verification_pipeline_version,
                policy_set_version=r.policy_set_version,
                status=VerificationStatus(r.status),
                risk_level=RiskLevel(r.risk_level),
                requires_human_approval=r.requires_human_approval,
                machine_readable_findings=r.machine_readable_findings,
                claim_findings=[
                    ClaimFindingResponse(
                        id=cf.id,
                        claim_text=cf.claim_text,
                        claim_category=cf.claim_category,
                        support_status=cf.support_status,
                        evidence_chunk_ids=cf.evidence_chunk_ids,
                        confidence_score=cf.confidence_score,
                        reason=cf.reason,
                        verification_method=cf.verification_method,
                    )
                    for cf in cfs
                ],
                policy_findings=[],
                started_at=r.started_at,
                completed_at=r.completed_at,
                execution_time_ms=r.execution_time_ms,
                request_id=r.request_id,
                error_message=r.error_message,
            )
        )

    return VerificationRunListResponse(items=items, total=len(items))


# =====================================================================
# 3. Policy Management
# =====================================================================


@router.get(
    "/policies",
    response_model=PolicyRuleListResponse,
    summary="List organization compliance policies",
)
async def list_policies(
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.VERIFICATION_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PolicyRuleListResponse:
    stmt = (
        select(PolicyRule)
        .where(PolicyRule.organization_id == org_ctx.organization_id)
        .order_by(PolicyRule.created_at)
    )
    res = await session.execute(stmt)
    policies = list(res.scalars().all())

    return PolicyRuleListResponse(
        items=[PolicyRuleResponse.model_validate(p, from_attributes=True) for p in policies],
        total=len(policies),
    )


@router.post(
    "/policies",
    response_model=PolicyRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new policy rule",
)
async def create_policy(
    payload: PolicyRuleCreateRequest,
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.POLICIES_MANAGE))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PolicyRuleResponse:
    now = datetime.now(UTC)
    policy = PolicyRule(
        organization_id=org_ctx.organization_id,
        name=payload.name,
        description=payload.description,
        policy_category=payload.policy_category.value,
        severity=payload.severity.value,
        rule_type=payload.rule_type.value,
        rule_config=payload.rule_config,
        is_enabled=payload.is_enabled,
        version_number=1,
        created_by_user_id=org_ctx.user.id,
        created_at=now,
        updated_at=now,
    )
    session.add(policy)
    await session.flush()

    await VerificationAuditService.record_event(
        session=session,
        organization_id=org_ctx.organization_id,
        event_type=VerificationAuditEventType.POLICY_CREATED,
        entity_type="policy",
        entity_id=policy.id,
        actor_id=org_ctx.user.id,
        event_summary=f"Created policy rule '{policy.name}' (Category: {policy.policy_category})",
        metadata_json={"rule_type": policy.rule_type, "severity": policy.severity},
    )

    return PolicyRuleResponse.model_validate(policy, from_attributes=True)


@router.put(
    "/policies/{policy_id}",
    response_model=PolicyRuleResponse,
    summary="Update an existing policy rule (increments version)",
)
async def update_policy(
    policy_id: Annotated[uuid.UUID, Path(...)],
    payload: PolicyRuleUpdateRequest,
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.POLICIES_MANAGE))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PolicyRuleResponse:
    stmt = select(PolicyRule).where(
        PolicyRule.id == policy_id,
        PolicyRule.organization_id == org_ctx.organization_id,
    )
    res = await session.execute(stmt)
    policy = res.scalar_one_or_none()
    if not policy:
        raise PolicyNotFoundException(policy_id)

    old_version = policy.version_number
    policy.version_number = old_version + 1

    if payload.name is not None:
        policy.name = payload.name
    if payload.description is not None:
        policy.description = payload.description
    if payload.severity is not None:
        policy.severity = payload.severity.value
    if payload.rule_config is not None:
        policy.rule_config = payload.rule_config
    if payload.is_enabled is not None:
        policy.is_enabled = payload.is_enabled

    policy.updated_at = datetime.now(UTC)
    await session.flush()

    await VerificationAuditService.record_event(
        session=session,
        organization_id=org_ctx.organization_id,
        event_type=VerificationAuditEventType.POLICY_UPDATED,
        entity_type="policy",
        entity_id=policy.id,
        actor_id=org_ctx.user.id,
        event_summary=f"Updated policy '{policy.name}' to version {policy.version_number}",
        metadata_json={"old_version": old_version, "new_version": policy.version_number},
    )

    return PolicyRuleResponse.model_validate(policy, from_attributes=True)


@router.patch(
    "/policies/{policy_id}/toggle",
    response_model=PolicyRuleResponse,
    summary="Enable or disable a policy rule",
)
async def toggle_policy(
    policy_id: Annotated[uuid.UUID, Path(...)],
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.POLICIES_MANAGE))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PolicyRuleResponse:
    stmt = select(PolicyRule).where(
        PolicyRule.id == policy_id,
        PolicyRule.organization_id == org_ctx.organization_id,
    )
    res = await session.execute(stmt)
    policy = res.scalar_one_or_none()
    if not policy:
        raise PolicyNotFoundException(policy_id)

    policy.is_enabled = not policy.is_enabled
    policy.updated_at = datetime.now(UTC)
    await session.flush()

    await VerificationAuditService.record_event(
        session=session,
        organization_id=org_ctx.organization_id,
        event_type=VerificationAuditEventType.POLICY_TOGGLED,
        entity_type="policy",
        entity_id=policy.id,
        actor_id=org_ctx.user.id,
        event_summary=f"Policy '{policy.name}' toggled to {'enabled' if policy.is_enabled else 'disabled'}",
        metadata_json={"is_enabled": policy.is_enabled},
    )

    return PolicyRuleResponse.model_validate(policy, from_attributes=True)


# =====================================================================
# 4. Human Approval Workflow
# =====================================================================


@router.post(
    "/drafts/{draft_id}/approvals",
    response_model=ApprovalRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit response draft for human approval",
)
async def request_approval(
    draft_id: Annotated[uuid.UUID, Path(...)],
    payload: ApprovalRequestCreateRequest,
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.VERIFICATION_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApprovalRequestResponse:
    approval_req = await ApprovalService.create_approval_request(
        session=session,
        organization_id=org_ctx.organization_id,
        draft_id=draft_id,
        draft_version=payload.draft_version,
        verification_run_id=payload.verification_run_id,
        requested_by_user_id=org_ctx.user.id,
        required_role=payload.required_role,
        separation_of_duties=payload.separation_of_duties,
    )
    return ApprovalRequestResponse.model_validate(approval_req, from_attributes=True)


@router.get(
    "/approvals",
    response_model=ApprovalRequestListResponse,
    summary="List approval requests in organization",
)
async def list_approvals(
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.VERIFICATION_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApprovalRequestListResponse:
    stmt = (
        select(ApprovalRequest)
        .where(ApprovalRequest.organization_id == org_ctx.organization_id)
        .order_by(desc(ApprovalRequest.created_at))
        .limit(limit)
        .offset(offset)
    )
    if status:
        stmt = stmt.where(ApprovalRequest.status == status)

    res = await session.execute(stmt)
    reqs = list(res.scalars().all())

    return ApprovalRequestListResponse(
        items=[ApprovalRequestResponse.model_validate(r, from_attributes=True) for r in reqs],
        total=len(reqs),
    )


@router.get(
    "/approvals/{approval_id}",
    response_model=ApprovalRequestResponse,
    summary="Get single approval request by ID",
)
async def get_approval(
    approval_id: Annotated[uuid.UUID, Path(...)],
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.VERIFICATION_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApprovalRequestResponse:
    stmt = select(ApprovalRequest).where(
        ApprovalRequest.id == approval_id,
        ApprovalRequest.organization_id == org_ctx.organization_id,
    )
    res = await session.execute(stmt)
    req = res.scalar_one_or_none()
    if not req:
        raise ApprovalNotFoundException(approval_id)

    return ApprovalRequestResponse.model_validate(req, from_attributes=True)


@router.post(
    "/approvals/{approval_id}/decision",
    response_model=ApprovalRequestResponse,
    summary="Commit human decision (approve, reject, or request revision)",
)
async def decide_approval(
    approval_id: Annotated[uuid.UUID, Path(...)],
    payload: ApprovalDecisionRequest,
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.VERIFICATION_APPROVE))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApprovalRequestResponse:
    approval_req, _ = await ApprovalService.decide_approval(
        session=session,
        organization_id=org_ctx.organization_id,
        approval_id=approval_id,
        decider=org_ctx.user,
        decision=payload.decision,
        decision_reason=payload.reason,
    )
    return ApprovalRequestResponse.model_validate(approval_req, from_attributes=True)


# =====================================================================
# 5. Append-Only Audit Trail
# =====================================================================


@router.get(
    "/verification-audit",
    response_model=VerificationAuditEventListResponse,
    summary="Query append-only audit trail for verification and approvals",
)
async def list_audit_trail(
    org_ctx: Annotated[
        OrganizationContext, Depends(require_permission(Permission.VERIFICATION_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> VerificationAuditEventListResponse:
    events = await VerificationAuditService.list_audit_events(
        session=session,
        organization_id=org_ctx.organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    return VerificationAuditEventListResponse(
        items=[
            VerificationAuditEventResponse.model_validate(e, from_attributes=True) for e in events
        ],
        total=len(events),
    )
