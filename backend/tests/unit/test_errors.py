"""Unit tests verifying exception structures and sensitive data sanitization."""

import json
import logging

from app.core.errors import AppException, ResourceNotFoundException, ServiceUnavailableException
from app.core.logging import StructuredJsonFormatter


def test_app_exception_structure():
    """Verify AppException carries code, message, and default status."""
    exc = AppException(message="Custom failure", code="CUSTOM_ERR", status_code=400)
    assert exc.message == "Custom failure"
    assert exc.code == "CUSTOM_ERR"
    assert exc.status_code == 400


def test_resource_not_found_exception():
    """Verify ResourceNotFoundException formatting."""
    exc = ResourceNotFoundException(resource_name="Conversation", identifier="12345")
    assert exc.code == "RESOURCE_NOT_FOUND"
    assert exc.status_code == 404
    assert "Conversation with identifier '12345' was not found." in exc.message


def test_service_unavailable_exception():
    """Verify ServiceUnavailableException formatting."""
    exc = ServiceUnavailableException(service_name="PostgreSQL", reason="Connection timeout")
    assert exc.code == "SERVICE_UNAVAILABLE"
    assert exc.status_code == 503
    assert "PostgreSQL is currently unavailable" in exc.message


def test_structured_log_sanitization():
    """Verify that credentials and secrets are redacted from structured logs."""
    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Authentication processed",
        args=(),
        exc_info=None,
    )
    record.extra_fields = {
        "user_id": "usr_99",
        "password": "SuperSecretPassword123",
        "api_key": "sk-1234567890",
        "nested": {"token": "jwt_token_here", "safe_param": "allowed"},
    }

    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["user_id"] == "usr_99"
    assert parsed["password"] == "[REDACTED]"
    assert parsed["api_key"] == "[REDACTED]"
    assert parsed["nested"]["token"] == "[REDACTED]"
    assert parsed["nested"]["safe_param"] == "allowed"
