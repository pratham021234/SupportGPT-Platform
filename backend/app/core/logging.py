"""Structured application logging with request and trace correlation ID integration.

Ensures predictable, machine-readable logs and prevents accidental credential or PII leakage.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# ContextVars storing correlation IDs for the active request task
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id_ctx", default=None)
trace_id_ctx: ContextVar[str | None] = ContextVar("trace_id_ctx", default=None)
organization_id_ctx: ContextVar[str | None] = ContextVar("organization_id_ctx", default=None)

# Regular expressions for string-level secret and sensitive PII detection
BEARER_PATTERN = re.compile(r"(?i)bearer\s+[a-zA-Z0-9\-._~+/]+=*")
API_KEY_PATTERN = re.compile(r"sk-[a-zA-Z0-9]{20,}")
JWT_PATTERN = re.compile(r"eyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]+")
CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
URL_PASSWORD_PATTERN = re.compile(r"(://[^:]+:)([^@]+)(@)")

SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "authorization",
    "api_key",
    "access_token",
    "private_key",
    "cookie",
    "session",
    "credential",
    "hash",
    "cvv",
    "credit_card",
    "card_number",
    "ssn",
    "raw_prompt",
    "raw_document",
}


def redact_sensitive_data(value: Any) -> Any:
    """Recursively redact secrets, authorization tokens, payment details, and PII from any payload."""
    if isinstance(value, dict):
        sanitized = {}
        for k, v in value.items():
            if any(sensitive in str(k).lower() for sensitive in SENSITIVE_KEYS):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = redact_sensitive_data(v)
        return sanitized
    elif isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    elif isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    elif isinstance(value, set):
        return {redact_sensitive_data(item) for item in value}
    elif isinstance(value, str):
        # Apply string pattern redactions
        text = BEARER_PATTERN.sub("Bearer [REDACTED]", value)
        text = API_KEY_PATTERN.sub("sk-[REDACTED]", text)
        text = JWT_PATTERN.sub("[REDACTED_JWT]", text)
        text = CREDIT_CARD_PATTERN.sub("[REDACTED_CARD]", text)
        text = SSN_PATTERN.sub("[REDACTED_SSN]", text)
        text = URL_PASSWORD_PATTERN.sub(r"\1[REDACTED]\3", text)
        return text
    return value


class StructuredJsonFormatter(logging.Formatter):
    """Custom JSON formatter for production-ready, structured log output with centralized redaction."""

    def __init__(self, environment: str = "production", service_name: str = "supportgpt-backend"):
        super().__init__()
        self.environment = environment
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        correlation_id = correlation_id_ctx.get()
        trace_id = trace_id_ctx.get()
        organization_id = organization_id_ctx.get()

        raw_message = record.getMessage()
        sanitized_message = redact_sensitive_data(raw_message)

        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "environment": self.environment,
            "logger": record.name,
            "message": sanitized_message,
            "correlation_id": correlation_id,
            "request_id": correlation_id,
            "trace_id": trace_id,
            "organization_id": organization_id,
        }

        # Include exception information if available (sanitized)
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            log_data["exception"] = redact_sensitive_data(exc_text)

        # Include custom extra fields if passed
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            sanitized_extras = redact_sensitive_data(record.extra_fields)
            log_data.update(sanitized_extras)

        return json.dumps(log_data)


def setup_logging(log_level: str = "INFO", environment: str = "development") -> None:
    """Initialize root and application loggers."""
    root_logger = logging.getLogger()
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to prevent duplicate lines
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)

    if environment in ("staging", "production"):
        console_handler.setFormatter(StructuredJsonFormatter(environment=environment))
    else:
        # Development human-readable structured formatter
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)

    # Reduce noise from chatty external libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Retrieve a configured application logger."""
    return logging.getLogger(name)
