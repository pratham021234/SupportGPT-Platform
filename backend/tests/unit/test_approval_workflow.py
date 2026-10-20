"""Unit tests for approval workflow, separation-of-duties, and draft version invalidation."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import (
    SelfApprovalForbiddenException,
    StaleDraftApprovalException,
)
from app.models.approval_request import ApprovalRequest
from app.models.enums import (
    ApprovalDecisionType,
    ApprovalStatus,
    DraftLifecycleStatus,
)
from app.models.response_draft import ResponseDraft
from app.models.user import User
from app.services.verification.approval_service import ApprovalService


@pytest.mark.asyncio
async def test_self_approval_forbidden_under_separation_of_duties():
    """Verify that a user who requested approval cannot approve their own draft."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    run_id = uuid.uuid4()
    approval_id = uuid.uuid4()

    user = User(id=user_id, email="agent@company.com", display_name="Agent", status="active")
    draft = ResponseDraft(
        id=draft_id,
        organization_id=org_id,
        original_query="Test query",
        draft_text="Draft text",
        version_number=1,
        lifecycle_status=DraftLifecycleStatus.APPROVAL_PENDING.value,
    )
    req = ApprovalRequest(
        id=approval_id,
        organization_id=org_id,
        draft_id=draft_id,
        draft_version=1,
        verification_run_id=run_id,
        status=ApprovalStatus.PENDING.value,
        separation_of_duties=True,
        requested_by_user_id=user_id,  # Requester is user_id
    )

    mock_session = AsyncMock()
    # Mock finding req and draft
    mock_session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=req)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=draft)),
        ]
    )

    with pytest.raises(SelfApprovalForbiddenException):
        await ApprovalService.decide_approval(
            session=mock_session,
            organization_id=org_id,
            approval_id=approval_id,
            decider=user,  # Decider is also user_id
            decision=ApprovalDecisionType.APPROVE,
            decision_reason="Approving my own response",
        )


@pytest.mark.asyncio
async def test_independent_approver_can_approve_draft():
    """Verify an independent team member can approve a draft."""
    org_id = uuid.uuid4()
    requester_id = uuid.uuid4()
    approver_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    approval_id = uuid.uuid4()

    approver = User(
        id=approver_id, email="reviewer@company.com", display_name="Reviewer", status="active"
    )
    draft = ResponseDraft(
        id=draft_id,
        organization_id=org_id,
        original_query="Test query",
        draft_text="Draft text",
        version_number=1,
        lifecycle_status=DraftLifecycleStatus.APPROVAL_PENDING.value,
    )
    req = ApprovalRequest(
        id=approval_id,
        organization_id=org_id,
        draft_id=draft_id,
        draft_version=1,
        verification_run_id=uuid.uuid4(),
        status=ApprovalStatus.PENDING.value,
        separation_of_duties=True,
        requested_by_user_id=requester_id,  # Requester is someone else
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=req)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=draft)),
        ]
    )

    decided_req, decided_draft = await ApprovalService.decide_approval(
        session=mock_session,
        organization_id=org_id,
        approval_id=approval_id,
        decider=approver,
        decision=ApprovalDecisionType.APPROVE,
        decision_reason="Looks accurate and grounded in policy.",
    )

    assert decided_req.status == ApprovalStatus.APPROVED.value
    assert decided_draft.lifecycle_status == DraftLifecycleStatus.APPROVED.value
    assert decided_req.decision_by_user_id == approver_id


@pytest.mark.asyncio
async def test_stale_draft_approval_rejected_on_version_mismatch():
    """Verify that attempting to approve a stale draft version raises StaleDraftApprovalException."""
    org_id = uuid.uuid4()
    approver_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    approval_id = uuid.uuid4()

    approver = User(
        id=approver_id, email="reviewer@company.com", display_name="Reviewer", status="active"
    )
    # Draft is now version 2
    draft = ResponseDraft(
        id=draft_id,
        organization_id=org_id,
        original_query="Test query",
        draft_text="Revised draft text",
        version_number=2,
        lifecycle_status=DraftLifecycleStatus.DRAFT.value,
    )
    # But approval was requested for version 1
    req = ApprovalRequest(
        id=approval_id,
        organization_id=org_id,
        draft_id=draft_id,
        draft_version=1,
        verification_run_id=uuid.uuid4(),
        status=ApprovalStatus.PENDING.value,
        separation_of_duties=False,
    )

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=req)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=draft)),
        ]
    )

    with pytest.raises(StaleDraftApprovalException):
        await ApprovalService.decide_approval(
            session=mock_session,
            organization_id=org_id,
            approval_id=approval_id,
            decider=approver,
            decision=ApprovalDecisionType.APPROVE,
        )
