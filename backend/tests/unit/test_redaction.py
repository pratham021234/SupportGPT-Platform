"""Unit tests for centralized sensitive information redaction."""

from app.core.logging import StructuredJsonFormatter, redact_sensitive_data


def test_dictionary_sensitive_keys_redacted() -> None:
    payload = {
        "user_id": "usr_123",
        "username": "alice",
        "password": "SuperSecretPassword!123",
        "token": "token_abc123xyz",
        "nested": {
            "api_key": "sk-1234567890abcdef1234567890",
            "safe_field": "public_data",
            "session_token": "sess_987654321",
            "raw_prompt": "You are a customer service bot...",
        },
    }

    sanitized = redact_sensitive_data(payload)

    assert sanitized["username"] == "alice"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["token"] == "[REDACTED]"
    assert sanitized["nested"]["safe_field"] == "public_data"
    assert sanitized["nested"]["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["session_token"] == "[REDACTED]"
    assert sanitized["nested"]["raw_prompt"] == "[REDACTED]"


def test_string_pattern_redaction() -> None:
    # Bearer token
    text_bearer = (
        "Authorization failed for Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDN context"
    )
    assert "Bearer [REDACTED]" in redact_sensitive_data(text_bearer)

    # OpenAI API Key
    text_openai = "Connecting to provider using sk-abcdef1234567890abcdef1234567890 and fallback"
    assert "sk-[REDACTED]" in redact_sensitive_data(text_openai)

    # Payment Card Number
    text_card = "Customer attempted payment using 4532-1234-5678-9010 on checkout"
    assert "[REDACTED_CARD]" in redact_sensitive_data(text_card)

    # Social Security Number
    text_ssn = "Customer verified identity with SSN 123-45-6789"
    assert "[REDACTED_SSN]" in redact_sensitive_data(text_ssn)

    # Database URL password
    db_url = "postgresql+asyncpg://admin:SecretDatabasePass123!@localhost:5432/supportgpt"
    redacted_url = redact_sensitive_data(db_url)
    assert "SecretDatabasePass123!" not in redacted_url
    assert "admin:[REDACTED]@" in redacted_url


def test_structured_json_formatter_sanitizes_message_and_extras() -> None:
    import logging

    formatter = StructuredJsonFormatter(environment="test")
    record = logging.LogRecord(
        name="test.logger",
        level=logging.ERROR,
        pathname="test.py",
        lineno=10,
        msg="Failed request with auth token: sk-abcdef1234567890abcdef1234567890",
        args=(),
        exc_info=None,
    )
    record.extra_fields = {
        "password": "plain_password",
        "api_endpoint": "/api/v1/tickets",
    }

    formatted = formatter.format(record)
    assert "plain_password" not in formatted
    assert "[REDACTED]" in formatted
    assert "sk-[REDACTED]" in formatted
    assert "/api/v1/tickets" in formatted
