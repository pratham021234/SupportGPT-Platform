"""Storage service package for object persistence in SupportGPT."""

from app.core.config import get_settings
from app.services.storage.base import StorageBackend, StorageObjectMetadata
from app.services.storage.local import LocalStorageBackend

_storage_instance: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Return the configured storage backend singleton."""
    global _storage_instance
    if _storage_instance is None:
        settings = get_settings()
        if settings.STORAGE_BACKEND == "local":
            _storage_instance = LocalStorageBackend(base_dir=settings.LOCAL_STORAGE_DIR)
        else:
            raise NotImplementedError(
                f"Storage backend '{settings.STORAGE_BACKEND}' is not implemented."
            )
    return _storage_instance


__all__ = [
    "StorageBackend",
    "StorageObjectMetadata",
    "LocalStorageBackend",
    "get_storage_backend",
]
