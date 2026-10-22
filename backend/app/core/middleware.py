"""HTTP transport middleware for correlation tracking, timing, and security headers."""

import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import correlation_id_ctx, get_logger

logger = get_logger("supportgpt.middleware")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware that injects or propagates a request correlation ID (X-Request-ID)."""

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract incoming header or generate new UUID4
        incoming_id = request.headers.get(self.header_name)
        correlation_id = incoming_id if incoming_id else str(uuid.uuid4())

        # Set ContextVar for structured logging
        token = correlation_id_ctx.set(correlation_id)

        start_time = time.perf_counter()
        try:
            response: Response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Attach headers to response
            response.headers[self.header_name] = correlation_id
            response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
            return response
        finally:
            correlation_id_ctx.reset(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that injects production-grade HTTP security headers on all responses."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response: Response = await call_next(request)

        # Standard defense-in-depth security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; frame-ancestors 'none'; object-src 'none';"
        )

        from app.core.config import settings

        if settings.ENVIRONMENT in ("production", "staging") or request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        return response
