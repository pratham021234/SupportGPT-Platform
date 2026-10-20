# SupportGPT AI — Platform Foundation & Architecture

> **Enterprise AI Support Quality, Verification, Human Approvals & Reliability Platform**

SupportGPT AI is a commercial-grade, multi-tenant B2B SaaS platform engineered for customer support automation with factual grounding, claim-level response verification, policy-enforced human approvals, and forensic AI failure investigation.

---

## 1. Engineering Status: Phase 00, Phase 01, Phase 02, Phase 03, Phase 04, Phase 05, Phase 06 & Phase 07 Completed

- **Phase 00 Foundation & Standards**:
  - **Architecture**: Modular Monolith with clean domain boundaries (`api/`, `core/`, `db/`, `models/`, `schemas/`, `ai/`).
  - **Backend Transport**: Python 3.11, FastAPI, Pydantic v2 Settings with strict production validation.
  - **Frontend Shell**: Next.js (App Router), React 19, TypeScript (Strict Mode), Tailwind CSS, live system diagnostics console.
  - **Quality Gates**: Pytest automated test suite, Ruff linter, and GitHub Actions CI workflow.
  - **Honest Metrics**: Zero fabricated business counts, fake tickets, fake revenue, or simulated accuracy.
- **Phase 01 Canonical Domain Model & PostgreSQL Persistence**:
  - **Authoritative Entities**: `Organization`, `OrganizationTicketCounter`, `Customer`, `CustomerIdentity`, `Ticket`, `Conversation`, `Message`, `Attachment`, `TicketEvent`, `IngestionReceipt`.
  - **Database-Enforced Tenant Consistency**: Composite foreign keys spanning `(ticket_id, organization_id)`, `(conversation_id, organization_id)`, `(message_id, organization_id)`.
  - **Deletion Safeguards**: Strict `ON DELETE RESTRICT` on organization and customer relationships to prevent accidental data destruction.
  - **Alembic Migrations**: `0001_initial_foundation` and `0002_canonical_domain_model` with verified transactional upgrade and downgrade DDL.
- **Phase 02 Authentication, Organization Membership, RBAC & Tenant Isolation**:
  - **Secure User Accounts**: UUID-keyed `User` entity, normalized emails, Argon2id password hashing (64MB memory, 3 iterations), side-channel constant-time verification.
  - **Revocable Session Lifecycle**: Server-side `UserSession` with opaque 256-bit entropy tokens, SHA-256 token hash storage, `HttpOnly` / `SameSite=Lax` cookies, Bearer fallback, and instant logout revocation.
  - **Centralized RBAC**: 4 explicit enterprise roles (`owner`, `admin`, `agent`, `viewer`), permission matrix, least-privilege enforcement, privilege escalation blocks, and last-owner protection.
  - **Organization Context & Scoped Queries**: Request-level `OrganizationContext` resolving memberships, and `TenantScopedQuery` enforcing tenant-scoped filtering with 404 responses on cross-tenant access to prevent direct-ID existence leakage.
  - **PostgreSQL Row-Level Security (RLS)**: Active RLS with `FORCE ROW LEVEL SECURITY` across 7 tenant tables, transactional context via `SELECT set_config('app.current_organization_id', :org_id, true)`.
  - **Alembic Migration**: `0003_auth_membership_rbac` with verified upgrade and downgrade paths.
  - **Frontend Integration**: Real Next.js login interface (`/login`), typed API client with credentials, session-aware app header, and live logout.
- **Phase 03 Ticket Management, Conversation Services, Message APIs & Business Logic**:
  - **Ticket Lifecycle & Numbering**: Atomic sequential ticket allocation (`TICK-{number}`) via row-level locks on `organization_ticket_counters`.
  - **Optimistic Concurrency Control (OCC)**: Version-based locking (`lock_version` integer on `tickets`) preventing lost updates with `409 Conflict` responses.
  - **Status Transitions & Assignment**: Centralized state transition validation (`can_transition_ticket_status`) and membership eligibility checks (rejecting read-only viewers and external users).
  - **Conversation & Message Services**: Deterministic sequence ordering (`created_at ASC, sequence_number ASC, id ASC`), idempotency on `external_message_id`, and author impersonation prevention.
  - **Attachment Metadata Protection**: Metadata retrieval strictly omitting internal `storage_key` locator secrets.
  - **Append-Only Audit Trail**: Immutable `TicketEvent` history committed atomically with ticket mutations.
  - **Alembic Migration**: `0004_ticket_concurrency_version` with verified reversible upgrade and downgrade.
  - **Frontend Integration**: Real Next.js `/tickets` management console with live listing, creation, conversation inspection, status transitions, and optimistic concurrency reloading.
