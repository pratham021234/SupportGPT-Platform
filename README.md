# SupportGPT AI — Platform Foundation & Architecture

> **Enterprise AI Support Quality, Verification, Human Approvals & Reliability Platform**

SupportGPT AI is a commercial-grade, multi-tenant B2B SaaS platform engineered for customer support automation with factual grounding, claim-level response verification, policy-enforced human approvals, and forensic AI failure investigation.

---

## 1. Engineering Status: Phase 00, Phase 01, Phase 02 & Phase 03 Completed

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
