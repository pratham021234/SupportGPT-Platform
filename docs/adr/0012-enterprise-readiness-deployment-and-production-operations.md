# ADR 0012: Enterprise Readiness, Deployment Architecture, and Production Operations

## Status
Accepted

## Context
In Phases 00 through 08, SupportGPT implemented multi-tenant core services:
- Customer knowledge management, document extraction, and hierarchical structural chunking.
- Dense semantic vector retrieval with Qdrant and fast local embeddings (FastEmbed).
- Evidence-grounded generation, atomic claim extraction, deterministic policy evaluation, and dual-role human approvals.
- High-fidelity observability, failure investigations (`INV-XXXXXX`), benchmark evaluations, and log redaction.

To transition SupportGPT from an active codebase into an enterprise-ready, operatable SaaS platform, Phase 09 addressed deployment hardening:
1. **Container Security & Reproducibility:** How do we containerize FastAPI and Next.js 15 without running as root, embedding local build artifacts, or leaking build-time secrets?
2. **Multi-Replica Migration Coordination:** How do we prevent concurrent application replicas from racing through Alembic database migrations during zero-downtime rolling deployments?
3. **Dedicated Background Processing:** How do we decouple long-running ingestion and document workers from user-facing HTTP request threads while guaranteeing graceful shutdown on `SIGTERM` / `SIGINT`?
4. **Disaster Recovery & Vector Reconstruction:** How do we automate verified database backups and reconstruct lost vector indices without treating Qdrant as an unbacked authoritative source?
5. **Runtime Security Invariants & Rate Limiting:** How do we ensure weak development passwords, insecure cookie flags, and wildcard CORS origins cannot silently run in staging or production?
6. **Network Boundaries:** How do we isolate the database, cache, and vector store from public network exposure?

---

## Decision

We implemented a repeatable, defense-in-depth deployment architecture spanning:
1. Standalone containerization (`backend/Dockerfile`, `frontend/Dockerfile`, `nginx/Dockerfile`).
2. Advisory lock-coordinated migrations (`backend/scripts/run_migrations.py`).
3. Dedicated worker runner with OS signal lifecycle handling (`backend/app/worker_runner.py`).
4. Cryptographically-verified disaster recovery (`backend/scripts/backup_database.py`, `restore_database.py`, `reindex_vectors.py`).
5. Production configuration validation, sliding-window rate limiting, and HTTP security headers.
6. Segmented Docker Compose topology (`docker-compose.prod.yml`) and reverse proxy (`nginx/nginx.conf`).

---

### 1. Multi-Stage Containerization & Non-Root User Execution

Both frontend and backend container builds use multi-stage compilation to minimize attack surfaces and image sizes:
- **Backend (`backend/Dockerfile`):**
  - **Builder Stage:** Uses `python:3.11-slim-bookworm` with compilation tools (`build-essential`, `libpq-dev`) to resolve and build wheels into `/install`.
  - **Runner Stage:** Copies pre-built wheels into a clean slim image with only runtime shared libraries (`libpq5`, `curl`).
  - **Non-Root User:** Runs under system user `appuser` (UID 10001, GID 10001) with restricted permissions.
  - **ASGI Tuning:** Configured for multi-worker production execution:
    `uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS} --proxy-headers --forwarded-allow-ips='*'`
  - **Health Probing:** Container-level `HEALTHCHECK` querying `curl -f http://localhost:8000/health`.
- **Frontend (`frontend/Dockerfile`):**
  - Next.js 15 standalone output traces (`output: "standalone"`).
  - Unprivileged user `nextjs` (UID 1001, GID 1001).
  - Built-in zero-dependency health check endpoint (`/api/health`).

---

### 2. Coordinated Migration Architecture (`run_migrations.py`)

In multi-container or Kubernetes rolling deployments, starting multiple API replicas simultaneously can cause concurrent migration races, leading to lock contention, duplicate index failures, or corrupted migration state.

**Solution:**
We introduced `backend/scripts/run_migrations.py`, which coordinates migration execution using PostgreSQL Session-Level Advisory Locks:
```python
# PostgreSQL 64-bit advisory lock key for SupportGPT migrations
MIGRATION_ADVISORY_LOCK_ID = 847291038

async def run_coordinated_migrations(target_revision: str = "head") -> None:
    # 1. Connect to PostgreSQL
    # 2. SELECT pg_advisory_lock(847291038)
    # 3. Execute alembic.command.upgrade(config, target_revision)
    # 4. SELECT pg_advisory_unlock(847291038) in finally block
```
In `docker-compose.prod.yml`, migrations run in a standalone, dedicated `migration` container that completes with code 0 before either the API or the worker containers are launched (`condition: service_completed_successfully`).

---

