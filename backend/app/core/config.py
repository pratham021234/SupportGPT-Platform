"""Application configuration management using Pydantic v2 Settings.

Enforces strict validation, environment variable mapping, and secure defaults.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Authoritative platform settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # General Platform Identity & Environment
    ENVIRONMENT: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        description="Runtime environment for the application",
    )
    APP_NAME: str = Field(
        default="SupportGPT-AI",
        description="Public platform identifier",
    )
    APP_VERSION: str = Field(
        default="0.1.0",
        description="Platform semantic version",
    )
    DEBUG: bool = Field(
        default=False,
        description="Debug mode. Must remain False in staging and production.",
    )
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Active logging verbosity level",
    )

    # Transport / HTTP Network Binding
    HOST: str = Field(default="0.0.0.0", description="Host address to bind HTTP listener")
    PORT: int = Field(default=8000, description="Port number to bind HTTP listener")
    API_V1_PREFIX: str = Field(default="/api/v1", description="URL path prefix for API v1")
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="List of allowed CORS origins",
    )

    # Authentication & Session Lifecycle Configuration
    SESSION_SECRET_KEY: str = Field(
        default="dev_session_secret_key_change_in_production_min_32_bytes_len",
        description="Secret key for signing session tokens and cookies",
    )
    SESSION_COOKIE_NAME: str = Field(
        default="supportgpt_session",
        description="Cookie name for browser session tokens",
    )
    SESSION_COOKIE_SECURE: bool = Field(
        default=False,
        description="Whether to require HTTPS for session cookies",
    )
    SESSION_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = Field(
        default="lax",
        description="SameSite policy for session cookies",
    )
    SESSION_COOKIE_HTTPONLY: bool = Field(
        default=True,
        description="Enforce HttpOnly flag on session cookies",
    )
    SESSION_DURATION_SECONDS: int = Field(
        default=604800,
        description="Session lifespan in seconds (default: 7 days)",
    )
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS: int = Field(
        default=5,
        description="Max failed login attempts per window",
    )
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=60,
        description="Rate limit evaluation window in seconds",
    )

    # Relational Database Configuration
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://supportgpt_user:supportgpt_dev_password@localhost:5432/supportgpt_db",
        description="Asynchronous PostgreSQL connection URL",
    )
    DB_POOL_SIZE: int = Field(default=10, description="Database connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=20, description="Database connection pool overflow")
    DB_POOL_TIMEOUT: int = Field(default=30, description="Database pool checkout timeout (seconds)")

    # Cache & Asynchronous Broker
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for caching and future task orchestration",
    )

    # Ingestion & Webhook Subsystem Configuration
    INGESTION_WEBHOOK_MAX_PAYLOAD_BYTES: int = Field(
        default=1_048_576,
        description="Max allowed bytes for inbound webhook payload (default: 1MB)",
    )
    INGESTION_TIMESTAMP_TOLERANCE_SECONDS: int = Field(
        default=300,
        description="Max acceptable clock skew/replay window for webhooks in seconds (default: 5 min)",
    )
    INGESTION_LEASE_TIMEOUT_SECONDS: int = Field(
        default=300,
        description="Worker lease timeout in seconds before hung processing jobs can be reclaimed",
    )
    INGESTION_MAX_ATTEMPTS: int = Field(
        default=5,
        description="Max worker processing retry attempts before transitioning to dead_letter",
    )
    INGESTION_WORKER_POLL_INTERVAL_SECONDS: float = Field(
        default=2.0,
        description="Worker loop polling interval in seconds",
    )
    INGESTION_WORKER_BATCH_SIZE: int = Field(
        default=20,
        description="Max jobs claimed per worker batch",
    )
    ENABLE_INGESTION_WORKER: bool = Field(
        default=True,
        description="Enable automatic background worker execution on application startup",
    )
    WEBHOOK_SECRETS_ENCRYPTION_KEY: str | None = Field(
        default=None,
        description="Optional master key for encrypting provider webhook secrets at rest",
    )

    # Storage & Document Processing Subsystem Configuration
    STORAGE_BACKEND: Literal["local", "s3"] = Field(
        default="local",
        description="Active binary object storage adapter backend",
    )
    LOCAL_STORAGE_DIR: str = Field(
        default="storage_data",
        description="Filesystem directory root for local object storage backend",
    )
    MAX_DOCUMENT_UPLOAD_BYTES: int = Field(
        default=20_971_520,
        description="Max allowed bytes for document uploads (default: 20MB)",
    )
    DOCUMENT_PROCESSING_BATCH_SIZE: int = Field(
        default=10,
        description="Max document versions claimed per background worker cycle",
    )
    DOCUMENT_PROCESSING_LEASE_TIMEOUT_SECONDS: int = Field(
        default=300,
        description="Document processing worker lease timeout in seconds before reclamation",
    )
    DOCUMENT_PROCESSING_MAX_ATTEMPTS: int = Field(
        default=3,
        description="Max worker processing retry attempts before marking document version failed",
    )
    DEFAULT_CHUNK_SIZE_CHARS: int = Field(
        default=1000,
        description="Target maximum character count per text chunk",
    )
    DEFAULT_CHUNK_OVERLAP_CHARS: int = Field(
        default=150,
        description="Target character overlap between sequential chunks",
    )
    ENABLE_DOCUMENT_WORKER: bool = Field(
        default=True,
        description="Enable automatic document processing background worker on startup",
    )
    DOCUMENT_PROCESSING_POLL_INTERVAL_SECONDS: float = Field(
        default=2.0,
        description="Document background worker poll interval in seconds",
    )

    # Vector Storage (Qdrant)
    QDRANT_HOST: str = Field(default="localhost", description="Qdrant vector engine host")
    QDRANT_PORT: int = Field(default=6333, description="Qdrant HTTP port")
    QDRANT_API_KEY: str | None = Field(default=None, description="Optional Qdrant API key")
    QDRANT_COLLECTION_NAME: str = Field(
        default="supportgpt_knowledge_chunks",
        description="Qdrant collection name for knowledge chunks",
    )
    QDRANT_LOCATION: str | None = Field(
        default=None,
        description="Explicit Qdrant location, e.g. ':memory:' or file path. If None, connects to QDRANT_HOST:QDRANT_PORT",
    )
    QDRANT_PATH: str | None = Field(
        default=None,
        description="Local on-disk storage directory for Qdrant embedded mode",
    )
    QDRANT_TIMEOUT_SECONDS: float = Field(
        default=10.0,
        description="Qdrant network request timeout in seconds",
    )

    # Embedding Provider Configuration
    EMBEDDING_PROVIDER: str = Field(
        default="fastembed",
        description="Embedding provider abstraction: 'fastembed', 'openai', or 'custom'",
    )
    EMBEDDING_MODEL_NAME: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="Embedding model identifier",
    )
    EMBEDDING_DIMENSIONS: int = Field(
        default=384,
        description="Embedding vector dimensions",
    )
    EMBEDDING_BATCH_SIZE: int = Field(
        default=32,
        description="Max batch size for vector generation",
    )
    EMBEDDING_API_KEY: str | None = Field(
        default=None,
        description="API key for external embedding provider (OpenAI, etc.)",
    )
    EMBEDDING_ENDPOINT: str | None = Field(
        default=None,
        description="Custom base URL for embedding provider API",
    )

    # Retrieval Configuration
    RETRIEVAL_TOP_K_DEFAULT: int = Field(
        default=5,
        description="Default number of evidence items retrieved",
    )
    RETRIEVAL_TOP_K_MAX: int = Field(
        default=20,
        description="Maximum number of evidence items retrieved",
    )
    RETRIEVAL_SIMILARITY_THRESHOLD: float = Field(
        default=0.45,
        description="Minimum cosine similarity threshold for retrieved evidence",
    )
    RETRIEVAL_ENABLE_HYBRID: bool = Field(
        default=True,
        description="Enable hybrid vector + PostgreSQL full-text retrieval",
    )
    RETRIEVAL_RRF_K: int = Field(
        default=60,
        description="Reciprocal Rank Fusion smoothing parameter",
    )

    # AI Provider & Grounded Answering Defaults
    AI_DEFAULT_PROVIDER: str = Field(
        default="anthropic",
        description="Default AI model provider abstraction",
    )
    AI_MODEL_NAME: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Default model identifier",
    )
    AI_TEMPERATURE: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Default generation temperature",
    )
    LLM_PROVIDER: str = Field(
        default="local_grounded",
        description="LLM provider for grounded answering: 'local_grounded', 'anthropic', 'openai'",
    )
    LLM_API_KEY: str | None = Field(
        default=None,
        description="API key for remote LLM provider",
    )
    LLM_MAX_CONTEXT_TOKENS: int = Field(
        default=4000,
        description="Maximum token budget for retrieved evidence context",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        """Parse CORS origins from JSON string or comma-separated list if provided as string."""
        if isinstance(value, str):
            val = value.strip()
            if val.startswith("[") and val.endswith("]"):
                import json

                try:
                    return json.loads(val)
                except Exception:
                    pass
            return [origin.strip() for origin in val.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_invariants(self) -> "Settings":
        """Enforce strict production safety invariants."""
        if self.ENVIRONMENT in ("staging", "production"):
            # 1. Debug mode must never be enabled in staging/production
            if self.DEBUG:
                raise ValueError(f"DEBUG mode must be False in '{self.ENVIRONMENT}' environment.")

            # 2. Database URL must not use default local development credentials in production
            if "supportgpt_dev_password" in self.DATABASE_URL:
                raise ValueError(
                    "DATABASE_URL uses default development credentials which are forbidden in production."
                )
            if "postgres:postgres@" in self.DATABASE_URL or "admin:admin@" in self.DATABASE_URL:
                raise ValueError(
                    "DATABASE_URL uses weak default credentials ('postgres:postgres' or 'admin:admin') which are forbidden in production."
                )

            # 3. CORS origins must not allow wildcard or localhost in production
            if "*" in self.CORS_ORIGINS:
                raise ValueError("Wildcard '*' CORS origin is forbidden in production.")
            if self.ENVIRONMENT == "production":
                for origin in self.CORS_ORIGINS:
                    if "localhost" in origin or "127.0.0.1" in origin:
                        raise ValueError(
                            f"Localhost CORS origin '{origin}' is forbidden in production."
                        )

            # 4. Session secret key must be custom and secure in production
            if "dev_session_secret_key" in self.SESSION_SECRET_KEY:
                raise ValueError(
                    "SESSION_SECRET_KEY uses default development secret which is forbidden in production."
                )
            if len(self.SESSION_SECRET_KEY) < 32:
                raise ValueError("SESSION_SECRET_KEY must be at least 32 characters in production.")

            # 5. HTTPS session cookies required in production
            if self.ENVIRONMENT == "production" and not self.SESSION_COOKIE_SECURE:
                raise ValueError(
                    "SESSION_COOKIE_SECURE must be True in production to ensure cookies are transmitted exclusively over TLS."
                )

            # 6. Webhook secrets encryption key required in production
            if self.ENVIRONMENT == "production":
                if not self.WEBHOOK_SECRETS_ENCRYPTION_KEY:
                    raise ValueError(
                        "WEBHOOK_SECRETS_ENCRYPTION_KEY must be configured in production for encrypting source credentials at rest."
                    )
                if len(self.WEBHOOK_SECRETS_ENCRYPTION_KEY) < 32:
                    raise ValueError(
                        "WEBHOOK_SECRETS_ENCRYPTION_KEY must be at least 32 characters long in production."
                    )

            # 7. External LLM API key validation in production
            if self.ENVIRONMENT == "production" and self.LLM_PROVIDER in ("openai", "anthropic"):
                if not self.LLM_API_KEY:
                    raise ValueError(
                        f"LLM_API_KEY must be set in production when LLM_PROVIDER is configured to '{self.LLM_PROVIDER}'."
                    )

        return self

    @property
    def async_database_url(self) -> str:
        """Ensure the database URL specifies the asyncpg dialect for SQLAlchemy."""
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Provide cached, singleton access to application settings."""
    return Settings()


# Singleton instance for direct access across modules
settings = get_settings()
