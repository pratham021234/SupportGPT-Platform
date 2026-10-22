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


class AuthenticationException(AppException):
    def __init__(self, message: str = "Authentication required or invalid credentials.") -> None:
        super().__init__(
            message=message,
            code="AUTHENTICATION_FAILED",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class ForbiddenException(AppException):
    def __init__(
        self, message: str = "Operation not permitted for the current identity or role."
    ) -> None:
        super().__init__(
            message=message,
            code="PERMISSION_DENIED",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class ConflictException(AppException):
    def __init__(self, message: str, code: str = "RESOURCE_CONFLICT") -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_409_CONFLICT,
        )


class RateLimitExceededException(AppException):
    def __init__(self, message: str = "Too many requests. Please wait before retrying.") -> None:
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class SignatureVerificationException(AppException):
    def __init__(self, message: str = "Invalid or missing webhook signature.") -> None:
        super().__init__(
            message=message,
            code="SIGNATURE_VERIFICATION_FAILED",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class PayloadSizeLimitException(AppException):
    def __init__(self, message: str = "Inbound payload exceeds maximum allowed size.") -> None:
        super().__init__(
            message=message,
            code="PAYLOAD_TOO_LARGE",
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        )


class InvalidContentTypeException(AppException):
    def __init__(self, message: str = "Unsupported or invalid request content-type.") -> None:
        super().__init__(
            message=message,
            code="UNSUPPORTED_MEDIA_TYPE",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )


class EventReplayWindowException(AppException):
    def __init__(
        self, message: str = "Webhook timestamp is outside acceptable clock skew tolerance window."
    ) -> None:
        super().__init__(
            message=message,
            code="TIMESTAMP_OUTSIDE_TOLERANCE",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class EventNormalizationException(AppException):
    def __init__(
        self, message: str = "Failed to normalize provider event into canonical schema."
    ) -> None:
        super().__init__(
            message=message,
            code="EVENT_NORMALIZATION_FAILED",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


class UnsupportedMediaTypeException(AppException):
    def __init__(self, message: str = "Unsupported file media type.") -> None:
        super().__init__(
            message=message,
            code="UNSUPPORTED_MEDIA_TYPE",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )


class DocumentExtractionException(AppException):
    def __init__(self, message: str = "Failed to extract text from document content.") -> None:
        super().__init__(
            message=message,
            code="DOCUMENT_EXTRACTION_FAILED",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


class DocumentProcessingException(AppException):
    def __init__(
        self, message: str = "Error encountered during document processing pipeline."
    ) -> None:
        super().__init__(
            message=message,
            code="DOCUMENT_PROCESSING_FAILED",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


class StorageException(AppException):
    def __init__(self, message: str = "Object storage operation failed.") -> None:
        super().__init__(
            message=message,
            code="STORAGE_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class PathTraversalException(AppException):
    def __init__(self, message: str = "Illegal storage key path traversal attempted.") -> None:
        super().__init__(
            message=message,
            code="SECURITY_VIOLATION",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class EmbeddingGenerationException(AppException):
    def __init__(self, message: str = "Vector embedding generation failed.") -> None:
        super().__init__(
            message=message,
            code="EMBEDDING_GENERATION_FAILED",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


class VectorStoreUnavailableException(AppException):
    def __init__(self, message: str = "Vector database service is unavailable.") -> None:
        super().__init__(
            message=message,
            code="VECTOR_STORE_UNAVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class VectorDimensionMismatchException(AppException):
    def __init__(
        self, message: str = "Embedding dimension does not match collection configuration."
    ) -> None:
        super().__init__(
            message=message,
            code="VECTOR_DIMENSION_MISMATCH",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class VectorIndexingException(AppException):
    def __init__(self, message: str = "Vector indexing operation failed.") -> None:
        super().__init__(
            message=message,
            code="VECTOR_INDEXING_FAILED",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class InvalidRetrievalQueryException(AppException):
    def __init__(self, message: str = "Retrieval query is invalid or exceeds limits.") -> None:
        super().__init__(
            message=message,
            code="INVALID_RETRIEVAL_QUERY",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class LLMGenerationException(AppException):
    def __init__(self, message: str = "Grounded answer generation failed.") -> None:
        super().__init__(
            message=message,
            code="LLM_GENERATION_FAILED",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


# Phase 07: Response Verification & Approval Exceptions


class SelfApprovalForbiddenException(AppException):
    def __init__(
        self,
        message: str = "Self-approval is forbidden. An independent reviewer must approve this draft under separation-of-duties policy.",
    ) -> None:
        super().__init__(
            message=message,
            code="SELF_APPROVAL_FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class StaleDraftApprovalException(AppException):
    def __init__(
        self,
        message: str = "The draft has been modified since this approval request was created. Decision must target the active version.",
    ) -> None:
        super().__init__(
            message=message,
            code="STALE_DRAFT_VERSION",
            status_code=status.HTTP_409_CONFLICT,
        )


class ApprovalNotFoundException(AppException):
    def __init__(self, approval_id: Any) -> None:
        super().__init__(
            message=f"Approval request '{approval_id}' was not found in this organization.",
            code="APPROVAL_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidApprovalStateException(AppException):
    def __init__(
        self, message: str = "Approval request is not in a decidable pending state."
    ) -> None:
        super().__init__(
            message=message,
            code="INVALID_APPROVAL_STATE",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class DraftNotFoundException(AppException):
    def __init__(self, draft_id: Any) -> None:
        super().__init__(
            message=f"Response draft '{draft_id}' was not found in this organization.",
            code="DRAFT_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class PolicyNotFoundException(AppException):
    def __init__(self, policy_id: Any) -> None:
        super().__init__(
            message=f"Policy rule '{policy_id}' was not found in this organization.",
            code="POLICY_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class TraceNotFoundException(AppException):
    def __init__(self, trace_id: str) -> None:
        super().__init__(
            message=f"Execution trace '{trace_id}' was not found in this organization.",
            code="TRACE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvestigationNotFoundException(AppException):
    def __init__(self, investigation_id: str) -> None:
        super().__init__(
            message=f"Failure investigation '{investigation_id}' was not found in this organization.",
            code="INVESTIGATION_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class EvaluationRunNotFoundException(AppException):
    def __init__(self, run_id: str) -> None:
        super().__init__(
            message=f"Evaluation benchmark run '{run_id}' was not found in this organization.",
            code="EVALUATION_RUN_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
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
