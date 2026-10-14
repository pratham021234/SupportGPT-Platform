"""Health and readiness probe endpoints."""

import time

from fastapi import APIRouter, Response, status
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import verify_database_connection
from app.schemas.health import DependencyHealth, HealthStatusResponse, ReadinessResponse

logger = get_logger("supportgpt.health")
router = APIRouter(tags=["Health & Diagnostics"])


@router.get(
    "/healthz",
    response_model=HealthStatusResponse,
    summary="Process Liveness Probe",
    description="Returns process liveness. Used by container orchestrators to detect process crashes.",
)
async def liveness_probe() -> HealthStatusResponse:
    return HealthStatusResponse(
        status="ok",
        app=settings.APP_NAME,
        environment=settings.ENVIRONMENT,
        version=settings.APP_VERSION,
    )


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    responses={
        200: {"description": "All critical dependencies are healthy and accepting traffic."},
        503: {
            "description": "One or more critical dependencies are down; traffic should not be routed."
        },
    },
    summary="Platform Readiness Probe",
    description="Probes external dependencies (PostgreSQL, Redis) to verify traffic handling capability.",
)
async def readiness_probe(response: Response) -> ReadinessResponse:
    dependencies: dict[str, DependencyHealth] = {}
    is_ready = True

    # 1. Probe Authoritative PostgreSQL Database
    db_ok, db_latency, db_err = await verify_database_connection(timeout_seconds=2.0)
    dependencies["database"] = DependencyHealth(
        status="up" if db_ok else "down",
        latency_ms=db_latency,
        error=db_err,
    )
    if not db_ok:
        is_ready = False

    # 2. Probe Redis Cache / Broker
    redis_start = time.perf_counter()
    try:
        redis_client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2.0)
        await redis_client.ping()
        await redis_client.aclose()
        redis_latency = (time.perf_counter() - redis_start) * 1000
        dependencies["redis"] = DependencyHealth(
            status="up",
            latency_ms=round(redis_latency, 2),
            error=None,
        )
    except Exception as exc:
        redis_latency = (time.perf_counter() - redis_start) * 1000
        # For Phase 00, Redis unavailability does not block basic HTTP readiness if DB is up,
        # but is accurately reported as degraded
        dependencies["redis"] = DependencyHealth(
            status="degraded",
            latency_ms=round(redis_latency, 2),
            error=str(exc),
        )

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        readiness_status = "degraded"
    else:
        readiness_status = "ready"

    return ReadinessResponse(
        status=readiness_status,
        environment=settings.ENVIRONMENT,
        dependencies=dependencies,
    )
