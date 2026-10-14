"""Root API routing configuration."""

from fastapi import APIRouter

from app.api.v1 import api_v1_router
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)
