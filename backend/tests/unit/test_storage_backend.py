"""Unit tests verifying LocalStorageBackend path traversal defense, atomic streaming, and size limits."""

import tempfile
import uuid
from pathlib import Path

import pytest

from app.core.errors import (
    PathTraversalException,
    PayloadSizeLimitException,
    ResourceNotFoundException,
    StorageException,
)
from app.services.storage.local import LocalStorageBackend


@pytest.fixture
def temp_storage():
    """Create a temporary storage backend instance for isolated testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        backend = LocalStorageBackend(base_dir=tmp_dir)
        yield backend, Path(tmp_dir)


@pytest.mark.asyncio
async def test_store_and_read_bytes(temp_storage):
    backend, root_dir = temp_storage
    key = "org_1/docs/doc_1/v1_test.bin"
    payload = b"Hello, SupportGPT Knowledge Base!"

    meta = await backend.store(storage_key=key, data=payload, max_bytes=1024)

    assert meta.storage_key == key
    assert meta.size_bytes == len(payload)
    assert len(meta.checksum) == 64
    assert await backend.exists(key) is True

    retrieved = await backend.read_bytes(key)
    assert retrieved == payload


@pytest.mark.asyncio
async def test_streaming_read(temp_storage):
    backend, _ = temp_storage
    key = "org_1/stream.bin"
    payload = b"A" * 128 * 1024  # 128 KB

    await backend.store(storage_key=key, data=payload, max_bytes=200 * 1024)

    chunks = []
    async for chunk in backend.read(key, chunk_size=32 * 1024):
        chunks.append(chunk)

    assert b"".join(chunks) == payload
    assert len(chunks) == 4


@pytest.mark.asyncio
async def test_payload_size_limit_exceeded(temp_storage):
    backend, root_dir = temp_storage
    key = "org_1/oversized.bin"
    payload = b"X" * 2000

    with pytest.raises(PayloadSizeLimitException):
        await backend.store(storage_key=key, data=payload, max_bytes=1000)

    # Verify no file or orphaned temp file was left
    assert await backend.exists(key) is False
    temp_files = list(root_dir.glob("**/.tmp_*"))
    assert len(temp_files) == 0


@pytest.mark.asyncio
async def test_streaming_size_limit_enforced_early(temp_storage):
    backend, root_dir = temp_storage
    key = "org_1/stream_oversized.bin"

    async def _data_gen():
        for _ in range(10):
            yield b"Y" * 500

    with pytest.raises(PayloadSizeLimitException):
        await backend.store(storage_key=key, data=_data_gen(), max_bytes=1500)

    assert await backend.exists(key) is False
    temp_files = list(root_dir.glob("**/.tmp_*"))
    assert len(temp_files) == 0


@pytest.mark.asyncio
async def test_path_traversal_detection(temp_storage):
    backend, _ = temp_storage

    traversal_keys = [
        "../../etc/passwd",
        "org_1/../../../windows/win.ini",
        "..\\..\\system32\\cmd.exe",
        "/etc/shadow",
    ]

    for key in traversal_keys:
        with pytest.raises(PathTraversalException):
            await backend.store(storage_key=key, data=b"malicious", max_bytes=1000)

        with pytest.raises(PathTraversalException):
            await backend.read_bytes(key)

        with pytest.raises(PathTraversalException):
            await backend.delete(key)


@pytest.mark.asyncio
async def test_checksum_verification_failure(temp_storage):
    backend, _ = temp_storage
    key = "org_1/checksum_test.bin"
    payload = b"Sensitive Content"
    wrong_checksum = "0000000000000000000000000000000000000000000000000000000000000000"

    with pytest.raises(StorageException, match="Integrity check failed"):
        await backend.store(
            storage_key=key,
            data=payload,
            max_bytes=1024,
            expected_checksum=wrong_checksum,
        )

    assert await backend.exists(key) is False


@pytest.mark.asyncio
async def test_delete_and_not_found(temp_storage):
    backend, _ = temp_storage
    key = "org_1/to_delete.bin"
    await backend.store(storage_key=key, data=b"temporary", max_bytes=1024)

    assert await backend.exists(key) is True
    deleted = await backend.delete(key)
    assert deleted is True
    assert await backend.exists(key) is False

    # Second delete returns False
    assert await backend.delete(key) is False

    # Reading deleted raises ResourceNotFoundException
    with pytest.raises(ResourceNotFoundException):
        await backend.read_bytes(key)


@pytest.mark.asyncio
async def test_generate_storage_key_isolation():
    org_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    key1 = LocalStorageBackend.generate_storage_key(org_id, doc_id, version_number=1)
    key2 = LocalStorageBackend.generate_storage_key(org_id, doc_id, version_number=2)

    assert f"org_{org_id}/docs/{doc_id}/v1_" in key1
    assert f"org_{org_id}/docs/{doc_id}/v2_" in key2
    assert key1 != key2
    assert key1.endswith(".bin")
