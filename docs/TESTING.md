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

## 4. Current Quality Status Summary (Phase 06 Verified Baseline)
- **Backend Unit Tests**: 100% Passing (82 unit tests covering password hashing, RBAC, storage, validation, chunking, real FastEmbed 384d embeddings, dimension validation, non-finite vector rejection, OpenAI provider failure handling, Qdrant collection creation/inspection, dimension mismatch detection, deterministic point IDs, Qdrant batch upsert, tenant filtering, version/document deletion, grounded answering, citation verification, prompt-injection defense in evidence, automated abstention on zero evidence and low relevance, and evaluation metric calculations).
- **Backend API Tests**: 100% Passing (86 API tests covering health probes, correlation ID, RFC 7807 errors, login, logout, current user, organization membership, role updates, last-owner protections, cross-tenant access denial, ticket lifecycle, webhook ingestion, knowledge base CRUD, document uploads/versions, knowledge base search, grounded Q&A, query length validation, and cross-tenant RAG isolation).
- **Backend Integration Tests**: 100% Passing (14 integration tests: declarative metadata validation, composite foreign key verification, live PostgreSQL RLS ticket isolation, live PostgreSQL RLS conversations/messages isolation, live PostgreSQL RLS on sources & receipts, live PostgreSQL RLS on knowledge tables, live PostgreSQL concurrent `FOR UPDATE SKIP LOCKED` worker claim isolation, background worker ticket creation, inbound message appending, lease expiration crash recovery, dead-letter failure handling, document worker pipeline execution, lease timeout reclamation, prior version preservation on new version failure, and live PostgreSQL + Qdrant RAG retrieval/indexing integration).
- **Backend Total**: **182 passed, 0 failures, 1 skipped** (`test_live_database_connection_probe` explicitly skipped when running in SQLite test mode).
- **Backend Linting & Formatting**: 100% Passing (`ruff check .` reported zero violations across app and tests).
- **Frontend Static Quality**: 100% Passing (`npx tsc --noEmit` reported zero TypeScript errors under strict mode).
- **Frontend Production Build**: 100% Passing (`npm run build` compiled 8 static/dynamic routes including `/knowledge`, `/tickets`, `/system`, `/login`, `/`).
- **Repeatable Evaluation Framework**:
  - Evaluation Dataset: 7 labeled enterprise support questions (4 answerable, 3 unanswerable/injection).
  - Model: FastEmbed `BAAI/bge-small-en-v1.5` (384 dims, Cosine similarity).
  - Retrieval Mean Recall@k: **1.0 (100%)**.
  - Mean Reciprocal Rank (MRR): **1.0**.
  - Citation Validity Rate: **1.0 (100%)**.
  - Abstention Accuracy: **0.8571 (85.7%)**.



