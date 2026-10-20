"""Unit tests for deterministic policy evaluation and pipeline disposition calculations."""

import uuid

import pytest

from app.models.enums import (
    PolicyCategory,
    PolicyRuleType,
    PolicySeverity,
    RiskLevel,
    VerificationStatus,
)
from app.models.policy_rule import PolicyRule
from app.models.response_draft import ResponseDraft
from app.services.verification.pipeline import ResponseVerificationPipeline
from app.services.verification.policy_evaluator import PolicyEvaluator


def test_keyword_prohibition_policy():
    """Verify PolicyEvaluator catches prohibited phrases and flags violation."""
    evaluator = PolicyEvaluator()
    dummy_org = uuid.uuid4()

    rule = PolicyRule(
        id=uuid.uuid4(),
        organization_id=dummy_org,
        name="Prohibited Terms",
        description="Block free forever promises",
        policy_category=PolicyCategory.PROHIBITED_TERMS.value,
        severity=PolicySeverity.HIGH.value,
        is_enabled=True,
        rule_type=PolicyRuleType.KEYWORD_PROHIBITION.value,
        rule_config={
            "prohibited_terms": ["free forever", "unconditional refund"],
            "case_sensitive": False,
        },
    )

    draft_with_violation = (
        "You can upgrade to our Enterprise tier which is free forever for your team."
    )
    findings = evaluator.evaluate_policies(draft_with_violation, [], [rule])

    assert len(findings) == 1
    assert findings[0].passed is False
    assert findings[0].severity == PolicySeverity.HIGH
    assert "free forever" in findings[0].details

    draft_clean = "You can upgrade to our Enterprise tier with annual billing."
    findings_clean = evaluator.evaluate_policies(draft_clean, [], [rule])
    assert len(findings_clean) == 1
    assert findings_clean[0].passed is True


def test_required_phrase_policy():
    """Verify PolicyEvaluator flags drafts missing mandatory disclaimer phrases."""
    evaluator = PolicyEvaluator()
    dummy_org = uuid.uuid4()

    rule = PolicyRule(
        id=uuid.uuid4(),
        organization_id=dummy_org,
        name="Mandatory Disclaimer",
        description="Must include terms disclaimer",
        policy_category=PolicyCategory.MANDATORY_DISCLAIMERS.value,
        severity=PolicySeverity.MEDIUM.value,
        is_enabled=True,
        rule_type=PolicyRuleType.REQUIRED_PHRASE.value,
        rule_config={"required_phrases": ["Terms and conditions apply"]},
    )

    draft_missing = "Your account discount has been applied to the current billing period."
    findings = evaluator.evaluate_policies(draft_missing, [], [rule])
    assert len(findings) == 1
    assert findings[0].passed is False
    assert "Terms and conditions apply" in findings[0].details

    draft_compliant = "Your account discount has been applied. Terms and conditions apply."
    findings_compliant = evaluator.evaluate_policies(draft_compliant, [], [rule])
    assert len(findings_compliant) == 1
    assert findings_compliant[0].passed is True


@pytest.mark.asyncio
async def test_pipeline_disposition_blocked_on_contradiction():
    """Verify pipeline returns BLOCKED with CRITICAL risk when claims contradict documentation."""
    pipeline = ResponseVerificationPipeline()
    dummy_org = uuid.uuid4()

    draft = ResponseDraft(
        id=uuid.uuid4(),
        organization_id=dummy_org,
        original_query="Can I get a full refund?",
        draft_text="We offer a full 100% money-back refund for all services.",
        version_number=1,
        evidence_references=[
            {
                "chunk_id": str(uuid.uuid4()),
                "excerpt": "All sales are final and software licenses are non-refundable.",
                "source_title": "Billing Terms",
            }
        ],
    )

    result = await pipeline.verify_draft(draft, policies=[])
    assert result.status == VerificationStatus.BLOCKED
    assert result.risk_level == RiskLevel.CRITICAL
    assert result.requires_human_approval is True
    assert result.machine_readable_findings["contradicted_claims"] >= 1


@pytest.mark.asyncio
async def test_pipeline_disposition_needs_revision_on_unsupported_claim():
    """Verify pipeline returns NEEDS_REVISION with HIGH risk when claims lack evidence grounding."""
    pipeline = ResponseVerificationPipeline()
    dummy_org = uuid.uuid4()

    draft = ResponseDraft(
        id=uuid.uuid4(),
        organization_id=dummy_org,
        original_query="What is your uptime guarantee?",
        draft_text="Our platform guarantees 99.999% uptime with immediate failover across five regions.",
        version_number=1,
        evidence_references=[],  # Zero evidence supplied
    )

    result = await pipeline.verify_draft(draft, policies=[])
    assert result.status == VerificationStatus.NEEDS_REVISION
    assert result.risk_level == RiskLevel.HIGH
    assert result.requires_human_approval is True
    assert result.machine_readable_findings["unsupported_claims"] >= 1


@pytest.mark.asyncio
async def test_pipeline_disposition_passed_on_grounded_response():
    """Verify pipeline returns PASSED with LOW risk when all claims are verified by evidence."""
    pipeline = ResponseVerificationPipeline()
    dummy_org = uuid.uuid4()

    draft = ResponseDraft(
        id=uuid.uuid4(),
        organization_id=dummy_org,
        original_query="What is the password requirement?",
        draft_text="Passwords must be at least 16 characters in length according to security standards.",
        version_number=1,
        evidence_references=[
            {
                "chunk_id": str(uuid.uuid4()),
                "excerpt": "According to enterprise security standards, passwords must be at least 16 characters in length.",
                "source_title": "Security Handbook",
            }
        ],
    )

    result = await pipeline.verify_draft(draft, policies=[])
    assert result.status == VerificationStatus.PASSED
    assert result.risk_level == RiskLevel.LOW
    assert result.requires_human_approval is False
    assert result.machine_readable_findings["unsupported_claims"] == 0
