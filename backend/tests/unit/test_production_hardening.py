"""Tests for Phase 09 Enterprise Readiness, Security Hardening, and Operational Recovery."""

import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import RateLimitExceededException
from app.core.rate_limiter import InMemoryRateLimiter
from app.main import app
from scripts.restore_database import compute_sha256, verify_backup_integrity


class TestProductionConfigurationInvariants:
    """Validate that insecure configurations are deterministically rejected in staging & production."""

    def test_production_rejects_debug_mode(self):
        with pytest.raises(ValueError, match="DEBUG mode must be False"):
            Settings(
                ENVIRONMENT="production",
                DEBUG=True,
                SESSION_SECRET_KEY="a" * 32,
                SESSION_COOKIE_SECURE=True,
                CORS_ORIGINS=["https://app.supportgpt.com"],
                DATABASE_URL="postgresql+asyncpg://user:strong_prod_pass_1234@db:5432/db",
                WEBHOOK_SECRETS_ENCRYPTION_KEY="k" * 32,
            )

    def test_production_rejects_default_database_password(self):
        with pytest.raises(ValueError, match="default development credentials"):
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SESSION_SECRET_KEY="a" * 32,
                SESSION_COOKIE_SECURE=True,
                CORS_ORIGINS=["https://app.supportgpt.com"],
                DATABASE_URL="postgresql+asyncpg://supportgpt_user:supportgpt_dev_password@db:5432/db",
                WEBHOOK_SECRETS_ENCRYPTION_KEY="k" * 32,
            )

    def test_production_rejects_insecure_session_cookie(self):
        with pytest.raises(ValueError, match="SESSION_COOKIE_SECURE must be True"):
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SESSION_SECRET_KEY="a" * 32,
                SESSION_COOKIE_SECURE=False,
                CORS_ORIGINS=["https://app.supportgpt.com"],
                DATABASE_URL="postgresql+asyncpg://user:strong_prod_pass_1234@db:5432/db",
                WEBHOOK_SECRETS_ENCRYPTION_KEY="k" * 32,
            )

    def test_production_rejects_weak_session_secret(self):
        with pytest.raises(ValueError, match="SESSION_SECRET_KEY must be at least 32 characters"):
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SESSION_SECRET_KEY="short_secret",
                SESSION_COOKIE_SECURE=True,
                CORS_ORIGINS=["https://app.supportgpt.com"],
                DATABASE_URL="postgresql+asyncpg://user:strong_prod_pass_1234@db:5432/db",
                WEBHOOK_SECRETS_ENCRYPTION_KEY="k" * 32,
            )

    def test_production_rejects_wildcard_or_localhost_cors(self):
        with pytest.raises(ValueError, match="Localhost CORS origin"):
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SESSION_SECRET_KEY="a" * 32,
                SESSION_COOKIE_SECURE=True,
                CORS_ORIGINS=["http://localhost:3000"],
                DATABASE_URL="postgresql+asyncpg://user:strong_prod_pass_1234@db:5432/db",
                WEBHOOK_SECRETS_ENCRYPTION_KEY="k" * 32,
            )

    def test_production_rejects_missing_webhook_encryption_key(self):
        with pytest.raises(ValueError, match="WEBHOOK_SECRETS_ENCRYPTION_KEY must be configured"):
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SESSION_SECRET_KEY="a" * 32,
                SESSION_COOKIE_SECURE=True,
                CORS_ORIGINS=["https://app.supportgpt.com"],
                DATABASE_URL="postgresql+asyncpg://user:strong_prod_pass_1234@db:5432/db",
                WEBHOOK_SECRETS_ENCRYPTION_KEY="",
            )

    def test_production_rejects_openai_without_api_key(self):
        with pytest.raises(ValueError, match="LLM_API_KEY must be set"):
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SESSION_SECRET_KEY="a" * 32,
                SESSION_COOKIE_SECURE=True,
                CORS_ORIGINS=["https://app.supportgpt.com"],
                DATABASE_URL="postgresql+asyncpg://user:strong_prod_pass_1234@db:5432/db",
                WEBHOOK_SECRETS_ENCRYPTION_KEY="k" * 32,
                LLM_PROVIDER="openai",
                LLM_API_KEY="",
            )

    def test_valid_production_settings_accepted(self):
        s = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            SESSION_SECRET_KEY="a" * 32,
            SESSION_COOKIE_SECURE=True,
            CORS_ORIGINS=["https://app.supportgpt.com"],
            DATABASE_URL="postgresql+asyncpg://user:strong_prod_pass_1234@db:5432/db",
            WEBHOOK_SECRETS_ENCRYPTION_KEY="k" * 32,
            LLM_PROVIDER="openai",
            LLM_API_KEY="sk-proj-valid-api-key-here",
        )
        assert s.ENVIRONMENT == "production"
        assert s.DEBUG is False


