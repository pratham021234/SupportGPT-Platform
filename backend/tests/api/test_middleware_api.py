"""API tests verifying correlation ID propagation and timing middleware."""

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_correlation_id_generated_when_missing(async_client: AsyncClient):
    """Verify X-Request-ID is automatically generated as UUID4 when not provided."""
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    request_id = response.headers["x-request-id"]
    # Check that it parses as a valid UUID
    parsed_uuid = uuid.UUID(request_id)
    assert parsed_uuid.version == 4


@pytest.mark.asyncio
async def test_correlation_id_preserved_when_supplied(async_client: AsyncClient):
    """Verify incoming X-Request-ID is preserved and echoed back."""
    custom_id = "req-custom-client-trace-9999"
    response = await async_client.get("/healthz", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == custom_id


@pytest.mark.asyncio
async def test_response_time_header_present(async_client: AsyncClient):
    """Verify X-Response-Time-Ms header is included and numeric."""
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    assert "x-response-time-ms" in response.headers
    response_time = float(response.headers["x-response-time-ms"])
    assert response_time >= 0.0


@pytest.mark.asyncio
async def test_404_error_returns_structured_payload(async_client: AsyncClient):
    """Verify non-existent route returns uniform ErrorResponse structure without leakage."""
    response = await async_client.get("/api/v1/non_existent_route")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "HTTP_ERROR"
    assert "timestamp" in data["error"]
    assert "request_id" in data["error"]
