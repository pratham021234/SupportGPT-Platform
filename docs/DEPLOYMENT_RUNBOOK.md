# SupportGPT AI Platform - Production Deployment & Operations Runbook

## 1. Scope and Target Architecture

This runbook defines the operational procedures for deploying, validating, operating, and recovering the **SupportGPT AI Support Operations Platform** in staging and production environments.

The target architecture is a **reproducible, containerized modular monolith** consisting of:
- **Edge Reverse Proxy:** Nginx 1.27 terminating TLS, enforcing request body limits (25MB), injecting HTTP security headers, and proxying `/api` to the backend and `/` to Next.js.
- **Frontend Container:** Next.js 15 standalone Node runtime executing as unprivileged user `nextjs` (UID 1001).
- **Backend API Container:** FastAPI ASGI application running under unprivileged user `appuser` (UID 10001) with multi-worker Uvicorn (`WORKERS=4`). Background workers are disabled in API replicas.
- **Background Worker Container:** Dedicated `worker_runner.py` process running Ingestion and Document workers with graceful `SIGTERM`/`SIGINT` handling and lease reclamation.
- **Migration Container:** One-off startup container executing `scripts/run_migrations.py` with PostgreSQL advisory locking.
- **Data Stores:**
  - PostgreSQL 16 with Row-Level Security (RLS) and connection pooling (SQLAlchemy + asyncpg).
  - Redis 7 with password authentication and Append-Only File (AOF) persistence.
  - Qdrant v1.12 vector search engine with Cosine distance metric.

---

## 2. Infrastructure Sizing & Prerequisites

| Component | Minimum Staging | Recommended Production | Notes |
|---|---|---|---|
| **CPU** | 4 vCPU | 8–16 vCPU | Embedding model execution & concurrent requests |
| **RAM** | 8 GB | 16–32 GB | FastEmbed ONNX models & PostgreSQL buffer pool |
| **Disk (SSD)** | 50 GB NVMe | 200+ GB NVMe | Fast I/O for PostgreSQL WAL, Qdrant indices, and storage |
| **Docker Engine** | 24.0+ | 26.0+ | Supports Compose v2 and multi-stage buildx |
| **Docker Compose**| v2.20+ | v2.26+ | Required for service completion conditions |
| **Operating System**| Ubuntu 22.04 LTS / Debian 12 | Ubuntu 24.04 LTS / Amazon Linux 2023 | Pinned, supported enterprise Linux distributions |

---

## 3. Pre-Deployment Configuration & Secret Injection

### Step 3.1: Generate Cryptographically Secure Secrets
Run on a secure workstation or secrets management orchestrator:
```bash
# Session Secret Key (AES-256 / HMAC signing, min 32 hex bytes)
openssl rand -hex 32

# Webhook Secrets Encryption Key (AES-256-GCM, min 32 hex bytes)
openssl rand -hex 32

# Strong Database Password
openssl rand -base64 24

# Redis Password
openssl rand -base64 24
```

### Step 3.2: Create the Production Environment File
Copy `.env.production.example` to `.env.production` on the production host (chmod 600):
```bash
cp .env.production.example .env.production
chmod 600 .env.production
```
Configure mandatory variables:
- `ENVIRONMENT=production`
- `DEBUG=false`
- `PUBLIC_API_URL=https://app.yourdomain.com/api`
- `CORS_ORIGINS=["https://app.yourdomain.com"]`
- `POSTGRES_USER=supportgpt_prod`
- `POSTGRES_PASSWORD=<generated_db_password>`
- `POSTGRES_DB=supportgpt_production`
- `DATABASE_URL=postgresql+asyncpg://supportgpt_prod:<generated_db_password>@postgres:5432/supportgpt_production`
- `BACKUP_DATABASE_URL=postgresql://supportgpt_backup:<backup_password>@postgres:5432/supportgpt_production`
- `REDIS_PASSWORD=<generated_redis_password>`
- `REDIS_URL=redis://:<generated_redis_password>@redis:6379/0`
- `SESSION_SECRET_KEY=<generated_session_key>`
- `SESSION_COOKIE_SECURE=true`
- `WEBHOOK_SECRETS_ENCRYPTION_KEY=<generated_webhook_key>`
- `LLM_PROVIDER=openai` (or `anthropic` or `deterministic`)
- `LLM_API_KEY=sk-proj-...`

> [!CAUTION]
> If any production invariant is violated (e.g. `DEBUG=true`, default passwords, wildcard CORS, or insecure cookie flags), the application fails to start immediately with an explicit validation error.

---

## 4. Initial Deployment Procedure

### Step 4.1: Deploy Storage Volumes and Network Topology
```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d postgres redis qdrant
```
Verify databases and stores are healthy:
```bash
docker compose -f docker-compose.prod.yml ps
```

### Step 4.2: Execute Coordinated Database Migrations
Migrations use PostgreSQL 64-bit advisory locking (`847291038`) to prevent concurrent race conditions:
```bash
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm migration
```
Output must confirm:
```
INFO  [supportgpt.migration] Migration lock 847291038 acquired. Executing Alembic upgrade to head...
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [supportgpt.migration] Alembic upgrade to 'head' completed successfully.
INFO  [supportgpt.migration] Migration lock released successfully.
```

### Step 4.3: Launch API, Background Worker, and Frontend
```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
```