class TestSecurityHeadersMiddleware:
    """Validate that defense-in-depth security headers are injected into all HTTP responses."""

    def test_security_headers_present_on_response(self):
        client = TestClient(app)
        res = client.get("/healthz")
        assert res.status_code == 200
        assert res.headers.get("X-Content-Type-Options") == "nosniff"
        assert res.headers.get("X-Frame-Options") == "DENY"
        assert res.headers.get("X-XSS-Protection") == "1; mode=block"
        assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "default-src 'self'" in res.headers.get("Content-Security-Policy", "")


class TestRateLimiter:
    """Validate sliding-window rate limiter mechanics."""

    @pytest.mark.asyncio
    async def test_rate_limiter_allows_under_limit(self):
        limiter = InMemoryRateLimiter()
        key = "test_user_ok"
        # Should not raise exception
        await limiter.check(key, max_attempts=5, window_seconds=60)
        await limiter.record_failure(key, window_seconds=60)
        await limiter.check(key, max_attempts=5, window_seconds=60)

    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_when_exceeded(self):
        limiter = InMemoryRateLimiter()
        key = "test_user_exceed"
        for _ in range(5):
            await limiter.record_failure(key, window_seconds=60)

        with pytest.raises(RateLimitExceededException, match="Too many failed attempts"):
            await limiter.check(key, max_attempts=5, window_seconds=60)

    @pytest.mark.asyncio
    async def test_rate_limiter_resets_on_success(self):
        limiter = InMemoryRateLimiter()
        key = "test_user_reset"
        for _ in range(5):
            await limiter.record_failure(key, window_seconds=60)

        with pytest.raises(RateLimitExceededException):
            await limiter.check(key, max_attempts=5, window_seconds=60)

        await limiter.reset(key)
        # Should now succeed without raising
        await limiter.check(key, max_attempts=5, window_seconds=60)

    @pytest.mark.asyncio
    async def test_rate_limiter_clear_all(self):
        limiter = InMemoryRateLimiter()
        await limiter.record_failure("user1", window_seconds=60)
        await limiter.record_failure("user2", window_seconds=60)
        await limiter.clear_all()
        await limiter.check("user1", max_attempts=1, window_seconds=60)
        await limiter.check("user2", max_attempts=1, window_seconds=60)


class TestBackupAndRestoreIntegrity:
    """Validate cryptographic checksumming and disaster recovery verification."""

    def test_verify_backup_integrity_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_file = os.path.join(tmpdir, "test_backup.dump")
            content = b"TEST BACKUP ARCHIVE CONTENT FOR INTEGRITY CHECK"
            with open(backup_file, "wb") as f:
                f.write(content)

            sha = compute_sha256(backup_file)
            checksum_file = f"{backup_file}.sha256"
            with open(checksum_file, "w", encoding="utf-8") as f:
                f.write(f"{sha}  test_backup.dump\n")

            assert verify_backup_integrity(backup_file) is True

    def test_verify_backup_integrity_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_file = os.path.join(tmpdir, "test_backup.dump")
            with open(backup_file, "wb") as f:
                f.write(b"ORIGINAL CONTENT")

            checksum_file = f"{backup_file}.sha256"
            with open(checksum_file, "w", encoding="utf-8") as f:
                f.write("0000000000000000000000000000000000000000000000000000000000000000  test_backup.dump\n")

            with pytest.raises(ValueError, match="Integrity verification failure"):
                verify_backup_integrity(backup_file)

    def test_verify_backup_integrity_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            verify_backup_integrity("non_existent_file_path.dump")