- **Phase 04 Reliable Event Ingestion, Webhooks, Idempotency, Background Processing & Connector Foundation**:
  - **Organization Source Configuration**: Scoped `EventSource` entity with secure secret generation, cryptographic hash indexing, preview masking, and AES-CTR encryption at rest.
  - **Inbound Webhook Verification**: Constant-time HMAC-SHA256 signature verification over raw request bytes, 300-second timestamp replay window rejection, and 1 MB payload limits.
  - **Durable Event Receipt & Deduplication**: PostgreSQL `ingestion_receipts` table acting as durable system of record with database-level uniqueness on `(organization_id, source_provider, external_event_id)` and payload digest comparison (202 Accepted on new events, 200 OK on duplicate delivery, 409 Conflict on payload mismatch).
  - **Asynchronous Background Worker**: Non-blocking `IngestionWorker` with transactional `FOR UPDATE SKIP LOCKED` job claiming, crash recovery via lease expiration reclamation, and exponential backoff with jitter on retries.
  - **Canonical Event Normalization & Domain Mapping**: Typed `CanonicalEvent` normalization and idempotent application to `Customer`, `Ticket`, `Conversation`, and `Message` models.
  - **Operational Observability & Replay**: Restricted API endpoints for receipt inspection, sanitized error summaries, worker health diagnostics, and idempotent dead-letter replay.
  - **Alembic Migration**: `0005_event_ingestion_subsystem` applied to both `supportgpt_db` and `supportgpt_test_db`.
- **Phase 05 Enterprise Knowledge Base, Document Processing, Versioning & Retrieval Foundation**:
  - **Canonical Knowledge Domain Models**: `KnowledgeBase`, `Document`, `DocumentVersion`, `DocumentChunk` with composite tenant foreign key constraints.
  - **Object Storage Subsystem**: Decoupled `StorageBackend` abstraction with `LocalStorageBackend` providing path traversal defense, opaque storage keys (`org_{org_id}/docs/{doc_id}/v{version_number}_{uuid}.bin`), atomic streaming writes, and checksum verification.
  - **Secure File Validation**: Explicit format allowlist (PDF, DOCX, TXT, Markdown), binary magic byte checking (`%PDF-`, PKZIP OpenXML), zip bomb defense (100MB uncompressed limit, 50x expansion ratio), and binary null byte rejection.
  - **Authentic Text Extractors**: `pypdf` extraction with automatic scanned/image-only PDF detection reporting `OCR_UNAVAILABLE`; `python-docx` structural extraction preserving headings and tables; and encoding-safe text/markdown extraction.
  - **Deterministic Normalization & Structural Chunking**: `TextNormalizer` and `HierarchicalStructuralChunker` generating reproducible chunks with heading hierarchy breadcrumbs, character offsets, SHA-256 chunk digests, and zero empty chunks.
  - **Prior Version Preservation & Worker Concurrency**: `DocumentWorker` executing PostgreSQL `FOR UPDATE SKIP LOCKED` claiming, crash lease recovery (300s timeout), exponential retry backoff, and version preservation (failed new versions keep prior usable versions active).
  - **Alembic Migration**: `0006_knowledge_base_subsystem` applied to both `supportgpt_db` and `supportgpt_test_db` with active PostgreSQL Row-Level Security (RLS) policies.
  - **RESTful Endpoints**: Full organization-scoped APIs for knowledge base collections, document uploads, revisions, reprocessing, soft delete, and chunk provenance with RBAC enforcement.
