"""Unit tests for webhook cryptography, signature verification, and replay guards."""

import hashlib
import hmac
import time

import pytest

from app.core.errors import (
    EventReplayWindowException,
    InvalidContentTypeException,
    PayloadSizeLimitException,
    SignatureVerificationException,
)
from app.services.secret_resolver import SecretResolver
from app.services.webhook_verifier import WebhookVerifier


def test_secret_generation_and_hashing():
    """Verify generated secrets have high entropy, proper prefix, and deterministic hashing."""
    secret_1 = SecretResolver.generate_secret()
    secret_2 = SecretResolver.generate_secret()

    assert secret_1.startswith("whsec_")
    assert secret_2.startswith("whsec_")
    assert secret_1 != secret_2
    assert len(secret_1) >= 40

    hash_1 = SecretResolver.hash_secret(secret_1)
    hash_1_again = SecretResolver.hash_secret(secret_1)
    assert hash_1 == hash_1_again
    assert len(hash_1) == 64


def test_secret_preview_masking():
    """Ensure secret previews redact raw secret material."""
    raw = "whsec_abcdef1234567890abcdef1234567890"
    preview = SecretResolver.make_preview(raw)
    assert preview.startswith("whsec_ab...")
    assert preview.endswith("7890")
    assert "1234567890" not in preview


def test_secret_symmetric_encryption_and_decryption():
    """Verify secrets can be encrypted at rest and decrypted without data loss."""
    raw = SecretResolver.generate_secret()
    encrypted = SecretResolver.encrypt_secret(raw)

    assert encrypted != raw
    decrypted = SecretResolver.decrypt_secret(encrypted)
    assert decrypted == raw


def test_webhook_signature_verification_success():
    """Valid HMAC-SHA256 signature is verified successfully in constant time."""
    secret = "whsec_test_secret_for_signing_purposes"
    payload = b'{"event_id": "evt-123", "type": "ticket.created"}'

    expected_hex = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    prefixed_sig = f"sha256={expected_hex}"

    # Verify both prefixed and raw hex signatures
    WebhookVerifier.verify_signature(payload, prefixed_sig, secret)
    WebhookVerifier.verify_signature(payload, expected_hex, secret)


def test_webhook_signature_verification_invalid():
    """Invalid signature or altered payload triggers SignatureVerificationException."""
    secret = "whsec_test_secret_for_signing_purposes"
    payload = b'{"event_id": "evt-123", "type": "ticket.created"}'
    invalid_sig = "sha256=0000000000000000000000000000000000000000000000000000000000000000"

    with pytest.raises(SignatureVerificationException):
        WebhookVerifier.verify_signature(payload, invalid_sig, secret)

    # Tampered payload
    tampered_payload = b'{"event_id": "evt-123", "type": "ticket.created", "hacked": true}'
    valid_sig = f"sha256={hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()}"
    with pytest.raises(SignatureVerificationException):
        WebhookVerifier.verify_signature(tampered_payload, valid_sig, secret)


def test_webhook_signature_verification_missing():
    """Missing signature header raises SignatureVerificationException."""
    with pytest.raises(SignatureVerificationException):
        WebhookVerifier.verify_signature(b"{}", None, "whsec_secret")


def test_webhook_timestamp_tolerance_and_replay_rejection():
    """Timestamp outside tolerance window is rejected to prevent replay attacks."""
    now = int(time.time())

    # Within tolerance (5 minutes)
    WebhookVerifier.verify_timestamp(str(now), tolerance_seconds=300)
    WebhookVerifier.verify_timestamp(str(now - 120), tolerance_seconds=300)

    # Expired timestamp (10 minutes ago)
    with pytest.raises(EventReplayWindowException):
        WebhookVerifier.verify_timestamp(str(now - 600), tolerance_seconds=300)

    # Future timestamp (10 minutes ahead)
    with pytest.raises(EventReplayWindowException):
        WebhookVerifier.verify_timestamp(str(now + 600), tolerance_seconds=300)


def test_webhook_payload_size_limit():
    """Payloads exceeding maximum byte threshold are rejected."""
    small_payload = b"x" * 1024
    WebhookVerifier.validate_payload_size(small_payload, max_bytes=2048)

    oversized_payload = b"x" * 4096
    with pytest.raises(PayloadSizeLimitException):
        WebhookVerifier.validate_payload_size(oversized_payload, max_bytes=2048)


def test_webhook_content_type_validation():
    """Only application/json content type is accepted."""
    WebhookVerifier.validate_content_type("application/json")
    WebhookVerifier.validate_content_type("application/json; charset=utf-8")

    with pytest.raises(InvalidContentTypeException):
        WebhookVerifier.validate_content_type("text/html")

    with pytest.raises(InvalidContentTypeException):
        WebhookVerifier.validate_content_type(None)
