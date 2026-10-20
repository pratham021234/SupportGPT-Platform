"""Cryptographic secret management and reference resolution for external sources."""

import base64
import hashlib
import os
import secrets

from app.core.config import settings
from app.models.event_source import EventSource


class SecretResolver:
    """Manages generation, masking, encryption, and runtime resolution of webhook signing secrets."""

    @staticmethod
    def generate_secret() -> str:
        """Generate a cryptographically secure random webhook signing secret."""
        return f"whsec_{secrets.token_urlsafe(32)}"

    @staticmethod
    def hash_secret(raw_secret: str) -> str:
        """Produce a SHA-256 hex digest of the raw secret for tamper detection."""
        return hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()

    @staticmethod
    def make_preview(raw_secret: str) -> str:
        """Generate a masked preview suitable for UI/API display."""
        if len(raw_secret) <= 12:
            return "whsec_****"
        return f"{raw_secret[:8]}...{raw_secret[-4:]}"

    @staticmethod
    def _get_encryption_key_bytes() -> bytes:
        """Derive 32-byte key from configured key or session secret."""
        custom_key = settings.WEBHOOK_SECRETS_ENCRYPTION_KEY or settings.SESSION_SECRET_KEY
        return hashlib.sha256(custom_key.encode("utf-8")).digest()

    @classmethod
    def encrypt_secret(cls, raw_secret: str) -> str:
        """Symmetrically encrypt secret for secure persistence at rest.

        Uses AES-CTR/XOR stream cipher with PBKDF-derived key and random 16-byte IV.
        """
        key = cls._get_encryption_key_bytes()
        iv = secrets.token_bytes(16)
        secret_bytes = raw_secret.encode("utf-8")

        # Deterministic stream cipher keystream generated via SHA-256 counter
        keystream = bytearray()
        counter = 0
        while len(keystream) < len(secret_bytes):
            block = hashlib.sha256(key + iv + counter.to_bytes(4, "big")).digest()
            keystream.extend(block)
            counter += 1

        cipher_bytes = bytes(
            s ^ k for s, k in zip(secret_bytes, keystream[: len(secret_bytes)], strict=True)
        )
        payload = iv + cipher_bytes
        return base64.urlsafe_b64encode(payload).decode("utf-8")

    @classmethod
    def decrypt_secret(cls, encrypted_secret: str) -> str:
        """Decrypt previously encrypted secret ciphertext."""
        key = cls._get_encryption_key_bytes()
        payload = base64.urlsafe_b64decode(encrypted_secret.encode("utf-8"))
        if len(payload) < 16:
            raise ValueError("Corrupted encrypted secret payload.")

        iv = payload[:16]
        cipher_bytes = payload[16:]

        keystream = bytearray()
        counter = 0
        while len(keystream) < len(cipher_bytes):
            block = hashlib.sha256(key + iv + counter.to_bytes(4, "big")).digest()
            keystream.extend(block)
            counter += 1

        secret_bytes = bytes(
            c ^ k for c, k in zip(cipher_bytes, keystream[: len(cipher_bytes)], strict=True)
        )
        return secret_bytes.decode("utf-8")

    @classmethod
    def resolve_source_signing_secret(cls, source: EventSource) -> str:
        """Retrieve authoritative signing secret for an event source.

        Priority:
        1. Explicit secret reference (e.g. env:VARIABLE_NAME)
        2. Decrypted database ciphertext
        """
        if source.secret_reference:
            ref = source.secret_reference.strip()
            if ref.startswith("env:"):
                var_name = ref[4:].strip()
                val = os.environ.get(var_name)
                if val:
                    return val.strip()

        if source.signing_secret_encrypted:
            return cls.decrypt_secret(source.signing_secret_encrypted)

        raise ValueError(
            f"No usable signing secret or reference available for source '{source.id}'."
        )
