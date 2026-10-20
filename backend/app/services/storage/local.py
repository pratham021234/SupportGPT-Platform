"""Local filesystem storage backend with path-traversal guards and atomic writes."""

import asyncio
import hashlib
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from app.core.errors import (
    PathTraversalException,
    PayloadSizeLimitException,
    ResourceNotFoundException,
    StorageException,
)
from app.core.logging import get_logger
from app.services.storage.base import StorageBackend, StorageObjectMetadata

logger = get_logger("supportgpt.storage.local")


class LocalStorageBackend(StorageBackend):
    """Secure local filesystem storage implementation for SupportGPT documents."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, storage_key: str) -> Path:
        """Resolve storage key against base directory ensuring strict boundary isolation."""
        if not storage_key:
            raise PathTraversalException("Empty storage key.")

        # Reject absolute paths, root-relative paths, Windows drive letters, and traversal syntax
        if (
            storage_key.startswith("/")
            or storage_key.startswith("\\")
            or ":" in storage_key
            or Path(storage_key).is_absolute()
        ):
            raise PathTraversalException("Access denied: absolute or root-relative path traversal detected.")

        parts = Path(storage_key).parts
        if ".." in parts:
            raise PathTraversalException("Access denied: path traversal detected.")

        target_path = (self.base_dir / storage_key).resolve()
        if not target_path.is_relative_to(self.base_dir):
            raise PathTraversalException("Access denied: path traversal detected.")

        return target_path

    async def store(
        self,
        storage_key: str,
        data: bytes | AsyncIterator[bytes],
        max_bytes: int,
        expected_checksum: str | None = None,
        media_type: str | None = None,
    ) -> StorageObjectMetadata:
        """Atomically stream and store binary object verifying size and checksum."""
        dest_path = self._resolve_path(storage_key)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_filename = f".tmp_{uuid.uuid4().hex}"
        tmp_path = dest_path.parent / tmp_filename

        hasher = hashlib.sha256()
        total_bytes = 0

        try:
            with open(tmp_path, "wb") as f:
                if isinstance(data, (bytes, bytearray)):
                    total_bytes = len(data)
                    if total_bytes > max_bytes:
                        raise PayloadSizeLimitException(
                            f"File size exceeds maximum allowed limit of {max_bytes} bytes."
                        )
                    hasher.update(data)
                    f.write(data)
                else:
                    async for chunk in data:
                        chunk_len = len(chunk)
                        total_bytes += chunk_len
                        if total_bytes > max_bytes:
                            raise PayloadSizeLimitException(
                                f"Upload stream exceeded limit of {max_bytes} bytes."
                            )
                        hasher.update(chunk)
                        f.write(chunk)

            calculated_checksum = hasher.hexdigest()
            if expected_checksum and calculated_checksum.lower() != expected_checksum.lower():
                raise StorageException(
                    "Integrity check failed: payload checksum does not match expected digest."
                )

            # Atomic replace into final target
            os.replace(tmp_path, dest_path)

            stat = dest_path.stat()
            return StorageObjectMetadata(
                storage_key=storage_key,
                size_bytes=stat.st_size,
                checksum=calculated_checksum,
                created_at=datetime.fromtimestamp(stat.st_ctime, tz=UTC),
                media_type=media_type,
            )

        except Exception as exc:
            # Cleanup temporary file if left behind
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            if isinstance(exc, (PayloadSizeLimitException, PathTraversalException, StorageException)):
                raise
            logger.error("Failed to store object: %s", str(exc))
            raise StorageException("Unable to persist document asset.") from exc

    async def read(self, storage_key: str, chunk_size: int = 64 * 1024) -> AsyncIterator[bytes]:
        """Stream stored binary data chunks asynchronously."""
        target_path = self._resolve_path(storage_key)
        if not target_path.exists() or not target_path.is_file():
            raise ResourceNotFoundException("Storage object", storage_key)

        def _read_chunks():
            with open(target_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    yield chunk

        for chunk in await asyncio.to_thread(_read_chunks):
            yield chunk

    async def read_bytes(self, storage_key: str) -> bytes:
        """Read complete file content into memory asynchronously."""
        target_path = self._resolve_path(storage_key)
        if not target_path.exists() or not target_path.is_file():
            raise ResourceNotFoundException("Storage object", storage_key)

        return await asyncio.to_thread(target_path.read_bytes)

    async def delete(self, storage_key: str) -> bool:
        """Delete stored object safely."""
        try:
            target_path = self._resolve_path(storage_key)
            if target_path.exists() and target_path.is_file():
                await asyncio.to_thread(target_path.unlink)
                return True
            return False
        except PathTraversalException:
            raise
        except Exception as exc:
            logger.error("Failed to delete storage object: %s", str(exc))
            raise StorageException("Failed to delete storage object.") from exc

    async def exists(self, storage_key: str) -> bool:
        """Check if storage key exists and is a file."""
        try:
            target_path = self._resolve_path(storage_key)
            return await asyncio.to_thread(lambda: target_path.is_file())
        except Exception:
            return False

    async def get_metadata(self, storage_key: str) -> StorageObjectMetadata | None:
        """Retrieve stored object metadata without reading full payload."""
        target_path = self._resolve_path(storage_key)
        if not target_path.exists() or not target_path.is_file():
            return None

        stat = await asyncio.to_thread(target_path.stat)

        # Compute checksum via threaded hash
        def _compute_hash() -> str:
            h = hashlib.sha256()
            with open(target_path, "rb") as f:
                for b in iter(lambda: f.read(64 * 1024), b""):
                    h.update(b)
            return h.hexdigest()

        checksum = await asyncio.to_thread(_compute_hash)
        return StorageObjectMetadata(
            storage_key=storage_key,
            size_bytes=stat.st_size,
            checksum=checksum,
            created_at=datetime.fromtimestamp(stat.st_ctime, tz=UTC),
        )
