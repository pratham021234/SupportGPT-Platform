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

## 4. Current Quality Status Summary (Phase 08 Verified Baseline)
- **Backend Unit Tests**: 100% Passing (102 unit tests covering password hashing, RBAC, storage, validation, chunking, real FastEmbed 384d embeddings, Qdrant collection creation/inspection, grounded answering, citation verification, prompt-injection defense in evidence, automated abstention, evaluation metric calculations, claim extraction & filler filtering, zero-evidence unsupported claim detection, matching corroboration, contradiction detection, declarative policy evaluation, disposition calculation, approval separation-of-duties, dictionary sensitive key redaction, multi-pattern regex secret redaction, structured JSON log sanitization, failure classification mapping, diagnostic hypotheses generation, token cost calculations, and regression threshold evaluation).
- **Backend API Tests**: 100% Passing (97 API tests covering health probes, correlation ID, RFC 7807 errors, login, logout, current user, organization membership, role updates, ticket lifecycle, webhook ingestion, knowledge base CRUD, document uploads/versions, knowledge search, grounded Q&A, response drafts CRUD, verification execution, policy rule management, approval submission and decision commit, deep system diagnostics, execution trace retrieval, failure investigation deduplication, benchmark evaluation runs and comparisons, usage summaries, and multi-tenant isolation across all resources).
- **Backend Integration Tests**: 100% Passing (16 integration tests: declarative metadata validation, composite foreign key verification, live PostgreSQL RLS ticket isolation, live PostgreSQL RLS conversations/messages isolation, live PostgreSQL RLS on sources & receipts, live PostgreSQL RLS on knowledge tables, live PostgreSQL concurrent `FOR UPDATE SKIP LOCKED` worker claim isolation, background worker ticket creation, inbound message appending, lease expiration crash recovery, dead-letter failure handling, document worker pipeline execution, lease timeout reclamation, live PostgreSQL + Qdrant RAG retrieval/indexing integration, live PostgreSQL 16 response verification, claim persistence, and human approval workflow, and live PostgreSQL 16 AI observability, trace recording, failure investigation deduplication, and token usage accounting under enforced PostgreSQL Row-Level Security).
- **Backend Total**: **216 passed, 0 failures, 1 skipped** (`test_live_database_connection_probe` explicitly skipped when running in SQLite test mode) in 70.04s.
- **Backend Linting & Formatting**: 100% Passing (`ruff check .` and `ruff format --check .` reported zero violations across app and tests).
- **Frontend Static Quality**: 100% Passing (`cmd /c npm run type-check` reported zero TypeScript errors under strict mode).
- **Frontend Production Build**: 100% Passing (`cmd /c npm run build` compiled 10 static/dynamic routes including `/observability`, `/verification`, `/knowledge`, `/tickets`, `/system`, `/login`, `/`).
- **Repeatable Evaluation Framework**:
  - Evaluation Dataset: Versioned benchmark runs (`supportgpt-eval-v1`).
  - Model: FastEmbed `BAAI/bge-small-en-v1.5` (384 dims, Cosine similarity).
  - Retrieval Mean Recall@k: **1.0 (100%)**.
  - Mean Reciprocal Rank (MRR): **1.0**.
  - Citation Validity Rate: **1.0 (100%)**.
  - Groundedness Rate: **1.0 (100%)**.
  - Abstention Accuracy: **0.8571 (85.7%)**.
  - Regression Threshold: 5.0% delta limit with automated alert generation.




