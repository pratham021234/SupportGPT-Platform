"""Response verification pipeline orchestrating claim extraction, evidence grounding, and policy evaluation."""

import time
from dataclasses import dataclass
from typing import Any

from app.models.enums import (
    ClaimSupportStatus,
    PolicySeverity,
    RiskLevel,
    VerificationStatus,
)
from app.models.policy_rule import PolicyRule
from app.models.response_draft import ResponseDraft
from app.services.verification.claim_extractor import ClaimExtractor
from app.services.verification.evidence_grounder import ClaimGroundingResult, EvidenceGrounder
from app.services.verification.policy_evaluator import PolicyEvaluationFinding, PolicyEvaluator


@dataclass
class VerificationResult:
    """Consolidated outcome of the verification pipeline execution."""

    status: VerificationStatus
    risk_level: RiskLevel
    requires_human_approval: bool
    claim_results: list[ClaimGroundingResult]
    policy_findings: list[PolicyEvaluationFinding]
    machine_readable_findings: dict[str, Any]
    execution_time_ms: int
    error_message: str | None = None


class ResponseVerificationPipeline:
    """Orchestrates end-to-end verification of customer support response drafts."""

    def __init__(
        self,
        claim_extractor: ClaimExtractor | None = None,
        evidence_grounder: EvidenceGrounder | None = None,
        policy_evaluator: PolicyEvaluator | None = None,
    ) -> None:
        self.claim_extractor = claim_extractor or ClaimExtractor()
        self.evidence_grounder = evidence_grounder or EvidenceGrounder()
        self.policy_evaluator = policy_evaluator or PolicyEvaluator()

    async def verify_draft(
        self,
        draft: ResponseDraft,
        policies: list[PolicyRule],
    ) -> VerificationResult:
        """Run complete verification pipeline on a ResponseDraft instance."""
        start_time = time.perf_counter()

        # Step 1: Claim extraction
        extracted_claims = self.claim_extractor.extract_claims(draft.draft_text)

        # Step 2: Evidence grounding
        evidence_refs = draft.evidence_references or []
        claim_results = self.evidence_grounder.evaluate_claims(
            extracted_claims,
            evidence_refs,
        )

        # Step 3: Policy evaluation
        policy_findings = self.policy_evaluator.evaluate_policies(
            draft_text=draft.draft_text,
            claim_results=claim_results,
            policies=policies,
        )

        # Step 4: Compute disposition and risk level
        status, risk_level, requires_approval = self._compute_disposition(
            claim_results,
            policy_findings,
        )

        # Step 5: Format machine-readable summary
        failed_policy_rules = [f.rule_name for f in policy_findings if not f.passed]
        contradicted_claims = [
            c.claim_text
            for c in claim_results
            if c.support_status == ClaimSupportStatus.CONTRADICTED
        ]
        unsupported_claims = [
            c.claim_text
            for c in claim_results
            if c.support_status == ClaimSupportStatus.UNSUPPORTED
        ]

        machine_findings = {
            "total_claims": len(claim_results),
            "supported_claims": len(
                [c for c in claim_results if c.support_status == ClaimSupportStatus.SUPPORTED]
            ),
            "partially_supported": len(
                [
                    c
                    for c in claim_results
                    if c.support_status == ClaimSupportStatus.PARTIALLY_SUPPORTED
                ]
            ),
            "unsupported_claims": len(unsupported_claims),
            "contradicted_claims": len(contradicted_claims),
            "total_policies_evaluated": len(policy_findings),
            "failed_policies": failed_policy_rules,
            "disposition_summary": self._generate_summary(
                status, risk_level, failed_policy_rules, contradicted_claims, unsupported_claims
            ),
        }

        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        return VerificationResult(
            status=status,
            risk_level=risk_level,
            requires_human_approval=requires_approval,
            claim_results=claim_results,
            policy_findings=policy_findings,
            machine_readable_findings=machine_findings,
            execution_time_ms=execution_time_ms,
        )

    def _compute_disposition(
        self,
        claim_results: list[ClaimGroundingResult],
        policy_findings: list[PolicyEvaluationFinding],
    ) -> tuple[VerificationStatus, RiskLevel, bool]:
        """Deterministic calculation of disposition outcome and risk tier."""
        has_critical_policy_failure = any(
            not f.passed and f.severity == PolicySeverity.CRITICAL for f in policy_findings
        )
        has_contradicted_claims = any(
            c.support_status == ClaimSupportStatus.CONTRADICTED for c in claim_results
        )

        if has_critical_policy_failure or has_contradicted_claims:
            return VerificationStatus.BLOCKED, RiskLevel.CRITICAL, True

        has_high_policy_failure = any(
            not f.passed and f.severity == PolicySeverity.HIGH for f in policy_findings
        )
        has_unsupported_material_claims = any(
            c.support_status == ClaimSupportStatus.UNSUPPORTED for c in claim_results
        )

        if has_high_policy_failure or has_unsupported_material_claims:
            return VerificationStatus.NEEDS_REVISION, RiskLevel.HIGH, True

        has_medium_policy_failure = any(
            not f.passed and f.severity == PolicySeverity.MEDIUM for f in policy_findings
        )
        has_partially_supported = any(
            c.support_status == ClaimSupportStatus.PARTIALLY_SUPPORTED for c in claim_results
        )

        if has_medium_policy_failure or has_partially_supported:
            requires_appr = any(f.requires_approval for f in policy_findings)
            return VerificationStatus.PASSED_WITH_WARNINGS, RiskLevel.MEDIUM, requires_appr

        # Fully passed
        requires_appr = any(f.requires_approval for f in policy_findings)
        return VerificationStatus.PASSED, RiskLevel.LOW, requires_appr

    def _generate_summary(
        self,
        status: VerificationStatus,
        risk_level: RiskLevel,
        failed_policies: list[str],
        contradicted: list[str],
        unsupported: list[str],
    ) -> str:
        """Construct human-readable diagnostic sentence for audit and review."""
        if status == VerificationStatus.BLOCKED:
            return f"BLOCKED: Critical policy failure ({', '.join(failed_policies)}) or direct documentary contradiction detected."
        elif status == VerificationStatus.NEEDS_REVISION:
            return f"NEEDS REVISION: High risk findings ({len(unsupported)} unsupported assertions, {len(failed_policies)} policy failures). Revision required prior to delivery."
        elif status == VerificationStatus.PASSED_WITH_WARNINGS:
            return f"PASSED WITH WARNINGS: Moderate risk ({', '.join(failed_policies) if failed_policies else 'partial evidence alignment'})."
        return "PASSED: All extracted claims corroborated by authorized evidence; zero policy violations."
