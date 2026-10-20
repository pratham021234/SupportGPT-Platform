"""Integration tests running Response Verification and Human Approvals against live PostgreSQL 16."""

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.approval_request import ApprovalRequest
from app.models.claim_finding import ClaimFinding
from app.models.enums import (
    ApprovalDecisionType,
    ApprovalStatus,
    DraftLifecycleStatus,
    OrganizationStatus,
    PolicyCategory,
    PolicyRuleType,
    PolicySeverity,
    UserStatus,
    VerificationStatus,
)
from app.models.organization import Organization
from app.models.policy_rule import PolicyRule
from app.models.response_draft import ResponseDraft
from app.models.user import User
from app.models.verification_audit_event import VerificationAuditEvent
from app.models.verification_run import VerificationRun
from app.services.verification.approval_service import ApprovalService
from app.services.verification.audit_service import VerificationAuditService
from app.services.verification.pipeline import ResponseVerificationPipeline

POSTGRES_TEST_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://supportgpt_user:supportgpt_dev_password@localhost:5432/supportgpt_test_db",
)


@pytest.fixture
async def live_postgres_verification_env():
    """Fixture providing a live PostgreSQL connection and clean test organization."""
    engine = create_async_engine(POSTGRES_TEST_URL, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Live PostgreSQL not reachable at {POSTGRES_TEST_URL}: {exc}")

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    org_id = uuid.uuid4()
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    async with session_factory() as session:
        # Enable admin bypass to seed test organization and users
        await session.execute(text("SELECT set_config('app.is_system_admin', 'true', false)"))
        org = Organization(
            id=org_id,
            name="Live Verification Org",
            slug=f"live-verif-{org_id.hex[:8]}",
            status=OrganizationStatus.ACTIVE.value,
        )
        user_a = User(
            id=user_a_id,
            email=f"author-{org_id.hex[:6]}@example.com",
            password_hash="test_hashed_password_12345678",
            display_name="Draft Author",
            status=UserStatus.ACTIVE.value,
        )
        user_b = User(
            id=user_b_id,
            email=f"reviewer-{org_id.hex[:6]}@example.com",
            password_hash="test_hashed_password_12345678",
            display_name="Draft Reviewer",
            status=UserStatus.ACTIVE.value,
        )
        session.add_all([org, user_a, user_b])
        await session.commit()

    yield session_factory, org_id, user_a, user_b

    # Teardown
    async with session_factory() as session:
        await session.execute(text("SELECT set_config('app.is_system_admin', 'true', false)"))
        await session.execute(
            delete(VerificationAuditEvent).where(VerificationAuditEvent.organization_id == org_id)
        )
        await session.execute(
            delete(ApprovalRequest).where(ApprovalRequest.organization_id == org_id)
        )
        await session.execute(delete(ClaimFinding).where(ClaimFinding.organization_id == org_id))
        await session.execute(
            delete(VerificationRun).where(VerificationRun.organization_id == org_id)
        )
        await session.execute(delete(ResponseDraft).where(ResponseDraft.organization_id == org_id))
        await session.execute(delete(PolicyRule).where(PolicyRule.organization_id == org_id))
        await session.execute(delete(User).where(User.id.in_([user_a_id, user_b_id])))
        await session.execute(delete(Organization).where(Organization.id == org_id))
        await session.commit()

    await engine.dispose()


@pytest.mark.asyncio
async def test_live_postgres_verification_and_approval_pipeline(live_postgres_verification_env):
    """Run full verification, claim persisting, approval workflow, and audit trail on live PostgreSQL 16."""
    session_factory, org_id, user_author, user_reviewer = live_postgres_verification_env

    async with session_factory() as session:
        # Set tenant session variable to enforce active PostgreSQL RLS
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, false)"),
            {"org_id": str(org_id)},
        )

        now = datetime.now(UTC)
        # 1. Create Policy Rule in PostgreSQL
        policy = PolicyRule(
            organization_id=org_id,
            name="Live SLA Guard",
            description="Restricts response promises",
            policy_category=PolicyCategory.RESTRICTED_COMMITMENTS.value,
            severity=PolicySeverity.HIGH.value,
            is_enabled=True,
            rule_type=PolicyRuleType.KEYWORD_PROHIBITION.value,
            rule_config={"prohibited_terms": ["free forever"], "case_sensitive": False},
            created_at=now,
            updated_at=now,
        )
        session.add(policy)

        # 2. Create Response Draft in PostgreSQL
        draft = ResponseDraft(
            organization_id=org_id,
            original_query="What is the standard SLA for Priority 1?",
            draft_text="Our standard SLA guarantees a response within 2 hours for Priority 1 issues.",
            version_number=1,
            lifecycle_status=DraftLifecycleStatus.DRAFT.value,
            evidence_references=[
                {
                    "chunk_id": str(uuid.uuid4()),
                    "excerpt": "For Priority 1 Critical issues, the initial response time is guaranteed within 2 hours.",
                    "source_title": "Enterprise SLA Document",
                }
            ],
            created_by_user_id=user_author.id,
            created_at=now,
            updated_at=now,
        )
        session.add(draft)
        await session.commit()

    # 3. Execute Pipeline
    pipeline = ResponseVerificationPipeline()
    result = await pipeline.verify_draft(draft, [policy])
    assert result.status == VerificationStatus.PASSED
    assert len(result.claim_results) >= 1

    # 4. Persist VerificationRun and ClaimFindings to PostgreSQL
    async with session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, false)"),
            {"org_id": str(org_id)},
        )

        now = datetime.now(UTC)
        run = VerificationRun(
            organization_id=org_id,
            draft_id=draft.id,
            draft_version=draft.version_number,
            verification_pipeline_version="v1.0.0",
            policy_set_version=1,
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
        )
        session.add(run)
        await session.flush()

        for c in result.claim_results:
            cf = ClaimFinding(
                organization_id=org_id,
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
            session.add(cf)

        await session.commit()

    # 5. Create Approval Request and Decide on PostgreSQL
    async with session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, false)"),
            {"org_id": str(org_id)},
        )

        appr_req = await ApprovalService.create_approval_request(
            session=session,
            organization_id=org_id,
            draft_id=draft.id,
            draft_version=1,
            verification_run_id=run.id,
            requested_by_user_id=user_author.id,
            separation_of_duties=True,
        )
        await session.commit()

        # Decide approval with independent reviewer
        decided_req, decided_draft = await ApprovalService.decide_approval(
            session=session,
            organization_id=org_id,
            approval_id=appr_req.id,
            decider=user_reviewer,
            decision=ApprovalDecisionType.APPROVE,
            decision_reason="Verified on live PostgreSQL.",
        )
        await session.commit()

        assert decided_req.status == ApprovalStatus.APPROVED.value
        assert decided_draft.lifecycle_status == DraftLifecycleStatus.APPROVED.value

    # 6. Verify Audit Trail in PostgreSQL
    async with session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, false)"),
            {"org_id": str(org_id)},
        )
        events = await VerificationAuditService.list_audit_events(
            session=session,
            organization_id=org_id,
        )
        assert len(events) >= 2
        event_types = [e.event_type for e in events]
        assert "approval_requested" in event_types
        assert "approval_granted" in event_types
