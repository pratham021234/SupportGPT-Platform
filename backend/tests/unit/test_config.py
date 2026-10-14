"""Unit tests verifying environment configuration validation and production invariants."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_default_development_settings():
    """Verify default development configuration values."""
    s = Settings(ENVIRONMENT="development")
    assert s.APP_NAME == "SupportGPT-AI"
    assert s.DEBUG is False
    assert s.ENVIRONMENT == "development"
    assert "http://localhost:3000" in s.CORS_ORIGINS
    assert s.async_database_url.startswith("postgresql+asyncpg://")


def test_cors_origins_parsing_from_string():
    """Verify comma-separated string parsing for CORS origins."""
    s = Settings(
        ENVIRONMENT="development",
        CORS_ORIGINS="https://app.supportgpt.ai, https://admin.supportgpt.ai",
    )
    assert len(s.CORS_ORIGINS) == 2
    assert "https://app.supportgpt.ai" in s.CORS_ORIGINS
    assert "https://admin.supportgpt.ai" in s.CORS_ORIGINS


def test_cors_origins_parsing_from_json_string():
    """Verify JSON array string parsing for CORS origins."""
    s = Settings(
        ENVIRONMENT="development",
        CORS_ORIGINS='["https://app.supportgpt.ai", "https://api.supportgpt.ai"]',
    )
    assert len(s.CORS_ORIGINS) == 2
    assert "https://app.supportgpt.ai" in s.CORS_ORIGINS


def test_production_invariant_debug_must_be_false():
    """Verify that setting DEBUG=True in production raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DEBUG=True,
            DATABASE_URL="postgresql+asyncpg://prod_user:StrongProdPass123!@db.internal:5432/prod_db",
            CORS_ORIGINS=["https://app.supportgpt.ai"],
        )
    assert "DEBUG mode must be False in 'production' environment" in str(exc_info.value)


def test_production_invariant_dev_password_forbidden():
    """Verify that default dev password in production raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            DATABASE_URL="postgresql+asyncpg://prod_user:supportgpt_dev_password@db.internal:5432/prod_db",
            CORS_ORIGINS=["https://app.supportgpt.ai"],
        )
    assert "DATABASE_URL uses default development credentials" in str(exc_info.value)


def test_production_invariant_wildcard_cors_forbidden():
    """Verify that wildcard CORS in production raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            DATABASE_URL="postgresql+asyncpg://prod_user:StrongProdPass123!@db.internal:5432/prod_db",
            CORS_ORIGINS=["*"],
        )
    assert "Wildcard '*' CORS origin is forbidden in production" in str(exc_info.value)
