"""API v1 Router aggregation."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.customers import router as customers_router
from app.api.v1.health import router as health_router
from app.api.v1.ingestion import diagnostics_router as ingestion_diagnostics_router
from app.api.v1.ingestion import router as ingestion_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.sources import router as sources_router
from app.api.v1.system import router as system_router
from app.api.v1.tickets import router as tickets_router
from app.api.v1.webhooks import router as webhooks_router

api_v1_router = APIRouter()

# Mount routes
api_v1_router.include_router(health_router)
api_v1_router.include_router(system_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(organizations_router)
api_v1_router.include_router(tickets_router)
api_v1_router.include_router(conversations_router)
api_v1_router.include_router(customers_router)
api_v1_router.include_router(webhooks_router)
api_v1_router.include_router(sources_router)
api_v1_router.include_router(ingestion_router)
api_v1_router.include_router(ingestion_diagnostics_router)
