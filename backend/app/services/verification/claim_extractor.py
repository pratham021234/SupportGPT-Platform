"""Structured claim extraction from response draft text."""

import re
from dataclasses import dataclass

from app.models.enums import ClaimCategory


@dataclass
class ExtractedClaim:
    """An atomic claim decomposed from response draft text."""

    claim_text: str
    category: ClaimCategory
    is_material: bool


class ClaimExtractor:
    """Decomposes response draft text into verifiable atomic assertions."""

    CONVERSATIONAL_FILLERS = {
        "hello",
        "hi",
        "hey",
        "greetings",
        "thank you for reaching out",
        "thanks for contacting us",
        "thanks for your patience",
        "i hope this helps",
        "have a great day",
        "best regards",
        "sincerely",
        "please let me know if you have any questions",
        "let us know if you need further assistance",
        "we are happy to help",
    }

    POLICY_KEYWORDS = {
        "policy",
        "terms",
        "condition",
        "eligible",
        "eligibility",
        "allowed",
        "prohibited",
        "forbidden",
        "required",
        "mandatory",
        "guideline",
    }

    REFUND_KEYWORDS = {
        "refund",
        "refunds",
        "reimburse",
        "credit",
        "dollar",
        "$",
        "charge",
        "fee",
        "cost",
        "price",
        "billing",
        "payment",
    }

    SLA_KEYWORDS = {
        "sla",
        "guarantee",
        "guaranteed",
        "commit",
        "commitment",
        "turnaround",
        "response time",
        "resolution time",
        "uptime",
        "hours",
        "minutes",
        "business days",
    }

    PRODUCT_KEYWORDS = {
        "feature",
        "support",
        "supports",
        "compatible",
        "configure",
        "install",
        "version",
        "api",
        "endpoint",
        "setting",
        "dashboard",
        "integration",
    }

    def extract_claims(self, text: str) -> list[ExtractedClaim]:
        """Extract atomic material and general claims from response text."""
        if not text or not text.strip():
            return []

        # Split text by sentence terminators (.!? and newlines)
        raw_sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
        claims: list[ExtractedClaim] = []

        for raw_s in raw_sentences:
            s = raw_s.strip()
            # Clean citation tags [citation:N] or [N] for cleaner claim evaluation
            s_clean = re.sub(r"\[citation:\d+\]", "", s).strip()
            s_clean = re.sub(r"\[\d+\]", "", s_clean).strip()

            if not s_clean or len(s_clean) < 8:
                continue

            # Check if this sentence is purely a greeting or conversational pleasantry
            lower_s = s_clean.lower().strip(",.!? ")
            if any(
                lower_s.startswith(filler) or lower_s == filler
                for filler in self.CONVERSATIONAL_FILLERS
            ):
                continue

            # Classify claim category
            category = self._classify_category(lower_s)
            is_material = category in {
                ClaimCategory.POLICY,
                ClaimCategory.PRICING_REFUND,
                ClaimCategory.SLA_COMMITMENT,
                ClaimCategory.PRODUCT_FACT,
            }

            claims.append(
                ExtractedClaim(
                    claim_text=s_clean,
                    category=category,
                    is_material=is_material,
                )
            )

        return claims

    def _classify_category(self, lower_text: str) -> ClaimCategory:
        """Categorize an assertion based on semantic indicator tokens."""
        if any(kw in lower_text for kw in self.REFUND_KEYWORDS):
            return ClaimCategory.PRICING_REFUND
        if any(kw in lower_text for kw in self.SLA_KEYWORDS):
            return ClaimCategory.SLA_COMMITMENT
        if any(kw in lower_text for kw in self.POLICY_KEYWORDS):
            return ClaimCategory.POLICY
        if any(kw in lower_text for kw in self.PRODUCT_KEYWORDS):
            return ClaimCategory.PRODUCT_FACT
        return ClaimCategory.GENERAL
