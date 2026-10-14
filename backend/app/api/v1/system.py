"""Platform system metadata endpoint."""

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.system import SystemInfoResponse

router = APIRouter(prefix="/system", tags=["System Information"])


@router.get(
    "/info",
    response_model=SystemInfoResponse,
    summary="Platform System Information",
    description="Returns public release version, phase description, and architectural blueprint metadata.",
)
async def get_system_info() -> SystemInfoResponse:
    return SystemInfoResponse(
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        phase="Phase 00: Foundation & Standards",
        architecture="Modular Monolith with Domain Isolation",
        docs_url="/docs",
    )
