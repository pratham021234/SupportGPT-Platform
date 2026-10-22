"""Storage service package for object persistence in SupportGPT."""

from app.core.config import get_settings
from app.services.storage.base import StorageBackend, StorageObjectMetadata
from app.services.storage.local import LocalStorageBackend

from pathlib import Path

_storage_instance: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Return the configured storage backend singleton."""
    global _storage_instance
    if _storage_instance is None:
        settings = get_settings()
        if settings.STORAGE_BACKEND == "local":
            base_dir = Path(settings.LOCAL_STORAGE_DIR)
            if not base_dir.is_absolute():
                backend_dir = Path(__file__).resolve().parents[3]
                if (backend_dir / base_dir).exists():
                    base_dir = backend_dir / base_dir
                elif not (Path.cwd() / base_dir).exists():
                    base_dir = backend_dir / base_dir
            _storage_instance = LocalStorageBackend(base_dir=base_dir)
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
