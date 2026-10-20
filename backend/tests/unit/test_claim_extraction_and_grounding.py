"""Unit tests for claim extraction, evidence grounding, and documentary contradiction detection."""

from app.models.enums import ClaimCategory, ClaimSupportStatus, ClaimVerificationMethod
from app.services.verification.claim_extractor import ClaimExtractor
from app.services.verification.evidence_grounder import EvidenceGrounder


def test_claim_extraction_filters_fillers_and_classifies_categories():
    """Verify ClaimExtractor strips greetings and categorizes material vs general claims."""
    extractor = ClaimExtractor()
    text = (
        "Hello! Thank you for reaching out to SupportGPT Support. "
        "Our standard refund policy permits returns within 30 days of purchase. "
        "We guarantee a response time within 2 hours for all Priority 1 incidents. "
        "SupportGPT Enterprise version 2.4 supports SAML 2.0 single sign-on integration. "
        "Have a great day and please let us know if you have any questions!"
    )

    claims = extractor.extract_claims(text)

    # Conversational fillers like 'Hello!' and 'Have a great day...' must be filtered out
    assert len(claims) == 3

    c1 = claims[0]
    assert c1.category == ClaimCategory.PRICING_REFUND
    assert "refund policy" in c1.claim_text.lower()
    assert c1.is_material is True

    c2 = claims[1]
    assert c2.category == ClaimCategory.SLA_COMMITMENT
    assert "response time" in c2.claim_text.lower()
    assert c2.is_material is True

    c3 = claims[2]
    assert c3.category == ClaimCategory.PRODUCT_FACT
    assert "saml 2.0" in c3.claim_text.lower()
    assert c3.is_material is True


def test_claim_grounding_with_zero_evidence_marks_material_claims_unsupported():
    """Verify material claims without evidence sources are flagged as unsupported rather than hallucinated safe."""
    extractor = ClaimExtractor()
    grounder = EvidenceGrounder()

    text = "We provide full cash refunds within 90 days of purchase without questions asked."
    claims = extractor.extract_claims(text)
    assert len(claims) == 1

    # Empty evidence list
    results = grounder.evaluate_claims(claims, evidence_references=[])
    assert len(results) == 1

    res = results[0]
    assert res.support_status == ClaimSupportStatus.UNSUPPORTED
    assert res.confidence_score == 0.0
    assert "no evidence sources" in res.reason.lower()


def test_claim_grounding_supported_by_matching_evidence():
    """Verify that claims with high term alignment against evidence are marked supported."""
    extractor = ClaimExtractor()
    grounder = EvidenceGrounder()

    text = "Passwords must be at least 16 characters in length according to enterprise security standards."
    claims = extractor.extract_claims(text)

    evidence = [
        {
            "chunk_id": "c1111111-1111-1111-1111-111111111111",
            "excerpt": "Under the enterprise security standards, passwords must be at least 16 characters in length.",
            "source_title": "Security Guidelines",
        }
    ]

    results = grounder.evaluate_claims(claims, evidence_references=evidence)
    assert len(results) == 1

    res = results[0]
    assert res.support_status == ClaimSupportStatus.SUPPORTED
    assert res.confidence_score >= 0.80
    assert "c1111111-1111-1111-1111-111111111111" in res.evidence_chunk_ids
    assert res.verification_method == ClaimVerificationMethod.EVIDENCE_GROUNDING


def test_contradiction_detection_for_refunds():
    """Verify that a claim promising full refunds is flagged as CONTRADICTED when evidence says non-refundable."""
    extractor = ClaimExtractor()
    grounder = EvidenceGrounder()

    text = "We are happy to issue a full 100% money-back refund for your purchase immediately."
    claims = extractor.extract_claims(text)

    evidence = [
        {
            "chunk_id": "c2222222-2222-2222-2222-222222222222",
            "excerpt": "All sales are final after 14 days and digital subscription fees are non-refundable under any circumstance.",
            "source_title": "Billing Terms",
        }
    ]

    results = grounder.evaluate_claims(claims, evidence_references=evidence)
    assert len(results) == 1

    res = results[0]
    assert res.support_status == ClaimSupportStatus.CONTRADICTED
    assert res.confidence_score >= 0.90
    assert "c2222222-2222-2222-2222-222222222222" in res.evidence_chunk_ids
    assert "non-refundable" in res.reason.lower()
