"""Webhook authenticity, signature verification, and replay protection."""

import hashlib
import hmac
import time
from datetime import datetime

from app.core.config import settings
from app.core.errors import (
    EventReplayWindowException,
    InvalidContentTypeException,
    PayloadSizeLimitException,
    SignatureVerificationException,
)


class WebhookVerifier:
    """Verifies incoming webhook payload authenticity, timestamp freshness, and size constraints."""

    @staticmethod
    def validate_content_type(content_type: str | None) -> None:
        """Enforce application/json for standard webhook requests."""
        if not content_type:
            raise InvalidContentTypeException("Missing Content-Type header.")
        media_type = content_type.split(";")[0].strip().lower()
        if media_type != "application/json":
            raise InvalidContentTypeException(
                f"Content-Type '{content_type}' is unsupported. Must be 'application/json'."
            )

    @staticmethod
    def validate_payload_size(raw_bytes: bytes, max_bytes: int | None = None) -> None:
        """Enforce strict upper bound on raw inbound payload bytes."""
        limit = max_bytes or settings.INGESTION_WEBHOOK_MAX_PAYLOAD_BYTES
        if len(raw_bytes) > limit:
            raise PayloadSizeLimitException(
                f"Payload size of {len(raw_bytes)} bytes exceeds limit of {limit} bytes."
            )

    @staticmethod
    def verify_timestamp(
        timestamp_header: str | None,
        tolerance_seconds: int | None = None,
    ) -> None:
        """Validate timestamp to prevent replay attacks within configured tolerance window."""
        if not timestamp_header:
            # If provider does not supply a timestamp, continue with signature check only
            return

        tolerance = tolerance_seconds or settings.INGESTION_TIMESTAMP_TOLERANCE_SECONDS
        now_ts = time.time()

        try:
            # Support both integer unix timestamp and ISO-8601 string
            if timestamp_header.isdigit() or (
                timestamp_header.startswith("-") and timestamp_header[1:].isdigit()
            ):
                event_ts = float(timestamp_header)
            else:
                # ISO-8601
                event_dt = datetime.fromisoformat(timestamp_header.replace("Z", "+00:00"))
                event_ts = event_dt.timestamp()
        except Exception:
            raise EventReplayWindowException(
                f"Invalid timestamp header format: '{timestamp_header}'."
            ) from None

        diff = abs(now_ts - event_ts)
        if diff > tolerance:
            raise EventReplayWindowException(
                f"Webhook timestamp delta ({diff:.1f}s) exceeds tolerance window of {tolerance}s."
            )

    @staticmethod
    def verify_signature(
        raw_body: bytes,
        signature_header: str | None,
        secret: str,
    ) -> None:
        """Validate HMAC-SHA256 signature using constant-time comparison."""
        if not signature_header:
            raise SignatureVerificationException("Missing required webhook signature header.")

        cleaned_sig = signature_header.strip()
        expected_hex = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

        # Support both 'sha256=<hex>' and raw '<hex>'
        expected_prefixed = f"sha256={expected_hex}"
        valid = hmac.compare_digest(cleaned_sig, expected_prefixed) or hmac.compare_digest(
            cleaned_sig, expected_hex
        )

        if not valid:
            raise SignatureVerificationException("Webhook signature verification failed.")
