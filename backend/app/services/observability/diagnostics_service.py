"""System Diagnostics Service for deep health checks and dependency monitoring."""

import time
from typing import Any

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import verify_database_connection
from app.services.rag.embedding import get_embedding_provider
from app.services.rag.qdrant_store import QdrantStoreManager

logger = get_logger("supportgpt.observability.diagnostics")


class DiagnosticsService:
    """Probes deep system dependencies without calling paid external LLMs."""

    @staticmethod
    async def get_system_diagnostics() -> dict[str, Any]:
        """Perform comprehensive readiness probe across all platform infrastructure."""
        results: dict[str, Any] = {
            "environment": settings.ENVIRONMENT,
            "version": settings.APP_VERSION,
            "timestamp": time.time(),
            "status": "healthy",
            "dependencies": {},
            "workers": {},
            "ai_providers": {},
        }

        # 1. Database Probe
        db_ok, db_lat, db_err = await verify_database_connection(timeout_seconds=2.0)
        results["dependencies"]["database"] = {
            "status": "up" if db_ok else "down",
            "latency_ms": db_lat,
            "error": db_err,
        }
        if not db_ok:
            results["status"] = "degraded"

        # 2. Redis Probe
        redis_start = time.perf_counter()
        try:
            redis_client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2.0)
            await redis_client.ping()
            await redis_client.aclose()
            redis_lat = round((time.perf_counter() - redis_start) * 1000, 2)
            results["dependencies"]["redis"] = {
                "status": "up",
                "latency_ms": redis_lat,
                "error": None,
            }
        except Exception as exc:
            redis_lat = round((time.perf_counter() - redis_start) * 1000, 2)
            results["dependencies"]["redis"] = {
                "status": "degraded",
                "latency_ms": redis_lat,
                "error": str(exc),
            }

        # 3. Qdrant Vector Store Probe
        qdrant_start = time.perf_counter()
        try:
            qdrant_mgr = QdrantStoreManager()
            collections = qdrant_mgr.client.get_collections()
            qdrant_lat = round((time.perf_counter() - qdrant_start) * 1000, 2)
            collection_names = [c.name for c in collections.collections]
            results["dependencies"]["qdrant"] = {
                "status": "up",
                "latency_ms": qdrant_lat,
                "collections_count": len(collection_names),
                "collections": collection_names,
                "error": None,
            }
        except Exception as exc:
            qdrant_lat = round((time.perf_counter() - qdrant_start) * 1000, 2)
            results["dependencies"]["qdrant"] = {
                "status": "degraded",
                "latency_ms": qdrant_lat,
                "error": str(exc),
            }

        # 4. Background Workers Configuration
        results["workers"]["ingestion_worker"] = {
            "enabled": settings.ENABLE_INGESTION_WORKER,
            "poll_interval_seconds": settings.INGESTION_WORKER_POLL_INTERVAL_SECONDS,
            "batch_size": settings.INGESTION_WORKER_BATCH_SIZE,
        }
        results["workers"]["document_worker"] = {
            "enabled": settings.ENABLE_DOCUMENT_WORKER,
            "poll_interval_seconds": settings.DOCUMENT_PROCESSING_POLL_INTERVAL_SECONDS,
            "batch_size": settings.DOCUMENT_PROCESSING_BATCH_SIZE,
        }

        # 5. Embedding Provider Diagnostics
        embed_start = time.perf_counter()
        try:
            provider = get_embedding_provider()
            embed_lat = round((time.perf_counter() - embed_start) * 1000, 2)
            results["ai_providers"]["embedding"] = {
                "provider": provider.provider_name,
                "model": provider.model_name,
                "dimensions": provider.dimensions,
                "status": "ready",
                "initialization_latency_ms": embed_lat,
            }
        except Exception as exc:
            results["ai_providers"]["embedding"] = {
                "provider": settings.EMBEDDING_PROVIDER,
                "model": settings.EMBEDDING_MODEL_NAME,
                "status": "error",
                "error": str(exc),
            }
            results["status"] = "degraded"

        # 6. LLM Configuration (no paid call)
        results["ai_providers"]["generation"] = {
            "provider": settings.AI_DEFAULT_PROVIDER,
            "model": settings.AI_MODEL_NAME,
            "max_tokens": settings.LLM_MAX_CONTEXT_TOKENS,
            "temperature": settings.AI_TEMPERATURE,
            "verification_pipeline_version": "v1.0.0",
        }

        return results