### Step 4.4: Initial Administrator & Organization Provisioning
Bootstrap the initial root tenant organization and administrator account via the backend CLI tool (never commit fixed admin credentials):
```bash
docker compose -f docker-compose.prod.yml exec -it backend python scripts/bootstrap_admin.py \
  --org-name "Acme Operations" \
  --admin-email "admin@acme.com"
```
The script will prompt for a strong password interactively and hash it using Argon2id.

---

## 5. Post-Deployment Verification (Smoke Testing)

Perform the following sequential verification checks:

1. **Edge Proxy Health:**
   ```bash
   curl -i https://app.yourdomain.com/health
   # HTTP/1.1 200 OK -> {"status":"ok","app":"SupportGPT-AI","environment":"production"}
   ```
2. **Platform Readiness Probe:**
   ```bash
   curl -i https://app.yourdomain.com/readyz
   # HTTP/1.1 200 OK -> {"status":"ready","dependencies":{"database":{"status":"up"},"redis":{"status":"up"}}}
   ```
3. **Frontend Health Probe:**
   ```bash
   curl -i https://app.yourdomain.com/api/health
   # HTTP/1.1 200 OK -> {"status":"healthy","service":"supportgpt-frontend"}
   ```
4. **Security Headers Verification:**
   Inspect response headers:
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `X-XSS-Protection: 1; mode=block`
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - `Content-Security-Policy: default-src 'self' ...`
5. **Authentication & Rate Limiting Verification:**
   - Attempt login with invalid credentials 5 times -> 6th attempt must receive `429 Too Many Requests`.
   - Log in with valid credentials -> verify `Set-Cookie` contains `Secure`, `HttpOnly`, and `SameSite=Lax`.
6. **Knowledge Management Verification:**
   - Upload a test markdown file to a knowledge base.
   - Verify background worker processes version from `queued` -> `extracting` -> `chunking` -> `indexed`.
   - Search knowledge base and confirm chunks are retrieved with citation breadcrumbs.
7. **Observability Verification:**
   - Open `/observability` dashboard in the UI.
   - Verify execution trace is recorded with span breakdown and token usage.

---

## 6. Operational Procedures & Maintenance

### 6.1: Database Backup Execution
```bash
docker compose -f docker-compose.prod.yml exec -it backend \
  python scripts/backup_database.py --backup-dir /app/backups --retention-days 14
```
Verify generated artifacts:
- `/app/backups/supportgpt_db_YYYYMMDD_HHMMSS.dump` (PostgreSQL custom archive)
- `/app/backups/supportgpt_db_YYYYMMDD_HHMMSS.dump.sha256` (SHA-256 digest)
- `/app/backups/supportgpt_db_YYYYMMDD_HHMMSS.dump.meta.json` (Structured receipt)

### 6.2: Checksum-Verified Database Restoration
```bash
# Verify checksum integrity without restoring
docker compose -f docker-compose.prod.yml exec -it backend \
  python scripts/restore_database.py /app/backups/supportgpt_db_YYYYMMDD_HHMMSS.dump --verify-only

# Execute full restore into target database
docker compose -f docker-compose.prod.yml exec -it backend \
  python scripts/restore_database.py /app/backups/supportgpt_db_YYYYMMDD_HHMMSS.dump --target-db supportgpt_production
```

### 6.3: Vector Disaster Recovery & Reindexing
If Qdrant data is lost or embedding models are upgraded:
```bash
docker compose -f docker-compose.prod.yml exec -it backend \
  python scripts/reindex_vectors.py --batch-size 50
```
PostgreSQL remains the single authoritative source of truth. All chunk content and metadata are re-embedded and upserted into Qdrant automatically.

### 6.4: Worker Crash Recovery & Stale Lease Reclamation
If a worker container crashes during document processing, the job remains in `extracting` or `chunking` state.
The Ingestion and Document workers automatically reclaim leases older than `INGESTION_LEASE_TIMEOUT_SECONDS` (default: 300s):
- Reclaims hung jobs up to `INGESTION_MAX_ATTEMPTS` (default: 5 retries).
- Jobs exceeding maximum retries transition to `dead_letter` or `failed` state with failure investigations (`INV-XXXXXX`) logged for operators.

---

## 7. Incident Response & Rollback Procedures

### 7.1: Application Rollback Procedure
If a release causes regressions:
1. Re-tag or pull the previous stable container image:
   ```bash
   docker pull your-registry/supportgpt-backend:<previous_tag>
   docker pull your-registry/supportgpt-frontend:<previous_tag>
   ```
2. Check database migration compatibility:
   - If migrations are backward-compatible (expand-and-contract pattern), do not roll back the database schema.
   - If a rollback is strictly necessary and verified safe:
     ```bash
     docker compose -f docker-compose.prod.yml exec -it backend alembic downgrade -1
     ```
3. Restart containers with previous image tags:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --no-deps backend frontend worker
   ```
4. Verify `/healthz` and `/readyz` probes return HTTP 200.

### 7.2: Provider Outage Handling (OpenAI / Anthropic)
If the upstream LLM provider suffers an outage:
1. Operations continue without customer-facing hallucination because retrieval and citation validation strictly abstain if the provider is unreachable or returns malformed citations.
2. In the observability dashboard (`/observability`), check failure investigations categorized under `generation_failure` or `provider_unavailable`.
3. To switch providers, update `LLM_PROVIDER` in `.env.production` and restart the backend and worker containers:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --no-deps backend worker
   ```
