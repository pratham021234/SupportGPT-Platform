"""Security and cryptographic primitives for SupportGPT AI.

Handles Argon2id password hashing, constant-time verification, session token generation,
and email normalization.
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

# Configure production-standard Argon2id hasher
# Memory: 64MB (65536 KiB), Time cost: 3 iterations, Parallelism: 4 threads
_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def normalize_email(email: str) -> str:
    """Normalize an email address according to explicit, deterministic rules.

    - Strips leading and trailing whitespace.
    - Converts entire string to lowercase.
    - Rejects empty values.
    """
    if not email:
        raise ValueError("Email address cannot be empty.")
    normalized = email.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError(f"Malformed email address: '{email}'")
    return normalized


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using Argon2id.

    Never stores or logs plaintext passwords.
    """
    if not plain_password:
        raise ValueError("Password cannot be empty.")
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash using constant-time comparison.

    Returns False safely on mismatch or invalid hash format without leaking exceptions.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        return _password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError):
        return False
    except Exception:
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Check if the password hash needs to be updated to match current Argon2id parameters."""
    try:
        return _password_hasher.check_needs_rehash(hashed_password)
    except Exception:
        return True


def generate_session_token() -> str:
    """Generate a high-entropy, cryptographically secure opaque session token (256 bits)."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Compute a SHA-256 hash of an opaque session token for safe persistence."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
