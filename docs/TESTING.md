# SupportGPT AI — Automated Testing & Quality Strategy

## 1. Testing Philosophy & Non-Negotiable Rules
In SupportGPT AI, automated testing is treated as an active quality gate rather than a cosmetic compliance check.
1. **Zero Mock Disguises**: Never write tests that merely assert `True`, mock out every domain behavior, or skip meaningful validations.
2. **Real Infrastructure Verification**: Integration tests that probe PostgreSQL or Redis must attempt genuine communication. If the service is unreachable in the current environment, the test must report as **BLOCKED / SKIPPED with an explicit message** rather than falsely claiming success.
3. **Strict Type Safety**: Frontend tests enforce zero TypeScript compilation errors (`tsc --noEmit`) and zero lint errors.

---

## 2. Test Pyramid & Categories

| Category | Scope | Tools | Execution Target |
|---|---|---|---|
| **Unit Tests** | Core configuration validation, production invariants, sensitive log redaction, custom exception schemas, AI boundary proposal invariants, domain normalization rules, status transitions, and SQLite in-memory relational integrity. | Pytest, `sqlite+aiosqlite` | Fast, isolated, zero external network dependency. |
| **API Transport Tests** | Route mapping, `/healthz` liveness, `/readyz` dependency degradation, `/api/v1/system/info`, middleware correlation ID propagation, response timing, RFC 7807 error envelopes. | Pytest, `httpx.AsyncClient` | Fast in-memory ASGI transport without network overhead. |
| **Database Integration Tests** | Async connection verification, declarative table metadata inspection, composite foreign key verification, constraint and naming convention checks. | Pytest, `asyncpg`, PostgreSQL | Live PostgreSQL datastore. (Reports BLOCKED if container is stopped). |
| **Frontend Static Quality** | Strict type checks (no implicit any, no unchecked index access), code styling. | TypeScript (`tsc`), ESLint | Frontend source tree. |
| **Frontend Production Build** | Production artifact compilation, static prerendering, server component validation. | Next.js (`next build`) | Standalone deployment bundle. |

---

## 3. Exact Test Commands (Windows PowerShell)

### Run All Backend Tests:
```powershell
cd D:\SupportGPT-Platform
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -v
```

### Run Unit Tests Only:
```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/unit -v
```

### Run API Transport Tests Only:
```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/api -v
```

### Run Integration Tests:
```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/integration -v
```

### Run Backend Lint & Format Checks:
```powershell
.\backend\.venv\Scripts\python.exe -m ruff check backend/
.\backend\.venv\Scripts\python.exe -m ruff format --check backend/
```

### Run Frontend Static Type Verification:
```powershell
cd D:\SupportGPT-Platform\frontend
cmd /c npm run type-check
```

### Run Frontend Production Build:
```powershell
cmd /c npm run build
```

---

## 4. Current Quality Status Summary (Phase 05 Verified Baseline)
- **Backend Unit Tests**: 100% Passing (66 unit tests covering password hashing, email normalization, token entropy, RBAC matrix, escalation guards, normalization, lifecycle, foreign keys, unique constraints, check constraints, webhook HMAC-SHA256 signature verification, replay window tolerances, payload size bounds, symmetric secret encryption/decryption, secret preview masking, canonical event normalization, local storage atomic writes, path traversal guards, size bounds, checksum integrity, secure document validation, magic bytes, zip bomb defenses, real PDF extraction, scanned PDF / OCR unavailable detection, real DOCX extraction, TXT/Markdown extraction, deterministic text normalization, and hierarchical structural chunking).
- **Backend API Tests**: 100% Passing (81 API tests covering health probes, correlation ID, RFC 7807 errors, login, logout, current user, organization membership, role updates, last-owner protections, cross-tenant access denial, direct ID attack defense, ticket creation, default status/priority, filters, search, pagination, status transition validation, OCC lock_version conflicts, assignment eligibility, deterministic message sequencing, idempotency, author impersonation prevention, attachment metadata sanitization, webhook signature enforcement, timestamp replay rejection, duplicate receipt handling, payload mismatch conflicts, generic webhook header routing, source configuration, secret rotation, receipt query filters, dead-letter replay, worker health diagnostics, knowledge base CRUD, document uploads, document versioning, reprocessing, soft delete, chunk retrieval, and cross-tenant knowledge access denial).
- **Backend Integration Tests**: 100% Passing (14 integration tests: declarative metadata validation, composite foreign key verification, live PostgreSQL RLS ticket isolation, live PostgreSQL RLS conversations/messages isolation, live PostgreSQL RLS on sources & receipts, live PostgreSQL RLS on knowledge tables, live PostgreSQL concurrent `FOR UPDATE SKIP LOCKED` worker claim isolation, background worker ticket creation, inbound message appending, lease expiration crash recovery, dead-letter failure handling, document worker pipeline execution, lease timeout reclamation, and prior version preservation on new version failure).
- **Backend Total**: **160 passed, 0 failures, 1 skipped** (`test_live_database_connection_probe` explicitly skipped when running in SQLite test mode).
- **Backend Linting & Formatting**: 100% Passing (`ruff check app tests` reported zero violations, clean code formatting).
- **Frontend Type-Check**: 100% Passing (TypeScript strict mode zero errors).
- **Frontend Production Build**: 100% Passing (Next.js production bundle compiled cleanly with static prerendering for `/`, `/_not-found`, `/login`, `/modules/[slug]`, `/system`, `/tickets`).



