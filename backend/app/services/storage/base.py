"""Storage abstraction and metadata definitions for SupportGPT knowledge assets."""

import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StorageObjectMetadata:
    """Metadata representing a stored binary object."""

    storage_key: str
    size_bytes: int
    checksum: str
    created_at: datetime
    media_type: str | None = None


class StorageBackend(ABC):
    """Abstract storage interface decoupling storage operations from domain services."""

    @abstractmethod
    async def store(
        self,
        storage_key: str,
        data: bytes | AsyncIterator[bytes],
        max_bytes: int,
        expected_checksum: str | None = None,
        media_type: str | None = None,
    ) -> StorageObjectMetadata:
        """Store an object securely with streaming size and checksum enforcement.

        Raises:
            PayloadSizeLimitException: If data exceeds max_bytes.
            PathTraversalException: If storage_key attempts to traverse outside storage root.
            StorageException: On checksum mismatch, I/O error, or storage failure.
        """
        pass

    @abstractmethod
    async def read(self, storage_key: str) -> AsyncIterator[bytes]:
        """Stream stored binary data chunks."""
        pass

    @abstractmethod
    async def read_bytes(self, storage_key: str) -> bytes:
        """Read full binary contents into memory."""
        pass

    @abstractmethod
    async def delete(self, storage_key: str) -> bool:
        """Delete stored object safely. Returns True if object existed and was removed."""
        pass

    @abstractmethod
    async def exists(self, storage_key: str) -> bool:
        """Verify whether an object exists in storage."""
        pass

    @abstractmethod
    async def get_metadata(self, storage_key: str) -> StorageObjectMetadata | None:
        """Retrieve stored object metadata without reading full payload."""
        pass

    @staticmethod
    def generate_storage_key(
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
        version_number: int,
    ) -> str:
        """Generate an opaque, non-guessable storage key isolated by tenant."""
        opaque_id = uuid.uuid4().hex
        return f"org_{organization_id}/docs/{document_id}/v{version_number}_{opaque_id}.bin"
