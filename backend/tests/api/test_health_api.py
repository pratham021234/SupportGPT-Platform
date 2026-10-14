"""API tests verifying liveness, readiness, and system info endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness_probe_healthz(async_client: AsyncClient):
    """Verify /healthz returns 200 OK and valid status payload."""
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "SupportGPT-AI"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_probe_structure(async_client: AsyncClient):
    """Verify /readyz returns expected dependency status structure.

    If database is not running in test runner, readiness probe returns 503 with degraded status,
    or 200 if running. Both states must adhere to the typed schema without unhandled exceptions.
    """
    response = await async_client.get("/readyz")
    assert response.status_code in (200, 503)
    data = response.json()
    assert data["status"] in ("ready", "degraded")
    assert "database" in data["dependencies"]
    assert "redis" in data["dependencies"]
    assert data["dependencies"]["database"]["status"] in ("up", "down")


@pytest.mark.asyncio
async def test_system_info_endpoint(async_client: AsyncClient):
    """Verify /api/v1/system/info returns correct release and architecture tier."""
    response = await async_client.get("/api/v1/system/info")
    assert response.status_code == 200
    data = response.json()
    assert data["app_name"] == "SupportGPT-AI"
    assert data["version"] == "0.1.0"
    assert "Phase 00" in data["phase"]
    assert "Modular Monolith" in data["architecture"]
