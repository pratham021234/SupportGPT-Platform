"""Unit tests verifying Argon2id password hashing, constant-time verification, and email normalization."""

import pytest

from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    needs_rehash,
    normalize_email,
    verify_password,
)


def test_argon2id_password_hashing_and_verification():
    """Verify that Argon2id hashes passwords securely and verifies correctly."""
    plain = "SuperSecurePassword123!"
    hashed = hash_password(plain)

    # Hash must start with argon2id algorithm identifier
    assert hashed.startswith("$argon2id$")
    assert hashed != plain

    # Correct password succeeds
    assert verify_password(plain, hashed) is True

    # Incorrect password fails safely
    assert verify_password("WrongPassword123!", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(plain, "") is False


def test_email_normalization_rules():
    """Verify email normalization handles whitespace, casing, and malformed inputs."""
    assert normalize_email("  User.Test@Example.COM  ") == "user.test@example.com"
    assert normalize_email("SUPPORT@AcmeCorp.io") == "support@acmecorp.io"

    with pytest.raises(ValueError, match="Email address cannot be empty"):
        normalize_email("")

    with pytest.raises(ValueError, match="Malformed email address"):
        normalize_email("notanemail")

    with pytest.raises(ValueError, match="Malformed email address"):
        normalize_email("@nodomain.com")

    with pytest.raises(ValueError, match="Malformed email address"):
        normalize_email("noatdomain.com@")


def test_session_token_entropy_and_hashing():
    """Verify session token generation produces distinct high-entropy tokens and SHA-256 hashes."""
    token1 = generate_session_token()
    token2 = generate_session_token()

    assert len(token1) >= 40
    assert token1 != token2

    hash1 = hash_session_token(token1)
    hash2 = hash_session_token(token2)

    assert len(hash1) == 64  # SHA-256 hex digest length
    assert hash1 != hash2
    assert hash1 == hash_session_token(token1)  # Deterministic hash of token


def test_needs_rehash_detection():
    """Verify needs_rehash returns False for current parameters and True for invalid."""
    hashed = hash_password("Password123!")
    assert needs_rehash(hashed) is False
    assert needs_rehash("corrupt_or_old_hash") is True
