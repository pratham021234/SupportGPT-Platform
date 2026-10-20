"""Evidence grounding and contradiction detection for extracted claims."""

import re
from dataclasses import dataclass
from typing import Any

from app.models.enums import ClaimCategory, ClaimSupportStatus, ClaimVerificationMethod
from app.services.verification.claim_extractor import ExtractedClaim


@dataclass
class ClaimGroundingResult:
    """Evaluated evidence grounding result for an individual claim."""

    claim_text: str
    claim_category: ClaimCategory
    support_status: ClaimSupportStatus
    evidence_chunk_ids: list[str]
    confidence_score: float
    reason: str
    verification_method: ClaimVerificationMethod


class EvidenceGrounder:
    """Verifies extracted claims against authorized evidence excerpts and detects contradictions."""

    STOPWORDS = {
        "a",
        "an",
        "the",
        "and",
        "or",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "by",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "it",
        "this",
        "that",
        "these",
        "those",
        "we",
        "you",
        "they",
        "our",
        "your",
        "their",
        "can",
        "could",
        "will",
        "would",
        "should",
        "may",
        "might",
    }

    CONTRADICTION_PATTERNS = [
        # Refunds
        (
            re.compile(
                r"\b(full|100%|instant|unconditional|money[-\s]back)\s+refund\b", re.IGNORECASE
            ),
            re.compile(
                r"\b(non[-\s]refundable|no\s+refunds?|all\s+sales\s+are\s+final)\b", re.IGNORECASE
            ),
            "Claim promises full or unconditional refunds, but evidence explicitly specifies non-refundable or final sale terms.",
        ),
        # SLAs / Response times
        (
            re.compile(r"\b(within\s+1\s+hour|instant\s+resolution|24/7\s+phone)\b", re.IGNORECASE),
            re.compile(
                r"\b(business\s+hours|4\s+business\s+hours|email\s+only|next\s+business\s+day)\b",
                re.IGNORECASE,
            ),
            "Claim commits to instant or 1-hour resolution, but evidence specifies standard business-hour SLAs.",
        ),
        # Unlimited access
        (
            re.compile(r"\b(unlimited|infinite|no\s+limits?)\b", re.IGNORECASE),
            re.compile(r"\b(rate\s+limit|capped\s+at|maximum\s+of|quota)\b", re.IGNORECASE),
            "Claim promises unlimited usage, but evidence documents strict quotas or rate limits.",
        ),
    ]

    def evaluate_claims(
        self,
        claims: list[ExtractedClaim],
        evidence_references: list[dict[str, Any]],
    ) -> list[ClaimGroundingResult]:
        """Match claims against evidence excerpts and assign grounding status."""
        results: list[ClaimGroundingResult] = []

        # If zero evidence items are available
        if not evidence_references:
            for c in claims:
                if c.is_material:
                    results.append(
                        ClaimGroundingResult(
                            claim_text=c.claim_text,
                            claim_category=c.category,
                            support_status=ClaimSupportStatus.UNSUPPORTED,
                            evidence_chunk_ids=[],
                            confidence_score=0.0,
                            reason="No evidence sources were provided or retrieved to support this material claim.",
                            verification_method=ClaimVerificationMethod.EVIDENCE_GROUNDING,
                        )
                    )
                else:
                    results.append(
                        ClaimGroundingResult(
                            claim_text=c.claim_text,
                            claim_category=c.category,
                            support_status=ClaimSupportStatus.NOT_VERIFIABLE,
                            evidence_chunk_ids=[],
                            confidence_score=0.5,
                            reason="Conversational or general claim without specific documentary evidence requirements.",
                            verification_method=ClaimVerificationMethod.EVIDENCE_GROUNDING,
                        )
                    )
            return results

        # Process claims against available evidence
        for claim in claims:
            res = self._evaluate_single_claim(claim, evidence_references)
            results.append(res)

        return results

    def _evaluate_single_claim(
        self,
        claim: ExtractedClaim,
        evidence_items: list[dict[str, Any]],
    ) -> ClaimGroundingResult:
        """Evaluate one claim across all candidate evidence excerpts."""
        claim_tokens = self._extract_content_tokens(claim.claim_text)
        if not claim_tokens:
            return ClaimGroundingResult(
                claim_text=claim.claim_text,
                claim_category=claim.category,
                support_status=ClaimSupportStatus.NOT_VERIFIABLE,
                evidence_chunk_ids=[],
                confidence_score=0.5,
                reason="Claim contains no substantive tokens to evaluate.",
                verification_method=ClaimVerificationMethod.EVIDENCE_GROUNDING,
            )

        best_score = 0.0
        best_chunk_ids: list[str] = []
        contradiction_found = False
        contradiction_reason = ""

        for ev in evidence_items:
            chunk_id = str(ev.get("chunk_id", ev.get("id", "")))
            excerpt = ev.get("excerpt", ev.get("relevant_excerpt", ev.get("content", "")))
            if not excerpt:
                continue

            # 1. Contradiction check
            for claim_pattern, ev_pattern, desc in self.CONTRADICTION_PATTERNS:
                if claim_pattern.search(claim.claim_text) and ev_pattern.search(excerpt):
                    contradiction_found = True
                    contradiction_reason = desc
                    if chunk_id:
                        best_chunk_ids.append(chunk_id)
                    break

            if contradiction_found:
                break

            # 2. Content token overlap
            ev_tokens = self._extract_content_tokens(excerpt)
            if not ev_tokens:
                continue

            overlap = claim_tokens.intersection(ev_tokens)
            score = len(overlap) / len(claim_tokens)

            if score > best_score:
                best_score = score
                if chunk_id:
                    best_chunk_ids = [chunk_id]

        if contradiction_found:
            return ClaimGroundingResult(
                claim_text=claim.claim_text,
                claim_category=claim.category,
                support_status=ClaimSupportStatus.CONTRADICTED,
                evidence_chunk_ids=best_chunk_ids,
                confidence_score=0.95,
                reason=contradiction_reason,
                verification_method=ClaimVerificationMethod.DETERMINISTIC_LEXICAL,
            )

        # Categorize score
        if best_score >= 0.40:
            return ClaimGroundingResult(
                claim_text=claim.claim_text,
                claim_category=claim.category,
                support_status=ClaimSupportStatus.SUPPORTED,
                evidence_chunk_ids=best_chunk_ids,
                confidence_score=round(best_score, 3),
                reason=f"Claim is supported by evidence excerpt with {round(best_score * 100)}% content term alignment.",
                verification_method=ClaimVerificationMethod.EVIDENCE_GROUNDING,
            )
        elif best_score >= 0.20:
            return ClaimGroundingResult(
                claim_text=claim.claim_text,
                claim_category=claim.category,
                support_status=ClaimSupportStatus.PARTIALLY_SUPPORTED,
                evidence_chunk_ids=best_chunk_ids,
                confidence_score=round(best_score, 3),
                reason="Claim is partially referenced in evidence, but some specifics lack full documentation.",
                verification_method=ClaimVerificationMethod.EVIDENCE_GROUNDING,
            )
        else:
            if claim.is_material:
                return ClaimGroundingResult(
                    claim_text=claim.claim_text,
                    claim_category=claim.category,
                    support_status=ClaimSupportStatus.UNSUPPORTED,
                    evidence_chunk_ids=[],
                    confidence_score=round(best_score, 3),
                    reason="Material claim lacks verifiable corroboration in retrieved evidence excerpts.",
                    verification_method=ClaimVerificationMethod.EVIDENCE_GROUNDING,
                )
            else:
                return ClaimGroundingResult(
                    claim_text=claim.claim_text,
                    claim_category=claim.category,
                    support_status=ClaimSupportStatus.NOT_VERIFIABLE,
                    evidence_chunk_ids=[],
                    confidence_score=round(best_score, 3),
                    reason="General assertion without explicit grounding requirements.",
                    verification_method=ClaimVerificationMethod.EVIDENCE_GROUNDING,
                )

    def _extract_content_tokens(self, text: str) -> set[str]:
        """Extract clean lowercased non-stopword alphanumeric tokens."""
        words = re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", text.lower())
        return {w for w in words if w not in self.STOPWORDS}
