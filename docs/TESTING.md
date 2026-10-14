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

## 4. Current Quality Status Summary
- **Backend Unit Tests**: 100% Passing (24 unit tests covering normalization, lifecycle, foreign keys, unique constraints, check constraints).
- **Backend API Tests**: 100% Passing (7 API tests).
- **Backend Integration Tests**: 2 Passing (all 11 canonical tables verified on declarative metadata, composite foreign keys verified), 1 Blocked/Skipped (Live PostgreSQL probe waiting for Docker container).
- **Backend Total**: 33 passed, 1 skipped (blocked by live DB container).
- **Backend Linting**: 100% Passing (Ruff zero violations).
- **Frontend Type-Check**: 100% Passing (TypeScript strict mode zero errors).
- **Frontend Production Build**: 100% Passing (compiled standalone bundle in 4.2s).
