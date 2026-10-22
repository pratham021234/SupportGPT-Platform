"""SupportGPT AI — FastAPI Core Application Entrypoint.

Configures lifespan lifecycle, structured logging, middleware pipeline,
RFC 7807 error handlers, and route hierarchy.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.v1.health import router as root_health_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.logging import get_logger, setup_logging
from app.core.middleware import CorrelationIdMiddleware, SecurityHeadersMiddleware
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

    worker_task = None
    worker = None
    if settings.ENABLE_INGESTION_WORKER and settings.ENVIRONMENT != "test":
        from app.services.ingestion_worker import get_default_worker

        worker = get_default_worker()
        worker_task = asyncio.create_task(worker.start())
        logger.info(f"IngestionWorker [{worker.worker_id}] background task started.")

    doc_worker_task = None
    doc_worker_stop = None
    if settings.ENABLE_DOCUMENT_WORKER and settings.ENVIRONMENT != "test":
        from app.db.session import async_session_factory
        from app.services.document_worker import DocumentWorker

        doc_worker = DocumentWorker(session_factory=async_session_factory)
        doc_worker_stop = asyncio.Event()
        doc_worker_task = asyncio.create_task(
            doc_worker.run_worker_loop(
                doc_worker_stop,
                poll_interval=settings.DOCUMENT_PROCESSING_POLL_INTERVAL_SECONDS,
            )
        )
        logger.info(f"DocumentWorker [{doc_worker.worker_id}] background task started.")

    yield

    # Teardown sequence
    if doc_worker_stop and doc_worker_task:
        logger.info("Stopping DocumentWorker...")
        doc_worker_stop.set()
        try:
            await asyncio.wait_for(doc_worker_task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
        logger.info("DocumentWorker stopped.")

    if worker and worker_task:
        logger.info(f"Stopping IngestionWorker [{worker.worker_id}]...")
        worker.stop()
        try:
            await asyncio.wait_for(worker_task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
        logger.info("IngestionWorker stopped.")

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

    # 2. Defense-in-Depth Security Headers
    app.add_middleware(SecurityHeadersMiddleware)

    # 3. Security Middleware: Cross-Origin Resource Sharing (CORS)
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
