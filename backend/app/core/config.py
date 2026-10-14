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

    # Vector Storage
    QDRANT_HOST: str = Field(default="localhost", description="Qdrant vector engine host")
    QDRANT_PORT: int = Field(default=6333, description="Qdrant HTTP port")
    QDRANT_API_KEY: str | None = Field(default=None, description="Optional Qdrant API key")

    # AI Provider Abstraction Defaults
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

            # 3. CORS origins must not allow wildcard in production
            if "*" in self.CORS_ORIGINS:
                raise ValueError("Wildcard '*' CORS origin is forbidden in production.")

            # 4. Session secret key must be custom and secure in production
            if "dev_session_secret_key" in self.SESSION_SECRET_KEY:
                raise ValueError(
                    "SESSION_SECRET_KEY uses default development secret which is forbidden in production."
                )
            if len(self.SESSION_SECRET_KEY) < 32:
                raise ValueError("SESSION_SECRET_KEY must be at least 32 characters in production.")

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
