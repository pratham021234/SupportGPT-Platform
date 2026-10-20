"""Deterministic and declarative policy evaluation engine."""

import re
from dataclasses import dataclass

from app.models.enums import (
    ClaimSupportStatus,
    PolicyCategory,
    PolicyRuleType,
    PolicySeverity,
)
from app.models.policy_rule import PolicyRule
from app.services.verification.evidence_grounder import ClaimGroundingResult


@dataclass
class PolicyEvaluationFinding:
    """Outcome of evaluating a single policy rule against a response draft."""

    policy_id: str | None
    rule_name: str
    policy_category: PolicyCategory
    rule_type: PolicyRuleType
    severity: PolicySeverity
    passed: bool
    requires_approval: bool
    details: str


class PolicyEvaluator:
    """Evaluates organization compliance policies and deterministic guardrails."""

    def evaluate_policies(
        self,
        draft_text: str,
        claim_results: list[ClaimGroundingResult],
        policies: list[PolicyRule],
    ) -> list[PolicyEvaluationFinding]:
        """Evaluate all active policies against draft text and claim findings."""
        findings: list[PolicyEvaluationFinding] = []

        # If no explicit organization policies are supplied, apply default baseline guardrails
        rules_to_eval = [p for p in policies if p.is_enabled]
        if not rules_to_eval:
            rules_to_eval = self._get_default_baseline_policies()

        for policy in rules_to_eval:
            finding = self._evaluate_rule(policy, draft_text, claim_results)
            findings.append(finding)

        return findings

    def _evaluate_rule(
        self,
        policy: PolicyRule,
        draft_text: str,
        claim_results: list[ClaimGroundingResult],
    ) -> PolicyEvaluationFinding:
        """Evaluate a single policy rule based on its rule_type."""
        rule_type = policy.rule_type
        config = policy.rule_config or {}

        if rule_type == PolicyRuleType.UNSUPPORTED_CLAIM_BLOCK.value:
            # Check for contradicted or unsupported claims
            contradicted = [
                c for c in claim_results if c.support_status == ClaimSupportStatus.CONTRADICTED
            ]
            unsupported = [
                c for c in claim_results if c.support_status == ClaimSupportStatus.UNSUPPORTED
            ]

            if contradicted:
                return PolicyEvaluationFinding(
                    policy_id=str(policy.id) if policy.id else None,
                    rule_name=policy.name,
                    policy_category=PolicyCategory(policy.policy_category),
                    rule_type=PolicyRuleType.UNSUPPORTED_CLAIM_BLOCK,
                    severity=PolicySeverity.CRITICAL,
                    passed=False,
                    requires_approval=True,
                    details=f"Draft makes {len(contradicted)} assertion(s) directly contradicted by evidence: '{contradicted[0].claim_text[:80]}...'",
                )

            if unsupported:
                return PolicyEvaluationFinding(
                    policy_id=str(policy.id) if policy.id else None,
                    rule_name=policy.name,
                    policy_category=PolicyCategory(policy.policy_category),
                    rule_type=PolicyRuleType.UNSUPPORTED_CLAIM_BLOCK,
                    severity=PolicySeverity.HIGH,
                    passed=False,
                    requires_approval=True,
                    details=f"Draft makes {len(unsupported)} material factual claim(s) lacking evidence support: '{unsupported[0].claim_text[:80]}...'",
                )

            return PolicyEvaluationFinding(
                policy_id=str(policy.id) if policy.id else None,
                rule_name=policy.name,
                policy_category=PolicyCategory(policy.policy_category),
                rule_type=PolicyRuleType.UNSUPPORTED_CLAIM_BLOCK,
                severity=PolicySeverity(policy.severity),
                passed=True,
                requires_approval=False,
                details="All material claims are grounded or non-assertive.",
            )

        elif rule_type == PolicyRuleType.KEYWORD_PROHIBITION.value:
            prohibited_terms = config.get("prohibited_terms", [])
            case_sensitive = config.get("case_sensitive", False)

            search_text = draft_text if case_sensitive else draft_text.lower()
            violating_terms = []

            for term in prohibited_terms:
                term_clean = term if case_sensitive else term.lower()
                pattern = r"\b" + re.escape(term_clean) + r"\b"
                if re.search(pattern, search_text):
                    violating_terms.append(term)

            if violating_terms:
                return PolicyEvaluationFinding(
                    policy_id=str(policy.id) if policy.id else None,
                    rule_name=policy.name,
                    policy_category=PolicyCategory(policy.policy_category),
                    rule_type=PolicyRuleType.KEYWORD_PROHIBITION,
                    severity=PolicySeverity(policy.severity),
                    passed=False,
                    requires_approval=True,
                    details=f"Draft contains prohibited term(s): {', '.join(violating_terms)}",
                )

            return PolicyEvaluationFinding(
                policy_id=str(policy.id) if policy.id else None,
                rule_name=policy.name,
                policy_category=PolicyCategory(policy.policy_category),
                rule_type=PolicyRuleType.KEYWORD_PROHIBITION,
                severity=PolicySeverity(policy.severity),
                passed=True,
                requires_approval=False,
                details="Zero prohibited terms detected.",
            )

        elif rule_type == PolicyRuleType.REQUIRED_PHRASE.value:
            required_phrases = config.get("required_phrases", [])
            missing_phrases = []

            for phrase in required_phrases:
                if phrase.lower() not in draft_text.lower():
                    missing_phrases.append(phrase)

            if missing_phrases:
                return PolicyEvaluationFinding(
                    policy_id=str(policy.id) if policy.id else None,
                    rule_name=policy.name,
                    policy_category=PolicyCategory(policy.policy_category),
                    rule_type=PolicyRuleType.REQUIRED_PHRASE,
                    severity=PolicySeverity(policy.severity),
                    passed=False,
                    requires_approval=False,
                    details=f"Draft is missing mandatory disclaimer/phrase(s): {', '.join(missing_phrases)}",
                )

            return PolicyEvaluationFinding(
                policy_id=str(policy.id) if policy.id else None,
                rule_name=policy.name,
                policy_category=PolicyCategory(policy.policy_category),
                rule_type=PolicyRuleType.REQUIRED_PHRASE,
                severity=PolicySeverity(policy.severity),
                passed=True,
                requires_approval=False,
                details="All mandatory phrases and disclaimers are present.",
            )

        elif rule_type == PolicyRuleType.MAX_LENGTH.value:
            max_chars = config.get("max_chars", 2500)
            if len(draft_text) > max_chars:
                return PolicyEvaluationFinding(
                    policy_id=str(policy.id) if policy.id else None,
                    rule_name=policy.name,
                    policy_category=PolicyCategory(policy.policy_category),
                    rule_type=PolicyRuleType.MAX_LENGTH,
                    severity=PolicySeverity(policy.severity),
                    passed=False,
                    requires_approval=False,
                    details=f"Draft character length ({len(draft_text)}) exceeds maximum permitted ceiling ({max_chars}).",
                )

            return PolicyEvaluationFinding(
                policy_id=str(policy.id) if policy.id else None,
                rule_name=policy.name,
                policy_category=PolicyCategory(policy.policy_category),
                rule_type=PolicyRuleType.MAX_LENGTH,
                severity=PolicySeverity(policy.severity),
                passed=True,
                requires_approval=False,
                details=f"Draft length is compliant ({len(draft_text)} <= {max_chars} chars).",
            )

        elif rule_type == PolicyRuleType.REFUND_LIMIT.value:
            max_authorized = float(config.get("max_authorized_amount", 50.0))
            # Scan for monetary refund values: e.g. $100, $ 100, 100 dollars
            amounts = re.findall(r"\$\s*([0-9]+(?:\.[0-9]{2})?)", draft_text)
            amounts += re.findall(
                r"\b([0-9]+(?:\.[0-9]{2})?)\s*(?:dollars|usd)\b", draft_text, re.IGNORECASE
            )

            exceeded_amounts = [float(a) for a in amounts if float(a) > max_authorized]
            if exceeded_amounts:
                return PolicyEvaluationFinding(
                    policy_id=str(policy.id) if policy.id else None,
                    rule_name=policy.name,
                    policy_category=PolicyCategory(policy.policy_category),
                    rule_type=PolicyRuleType.REFUND_LIMIT,
                    severity=PolicySeverity.HIGH,
                    passed=False,
                    requires_approval=True,
                    details=f"Draft proposes monetary refund/credit (${max(exceeded_amounts)}) exceeding automated limit (${max_authorized}).",
                )

            return PolicyEvaluationFinding(
                policy_id=str(policy.id) if policy.id else None,
                rule_name=policy.name,
                policy_category=PolicyCategory(policy.policy_category),
                rule_type=PolicyRuleType.REFUND_LIMIT,
                severity=PolicySeverity(policy.severity),
                passed=True,
                requires_approval=False,
                details=f"All monetary amounts are within authorized threshold (${max_authorized}).",
            )

        # Fallback for unrecognized rule type
        return PolicyEvaluationFinding(
            policy_id=str(policy.id) if policy.id else None,
            rule_name=policy.name,
            policy_category=PolicyCategory.GENERAL,
            rule_type=PolicyRuleType.UNSUPPORTED_CLAIM_BLOCK,
            severity=PolicySeverity.LOW,
            passed=True,
            requires_approval=False,
            details=f"Rule type '{rule_type}' evaluated without findings.",
        )

    def _get_default_baseline_policies(self) -> list[PolicyRule]:
        """Generate default deterministic baseline policies when organization has not configured custom rules."""
        import uuid

        dummy_org_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

        return [
            PolicyRule(
                id=uuid.uuid4(),
                organization_id=dummy_org_id,
                name="Strict Factual Grounding Guard",
                description="Blocks responses with contradicted claims and flags unsupported assertions.",
                policy_category=PolicyCategory.FACTUAL_GROUNDING.value,
                severity=PolicySeverity.HIGH.value,
                is_enabled=True,
                rule_type=PolicyRuleType.UNSUPPORTED_CLAIM_BLOCK.value,
                rule_config={},
            ),
            PolicyRule(
                id=uuid.uuid4(),
                organization_id=dummy_org_id,
                name="Prohibited Commitments & Guarantees",
                description="Detects unauthorized commercial commitments such as free forever promises.",
                policy_category=PolicyCategory.RESTRICTED_COMMITMENTS.value,
                severity=PolicySeverity.HIGH.value,
                is_enabled=True,
                rule_type=PolicyRuleType.KEYWORD_PROHIBITION.value,
                rule_config={
                    "prohibited_terms": [
                        "free forever",
                        "unconditional refund",
                        "100% guaranteed",
                        "unlimited free credits",
                        "waive all fees",
                    ],
                    "case_sensitive": False,
                },
            ),
            PolicyRule(
                id=uuid.uuid4(),
                organization_id=dummy_org_id,
                name="Maximum Response Length Bounds",
                description="Restricts bloated responses exceeding 3,000 characters.",
                policy_category=PolicyCategory.FACTUAL_GROUNDING.value,
                severity=PolicySeverity.LOW.value,
                is_enabled=True,
                rule_type=PolicyRuleType.MAX_LENGTH.value,
                rule_config={"max_chars": 3000},
            ),
        ]
