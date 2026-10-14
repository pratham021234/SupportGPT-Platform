"""Structured application logging with request correlation ID integration.

Ensures predictable, machine-readable logs and prevents accidental credential leakage.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# ContextVar storing correlation ID for the active request task
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id_ctx", default=None)


class StructuredJsonFormatter(logging.Formatter):
    """Custom JSON formatter for production-ready, structured log output."""

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
    }

    def format(self, record: logging.LogRecord) -> str:
        correlation_id = correlation_id_ctx.get()

        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id,
        }

        # Include exception information if available (sanitized)
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Include custom extra fields if passed
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            sanitized_extras = self._sanitize_dict(record.extra_fields)
            log_data.update(sanitized_extras)

        return json.dumps(log_data)

    def _sanitize_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Redact sensitive keys from log dictionaries."""
        sanitized = {}
        for k, v in data.items():
            if any(sensitive in k.lower() for sensitive in self.SENSITIVE_KEYS):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, dict):
                sanitized[k] = self._sanitize_dict(v)
            else:
                sanitized[k] = v
        return sanitized


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
        console_handler.setFormatter(StructuredJsonFormatter())
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
