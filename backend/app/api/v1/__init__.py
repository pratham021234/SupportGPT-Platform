"""API v1 Router aggregation."""

from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.system import router as system_router

api_v1_router = APIRouter()

# Mount health routes both at root and v1 for ease of orchestration probes
api_v1_router.include_router(health_router)
api_v1_router.include_router(system_router)