### 3. Dedicated Background Worker Runner (`worker_runner.py`)

To eliminate thread contention and event loop starvation in user-facing web servers:
- API containers disable in-process background worker loops (`ENABLE_INGESTION_WORKER=false`, `ENABLE_DOCUMENT_WORKER=false`).
- A dedicated `worker` service executes `app.worker_runner`.
- **Signal Handling:** Listens for `SIGTERM` and `SIGINT`. On receipt:
  1. Triggers cancellation flags (`worker.stop()` and `asyncio.Event`).
  2. Awaits running tasks up to a graceful timeout (30 seconds).
  3. Closes database connection pools cleanly (`await async_engine.dispose()`).
  4. Exits with code 0 without dropping in-flight database transactions.

---

### 4. Cryptographic Disaster Recovery & Vector Re-Indexing

PostgreSQL is the single authoritative source of truth for all customer records, documents, versions, and chunk text.
1. **Database Backups (`backup_database.py`):**
   - Invokes `pg_dump` with custom compressed format (`-F c`).
   - Computes SHA-256 integrity hash and writes alongside backup (`.dump.sha256`).
   - Writes structured JSON metadata receipt (`.dump.meta.json`) recording database name, timestamp, file size, checksum, and environment.
   - Enforces configurable retention pruning (default: 14 days).
2. **Database Restoration (`restore_database.py`):**
   - Recalculates SHA-256 hash of the target dump and verifies exact match against the `.sha256` digest prior to launching `pg_restore`.
   - Rejects corrupted, tampered, or partial backup files immediately (`ValueError`).
3. **Qdrant Vector Recovery (`reindex_vectors.py`):**
   - If Qdrant collections are wiped, corrupted, or re-initialized with new dimensions, this utility queries authoritative PostgreSQL `document_chunks` for active indexed versions.
   - Re-embeds content using the active embedding provider and upserts verified points into Qdrant in deterministic batches.

---

### 5. Production Configuration Invariants, Rate Limiting & Security Headers

1. **Deterministic Production Invariants (`Settings.validate_production_invariants`):**
   - `DEBUG=False` strictly enforced in staging and production.
   - Default credentials (`supportgpt_dev_password`, `postgres:postgres`, `admin:admin`) rejected at startup.
   - `SESSION_COOKIE_SECURE=True` required for TLS-only session cookies.
   - `SESSION_SECRET_KEY` must be non-default and >= 32 characters.
   - Wildcard `*` and `localhost` CORS origins rejected in production.
   - `WEBHOOK_SECRETS_ENCRYPTION_KEY` strictly required (>= 32 chars).
   - `LLM_API_KEY` validated if external LLM provider (`openai`, `anthropic`) is active.
2. **Brute-Force Rate Limiting (`InMemoryRateLimiter`):**
   - Sliding-window tracking of failed login attempts per client IP / key.
   - Enforces HTTP 429 (`RATE_LIMIT_EXCEEDED`) with dynamic `retry_after_seconds` once thresholds are exceeded (default: 5 attempts per 60 seconds).
   - Automatically resets counters upon valid credential verification.
3. **Security Headers (`SecurityHeadersMiddleware`):**
   - Injects `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Content-Security-Policy` into all HTTP responses.

---

### 6. Network Segmentation & Ingress Topology

In `docker-compose.prod.yml`:
- **`supportgpt-internal` network (`internal: true`):** Contains `postgres`, `redis`, `qdrant`, `migration`, `backend`, and `worker`. It has no external port bindings, isolating data stores from direct internet exposure.
- **`supportgpt-edge` network:** Connects only `nginx` to the public port 80/443.
- **Nginx Reverse Proxy:** Terminates HTTP/TLS, buffers client uploads (up to 25MB), routes `/api/` to `backend:8000`, routes `/` to `frontend:3000`, and enforces standard upstream connection pooling.

---

## Consequences

### Positive
- Zero risk of multi-replica migration races during deployments.
- Non-root container privileges comply with SOC 2 / ISO 27001 least-privilege standards.
- In-flight background workers shut down cleanly without leaving unreleased document leases.
- Authoritative disaster recovery guarantees Qdrant vectors can always be reconstructed from PostgreSQL.
- Insecure configurations fail fast at boot before serving client traffic.

### Trade-offs & Operational Requirements
- Database backup scripts require a database user with `BYPASSRLS` privileges (e.g. `supportgpt_backup`) or superuser access to dump tables with `FORCE ROW LEVEL SECURITY`.
- Redis currently runs with password authentication and append-only persistence; for multi-node high availability, Redis Sentinel or managed cloud caching is recommended in future phases.
- Rate limiting is currently in-memory per container replica; multi-region deployments should back rate limiting with Redis sliding-window keys.