- **Phase 06 Evidence-Grounded Retrieval & Answering Foundation**:
  - **Real Dense Semantic Embeddings**: `EmbeddingProvider` abstraction with local ONNX `FastEmbedEmbeddingProvider` (`BAAI/bge-small-en-v1.5`, 384 dims) and `OpenAIEmbeddingProvider`. Strict dimensional checking and finite float value validation.
  - **Qdrant Vector Indexing**: `QdrantStoreManager` with deterministic UUIDv5 point identities, collection parameter drift detection, minimal payloads, and tenant isolation filters.
  - **Durable Indexing Integration**: `DocumentWorker` advances document versions to `INDEXED` only after successful vector embedding and verified Qdrant upsert. Reprocessing idempotency and deletion de-indexing.
  - **Dedicated Retrieval Service**: Query normalization, hybrid search combining dense vectors and PostgreSQL full-text search (`tsvector`), Reciprocal Rank Fusion (RRF), and authoritative PostgreSQL Row-Level Security post-verification.
  - **Dual-Layer Tenant Isolation**: Mandatory server-enforced Qdrant payload filters combined with authoritative database verification purging unauthorized, deleted, or superseded versions.
  - **Grounded Answer Generation & Anti-Injection**: Strict `<evidence>` XML boundary isolation, anti-injection system prompt directives, verified `[citation:N]` citation resolution, and automated abstention (`NO_RELEVANT_EVIDENCE`, `EVIDENCE_INSUFFICIENT`).
  - **Repeatable Evaluation Framework**: `RAGEvaluator` computing measured Recall@k, Mean Reciprocal Rank (MRR), citation validity, and abstention accuracy against an explicitly labeled dataset.
  - **Frontend Search & Grounded Q&A**: Interactive Next.js console at `/knowledge` with tenant selector, collection filtering, citation inspectors, and latency/model diagnostics.
- **Phase 07 AI Response Verification, Policy Enforcement & Human Approval**:
  - **Canonical Verification Domain Models**: `ResponseDraft`, `VerificationRun`, `ClaimFinding`, `PolicyRule`, `ApprovalRequest`, `VerificationAuditEvent` with full composite tenant isolation and PostgreSQL Row-Level Security.
  - **Granular Claim Extraction & Evidence Grounding**: Deterministic sentence and clause decomposition filtering conversational preamble, classifying claims (`policy`, `pricing_refund`, `sla_commitment`, `product_fact`, `general`), and evaluating support against retrieved knowledge chunks (`supported`, `partially_supported`, `unsupported`, `contradicted`, `not_verifiable`).
  - **Versioned Declarative Policy Engine**: Organization-scoped, schema-validated policy rules (`unsupported_claim_block`, `keyword_prohibition`, `required_phrase`, `max_length`, `refund_limit`, `mandatory_approval_on_risk`) with severity tiers and version increments.
  - **Deterministic Disposition & Risk Engine**: Computes pipeline disposition (`passed`, `passed_with_warnings`, `needs_revision`, `blocked`, `failed`) and overall risk level (`low`, `medium`, `high`, `critical`) requiring human approval when risk or policy triggers trip.
  - **Durable Human Approval Workflow**: Enforces strict server-side separation of duties (requester cannot self-approve), role permissions (`VERIFICATION_APPROVE`), draft version binding, and automatic invalidation of stale approvals on draft revisions.
  - **Append-Only Forensic Audit Trail**: Immutable logging of all draft mutations, verification runs, approval requests, decisions, and invalidation lifecycle events.
  - **Alembic Migration**: `0007_response_verification` applied to both `supportgpt_db` and `supportgpt_test_db` with active PostgreSQL Row-Level Security (RLS) policies.
  - **Interactive Next.js Console**: Full management console at `/verification` featuring draft review with claim findings, human approval queue, policy engine configuration, and append-only audit trail inspection.

---

## 2. Prerequisites & Environment

- **Operating System**: Windows 10/11 64-bit (PowerShell 5.1+ or PowerShell 7+)
- **Python**: 3.11.x (Verify via `py -3.11 --version` or `py -0`)
- **Node.js**: v20.x or v22+ (`node -v`)
- **Git**: 2.40+ (`git --version`)
- **Docker Desktop**: Optional for host development, required for running containerized PostgreSQL 16, Redis 7, and Qdrant.

