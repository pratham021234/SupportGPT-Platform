# Stage 1: Build & dependency resolution
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install .

# Stage 2: Hardened, non-root production runtime
FROM python:3.11-slim-bookworm AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    WORKERS=2

# Install runtime system libraries (libpq for asyncpg/psycopg, curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Create non-root application user and group
RUN groupadd --system --gid 10001 appgroup && \
    useradd --system --uid 10001 --gid appgroup --shell /sbin/nologin --home-dir /app appuser

# Copy application source code
COPY --chown=appuser:appgroup alembic alembic
COPY --chown=appuser:appgroup alembic.ini .
COPY --chown=appuser:appgroup pyproject.toml .
COPY --chown=appuser:appgroup app app
COPY --chown=appuser:appgroup scripts scripts

# Create and set permissions on data directories
RUN mkdir -p /app/storage_data /app/backups && \
    chown -R appuser:appgroup /app/storage_data /app/backups

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS} --proxy-headers --forwarded-allow-ips='*'"]
