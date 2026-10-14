"""Custom application exceptions and global error handlers."""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import correlation_id_ctx, get_logger
from app.schemas.error import ErrorBody, ErrorDetail, ErrorResponse

logger = get_logger("supportgpt.errors")


class AppException(Exception):
    """Base domain and application exception."""

    def __init__(
        self,
        message: str,
        code: str = "APPLICATION_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: list[ErrorDetail] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or []


class ResourceNotFoundException(AppException):
    def __init__(self, resource_name: str, identifier: Any) -> None:
        super().__init__(
            message=f"{resource_name} with identifier '{identifier}' was not found.",
            code="RESOURCE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ServiceUnavailableException(AppException):
    def __init__(self, service_name: str, reason: str = "Service dependency unavailable") -> None:
        super().__init__(
            message=f"{service_name} is currently unavailable: {reason}",
            code="SERVICE_UNAVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def register_error_handlers(app: FastAPI) -> None:
    """Register uniform RFC 7807/structured error handlers with the FastAPI application."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        correlation_id = correlation_id_ctx.get()
        logger.warning(
            f"AppException [{exc.code}] on {request.method} {request.url.path}: {exc.message}"
        )
        response_body = ErrorResponse(
            error=ErrorBody(
                code=exc.code,
                message=exc.message,
                details=exc.details,
                request_id=correlation_id,
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=response_body.model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        correlation_id = correlation_id_ctx.get()
        details = []
        for error in exc.errors():
            field_path = " -> ".join(str(loc) for loc in error.get("loc", []))
            details.append(
                ErrorDetail(
                    field=field_path,
                    message=error.get("msg", "Invalid field value"),
                    code=error.get("type"),
                )
            )

        logger.info(
            f"Validation error on {request.method} {request.url.path} with {len(details)} violation(s)"
        )
        response_body = ErrorResponse(
            error=ErrorBody(
                code="VALIDATION_FAILED",
                message="Request payload failed schema validation.",
                details=details,
                request_id=correlation_id,
            )
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=response_body.model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        correlation_id = correlation_id_ctx.get()
        response_body = ErrorResponse(
            error=ErrorBody(
                code="HTTP_ERROR",
                message=str(exc.detail),
                details=[],
                request_id=correlation_id,
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=response_body.model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        correlation_id = correlation_id_ctx.get()
        # Log complete stack trace internally for engineering investigation
        logger.exception(
            f"Unhandled internal server error on {request.method} {request.url.path}: {exc}"
        )
        # Never leak internal stack trace, file path, or database details to external clients
        response_body = ErrorResponse(
            error=ErrorBody(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected internal server error occurred. Please contact platform support.",
                details=[],
                request_id=correlation_id,
            )
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_body.model_dump(),
        )
