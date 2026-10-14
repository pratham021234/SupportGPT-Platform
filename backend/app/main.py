"""SupportGPT AI — FastAPI Core Application Entrypoint.

Configures lifespan lifecycle, structured logging, middleware pipeline,
RFC 7807 error handlers, and route hierarchy.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.v1.health import router as root_health_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.logging import get_logger, setup_logging
from app.core.middleware import CorrelationIdMiddleware
from app.db.session import async_engine

logger = get_logger("supportgpt.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Graceful application lifespan context for resource initialization and teardown."""
    # Startup sequence
    setup_logging(log_level=settings.LOG_LEVEL, environment=settings.ENVIRONMENT)
    logger.info(
        f"Starting {settings.APP_NAME} v{settings.APP_VERSION} in [{settings.ENVIRONMENT}] mode"
    )

    yield

    # Teardown sequence
    logger.info("Initiating graceful shutdown: disposing database connection pool...")
    await async_engine.dispose()
    logger.info("Database pool closed. Shutdown complete.")


def create_application() -> FastAPI:
    """Application factory constructing the configured FastAPI application instance."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Enterprise AI Support Quality, Verification, and Reliability Platform",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
        openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
        lifespan=lifespan,
    )

    # 1. Transport Middleware: Request Correlation Tracking
    app.add_middleware(CorrelationIdMiddleware)

    # 2. Security Middleware: Cross-Origin Resource Sharing (CORS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
    )

    # 3. Global Exception Handlers
    register_error_handlers(app)

    # 4. Root Probes (Standard Container Orchestration endpoints)
    app.include_router(root_health_router)

    # 5. Versioned API Subsystems
    app.include_router(api_router)

    return app


app = create_application()
