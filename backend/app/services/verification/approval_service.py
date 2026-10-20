"""Human approval workflow service with separation-of-duties and version invalidation."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ApprovalNotFoundException,
    DraftNotFoundException,
    InvalidApprovalStateException,
    SelfApprovalForbiddenException,
    StaleDraftApprovalException,
)
from app.models.approval_request import ApprovalRequest
from app.models.enums import (
    ApprovalDecisionType,
    ApprovalStatus,
    DraftLifecycleStatus,
    MembershipRole,
    VerificationAuditEventType,
)
from app.models.response_draft import ResponseDraft
from app.models.user import User
from app.services.verification.audit_service import VerificationAuditService


class ApprovalService:
    """Manages the lifecycle of human approval requests for AI-generated response drafts."""

    @staticmethod
    async def create_approval_request(
        session: AsyncSession,
        organization_id: uuid.UUID,
        draft_id: uuid.UUID,
        draft_version: int,
        verification_run_id: uuid.UUID,
        requested_by_user_id: uuid.UUID | None = None,
        required_role: MembershipRole | str = MembershipRole.AGENT,
        separation_of_duties: bool = True,
        request_id: str | None = None,
    ) -> ApprovalRequest:
        """Create a new pending approval request bound to an exact draft version."""
        # 1. Authoritative draft lookup
        stmt = select(ResponseDraft).where(
            ResponseDraft.id == draft_id,
            ResponseDraft.organization_id == organization_id,
        )
        res = await session.execute(stmt)
        draft = res.scalar_one_or_none()
        if not draft:
            raise DraftNotFoundException(draft_id)

        # 2. Check if an active pending request already exists for this exact draft and version
        pending_stmt = select(ApprovalRequest).where(
            ApprovalRequest.organization_id == organization_id,
            ApprovalRequest.draft_id == draft_id,
            ApprovalRequest.draft_version == draft_version,
            ApprovalRequest.status == ApprovalStatus.PENDING.value,
        )
        existing_res = await session.execute(pending_stmt)
        existing = existing_res.scalar_one_or_none()
        if existing:
            return existing

        role_str = (
            required_role.value if isinstance(required_role, MembershipRole) else str(required_role)
        )
        now = datetime.now(UTC)

        approval_req = ApprovalRequest(
            organization_id=organization_id,
            draft_id=draft_id,
            draft_version=draft_version,
            verification_run_id=verification_run_id,
            status=ApprovalStatus.PENDING.value,
            required_role=role_str,
            separation_of_duties=separation_of_duties,
            requested_by_user_id=requested_by_user_id,
            created_at=now,
            updated_at=now,
        )
        session.add(approval_req)

        # Update draft lifecycle status
        draft.lifecycle_status = DraftLifecycleStatus.APPROVAL_PENDING.value
        draft.updated_at = now
        await session.flush()

        # Audit event
        await VerificationAuditService.record_event(
            session=session,
            organization_id=organization_id,
            event_type=VerificationAuditEventType.APPROVAL_REQUESTED,
            entity_type="approval_request",
            entity_id=approval_req.id,
            actor_id=requested_by_user_id,
            request_id=request_id,
            event_summary=f"Approval requested for draft version {draft_version} (Required role: {role_str})",
            metadata_json={
                "draft_id": str(draft_id),
                "draft_version": draft_version,
                "run_id": str(verification_run_id),
            },
        )

        return approval_req

    @staticmethod
    async def decide_approval(
        session: AsyncSession,
        organization_id: uuid.UUID,
        approval_id: uuid.UUID,
        decider: User,
        decision: ApprovalDecisionType | str,
        decision_reason: str | None = None,
        request_id: str | None = None,
    ) -> tuple[ApprovalRequest, ResponseDraft]:
        """Record an explicit human approval, rejection, or revision request with strict safety checks."""
        # 1. Fetch approval request
        stmt = select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.organization_id == organization_id,
        )
        res = await session.execute(stmt)
        approval_req = res.scalar_one_or_none()
        if not approval_req:
            raise ApprovalNotFoundException(approval_id)

        if approval_req.status != ApprovalStatus.PENDING.value:
            raise InvalidApprovalStateException(
                f"Approval request is currently in '{approval_req.status}' state and cannot be decided."
            )

        # 2. Fetch parent draft
        draft_stmt = select(ResponseDraft).where(
            ResponseDraft.id == approval_req.draft_id,
            ResponseDraft.organization_id == organization_id,
        )
        draft_res = await session.execute(draft_stmt)
        draft = draft_res.scalar_one_or_none()
        if not draft:
            raise DraftNotFoundException(approval_req.draft_id)

        # 3. Exact Version Binding Invariant: Ensure draft has not been modified
        if draft.version_number != approval_req.draft_version:
            approval_req.status = ApprovalStatus.INVALIDATED.value
            await session.flush()
            raise StaleDraftApprovalException(
                f"Draft has been updated to version {draft.version_number}. This approval request for version {approval_req.draft_version} is now invalidated."
            )

        # 4. Separation of Duties Invariant: Requester cannot self-approve
        decision_enum = ApprovalDecisionType(decision) if isinstance(decision, str) else decision
        if (
            approval_req.separation_of_duties
            and approval_req.requested_by_user_id is not None
            and approval_req.requested_by_user_id == decider.id
            and decision_enum == ApprovalDecisionType.APPROVE
        ):
            raise SelfApprovalForbiddenException(
                "Self-approval is forbidden under separation of duties. Another authorized team member must review and approve this draft."
            )

        now = datetime.now(UTC)
        approval_req.decision_by_user_id = decider.id
        approval_req.decision_reason = decision_reason
        approval_req.decided_at = now
        approval_req.updated_at = now
        draft.updated_at = now

        audit_event_type = VerificationAuditEventType.APPROVAL_GRANTED
        summary = ""

        if decision_enum == ApprovalDecisionType.APPROVE:
            approval_req.status = ApprovalStatus.APPROVED.value
            draft.lifecycle_status = DraftLifecycleStatus.APPROVED.value
            audit_event_type = VerificationAuditEventType.APPROVAL_GRANTED
            summary = f"Draft v{draft.version_number} approved by {decider.email}"
        elif decision_enum == ApprovalDecisionType.REJECT:
            approval_req.status = ApprovalStatus.REJECTED.value
            draft.lifecycle_status = DraftLifecycleStatus.REJECTED.value
            audit_event_type = VerificationAuditEventType.APPROVAL_REJECTED
            summary = (
                f"Draft v{draft.version_number} rejected: {decision_reason or 'No reason provided'}"
            )
        elif decision_enum == ApprovalDecisionType.REQUEST_REVISION:
            approval_req.status = ApprovalStatus.REVISION_REQUESTED.value
            draft.lifecycle_status = DraftLifecycleStatus.REVISION_REQUIRED.value
            audit_event_type = VerificationAuditEventType.REVISION_REQUESTED
            summary = f"Revision requested for draft v{draft.version_number}: {decision_reason or 'No reason provided'}"

        await session.flush()

        # Record audit event
        await VerificationAuditService.record_event(
            session=session,
            organization_id=organization_id,
            event_type=audit_event_type,
            entity_type="approval_request",
            entity_id=approval_req.id,
            actor_id=decider.id,
            request_id=request_id,
            event_summary=summary,
            metadata_json={
                "draft_id": str(draft.id),
                "draft_version": draft.version_number,
                "decision": decision_enum.value,
                "reason": decision_reason,
            },
        )

        return approval_req, draft

    @staticmethod
    async def invalidate_prior_approvals_for_draft(
        session: AsyncSession,
        organization_id: uuid.UUID,
        draft_id: uuid.UUID,
        new_version_number: int,
        actor_id: uuid.UUID | None = None,
        request_id: str | None = None,
    ) -> int:
        """Automatically invalidate previous approvals when a new draft version is committed."""
        stmt = select(ApprovalRequest).where(
            ApprovalRequest.organization_id == organization_id,
            ApprovalRequest.draft_id == draft_id,
            ApprovalRequest.draft_version < new_version_number,
            ApprovalRequest.status.in_(
                [ApprovalStatus.PENDING.value, ApprovalStatus.APPROVED.value]
            ),
        )
        res = await session.execute(stmt)
        requests_to_invalidate = list(res.scalars().all())

        now = datetime.now(UTC)
        for req in requests_to_invalidate:
            req.status = ApprovalStatus.INVALIDATED.value
            req.updated_at = now
            await VerificationAuditService.record_event(
                session=session,
                organization_id=organization_id,
                event_type=VerificationAuditEventType.APPROVAL_INVALIDATED,
                entity_type="approval_request",
                entity_id=req.id,
                actor_id=actor_id,
                request_id=request_id,
                event_summary=f"Approval request for draft v{req.draft_version} invalidated because draft was revised to v{new_version_number}",
                metadata_json={
                    "draft_id": str(draft_id),
                    "old_version": req.draft_version,
                    "new_version": new_version_number,
                },
            )

        if requests_to_invalidate:
            await session.flush()

        return len(requests_to_invalidate)
