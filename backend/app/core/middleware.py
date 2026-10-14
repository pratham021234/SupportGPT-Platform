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