---

## 3. Quick Start (Windows PowerShell)

Open a Windows PowerShell terminal in `D:\SupportGPT-Platform`.

### Step 1: Copy Environment Templates
```powershell
Copy-Item .env.example .env
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
```

### Step 2: Set Up Backend Virtual Environment
```powershell
# Create Python 3.11 virtual environment
py -3.11 -m venv backend\.venv

# Upgrade pip and install development dependencies
.\backend\.venv\Scripts\python.exe -m pip install --upgrade pip
.\backend\.venv\Scripts\pip.exe install -e "./backend[dev]"
```

### Step 3: Set Up Frontend Dependencies
```powershell
cd frontend
cmd /c npm install
cd ..
```

### Step 4: (Optional) Start Infrastructure Containers
If Docker Desktop is running on your machine:
```powershell
docker compose up -d postgres redis qdrant
```

---

## 4. Running the Development Servers

### Terminal 1: Backend API (FastAPI)
```powershell
cd D:\SupportGPT-Platform\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
- API Base: `http://localhost:8000`
- Interactive OpenAPI Docs: `http://localhost:8000/docs`
- Process Liveness Probe: `http://localhost:8000/healthz`
- Infrastructure Readiness Probe: `http://localhost:8000/readyz`

### Terminal 2: Frontend UI (Next.js)
```powershell
cd D:\SupportGPT-Platform\frontend
cmd /c npm run dev
```
- Web Application Shell: `http://localhost:3000`
- Live System Diagnostics Console: `http://localhost:3000/system`

---

## 5. Verification & Testing

### Run Backend Automated Tests (Pytest)
```powershell
cd D:\SupportGPT-Platform
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -v
```

### Run Backend Lint & Formatting (Ruff)
```powershell
.\backend\.venv\Scripts\python.exe -m ruff check backend/
```

### Run Frontend Strict Type-Checking
```powershell
cd D:\SupportGPT-Platform\frontend
cmd /c npm run type-check
```

### Run Frontend Production Build
```powershell
cmd /c npm run build
```

---

## 6. Architecture & Governance Documentation

- [Architecture & Standards](docs/ARCHITECTURE.md): Layer boundaries, request flows, and architectural invariants.
- [Development Guide](docs/DEVELOPMENT.md): Detailed workflow, PowerShell execution policies, and migration guides.
- [Security Architecture](docs/SECURITY.md): Active protections, production validation, and future security milestones.
- [Testing & Quality Gates](docs/TESTING.md): Test categories, execution rules, and current test results.
- [Phased Product Roadmap](docs/ROADMAP.md): Detailed milestones for Phases 00 through 09.
- [ADR 0001: Modular Monolith](docs/adr/0001-modular-monolith-architecture.md)
- [ADR 0002: Async SQLAlchemy & Alembic](docs/adr/0002-async-sqlalchemy-and-alembic.md)
- [ADR 0003: Multi-Tenancy & PostgreSQL RLS Strategy](docs/adr/0003-tenant-isolation-and-rls-strategy.md)
- [ADR 0004: Canonical Domain Model & Tenant Integrity](docs/adr/0004-canonical-domain-model-and-tenant-integrity.md)
- [ADR 0005: Production Authentication, Session Lifecycle, RBAC & PostgreSQL RLS](docs/adr/0005-production-authentication-and-rbac.md)
- [ADR 0006: Ticket Management, Conversation Services & Concurrency Control](docs/adr/0006-ticket-management-and-conversation-services.md)
- [ADR 0007: Reliable Event Ingestion, Webhooks & Background Worker Architecture](docs/adr/0007-reliable-event-ingestion-and-worker-architecture.md)
- [ADR 0008: Enterprise Knowledge Base, Document Processing & Versioning Foundation](docs/adr/0008-knowledge-base-document-processing-and-versioning.md)
- [ADR 0009: Evidence-Grounded Retrieval and Answering Foundation](docs/adr/0009-evidence-grounded-retrieval-and-answering.md)
- [ADR 0010: AI Response Verification, Policy Enforcement and Human Approval](docs/adr/0010-ai-response-verification-and-approval.md)

