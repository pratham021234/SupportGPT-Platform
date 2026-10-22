# SupportGPT AI — QA Defects, Root Cause Analysis & Engineering Fixes

## 1. Overview

During the execution of the Master End-to-End QA Mission on SupportGPT AI, all issues were investigated to their root cause, fixed directly in the codebase, validated with regression tests, and verified in real browser sessions.

---

## 2. Defect Log & Remediation Details

### Defect 1: PostgreSQL RLS Session Variable Cleared on Commit (`InvalidRequestError`)
- **Severity**: Critical (P0)
- **Subsystem**: Relational Data Layer / Row-Level Security (RLS)
- **Affected Components**:
  - `backend/app/services/ticket_service.py`
  - `backend/app/services/conversation_service.py`
  - `backend/app/services/document_service.py`
- **Symptom**:
  When posting a reply in a ticket thread or updating a ticket's status, the API returned HTTP 500. Backend server logs showed:
  ```text
  sqlalchemy.exc.InvalidRequestError: Could not refresh instance '<Ticket ...>' - no row was returned for the identity key
  ```
- **Root Cause Analysis**:
  Tenant isolation in SupportGPT AI is strictly enforced by PostgreSQL Row-Level Security (RLS). When a database session is opened, `set_tenant_rls_context(session, org_id)` runs:
  ```sql
  SELECT set_config('app.current_organization_id', :org_id, true);
  ```
  The third argument `is_local = true` scopes the PostgreSQL configuration variable strictly to the *current transaction*. When the service executed `await session.commit()`, PostgreSQL closed the transaction and cleared the `app.current_organization_id` setting. When SQLAlchemy immediately followed with `await session.refresh(ticket)`, it initiated a new transaction where `app.current_organization_id` was `NULL`. Because RLS policies prevent reading rows without an active organization context, PostgreSQL returned 0 rows, triggering SQLAlchemy's `InvalidRequestError`.
- **Engineering Fix**:
  Updated `ticket_service.py`, `conversation_service.py`, and `document_service.py` so that whenever `session.commit()` is called, `set_tenant_rls_context(session, organization_id)` is explicitly re-established before calling `session.refresh(...)`.
  ```python
  # Re-establish RLS context after commit for refresh
  await session.commit()
  await set_tenant_rls_context(self.session, organization_id)
  await self.session.refresh(ticket)
  ```
- **Verification**:
  Browser testing verified: Ticket updates, thread replies, and status transitions to `closed` succeed with HTTP 200 and persist across page reloads.

---

### Defect 2: Storage Directory Path Sensitivity Across Working Directories
- **Severity**: High (P1)
- **Subsystem**: Storage & Document Processing Subsystem
- **Affected Components**:
  - `backend/app/services/storage/__init__.py`
  - `backend/app/services/document_worker.py`
- **Symptom**:
  Background `DocumentWorker` failed with:
  ```text
  app.core.errors.ResourceNotFoundException: Storage object with identifier 'org_.../docs/.../v1_....bin' was not found.
  ```
- **Root Cause Analysis**:
  `settings.LOCAL_STORAGE_DIR` defaults to `"storage_data"` (a relative path). When `LocalStorageBackend` initialized, it called `Path(base_dir).resolve()`, which resolves relative to the current working directory (`os.getcwd()`).
  When tests or seeding scripts ran inside `D:\SupportGPT-Platform\backend`, objects were written to `D:\SupportGPT-Platform\backend\storage_data`. But when the FastAPI daemon was launched from the repository root `D:\SupportGPT-Platform`, it looked in `D:\SupportGPT-Platform\storage_data`, causing binary lookup failures.
- **Engineering Fix**:
  Modified `get_storage_backend()` in `backend/app/services/storage/__init__.py` to resolve relative storage directory paths against the canonical backend directory:
  ```python
  if not base_dir.is_absolute():
      backend_dir = Path(__file__).resolve().parents[3]
      if (backend_dir / base_dir).exists():
          base_dir = backend_dir / base_dir
      elif not (Path.cwd() / base_dir).exists():
          base_dir = backend_dir / base_dir
  ```
- **Verification**:
  Worker successfully claimed version `61f5b15d-8b1c-4f87-adfd-0591a9ef5150`, read binary content, extracted markdown, generated 4 chunks, and indexed vectors into Qdrant.

---

### Defect 3: Fragile Sleep-Based Concurrency Test on Windows
- **Severity**: Medium (P2)
- **Subsystem**: Integration Test Suite
- **Affected Components**:
  - `backend/tests/integration/test_postgres_worker_concurrency.py`
- **Symptom**:
  ```text
  AssertionError: Worker collision detected! Shared receipts: {UUID('...'), UUID('...'), UUID('...')}
  assert 3 == 0
  ```
- **Root Cause Analysis**:
  `test_live_postgresql_concurrent_worker_skip_locked` tests that two concurrent workers using `FOR UPDATE SKIP LOCKED` claim disjoint batches. The test relied on `await asyncio.sleep(0.1)` in worker 1 and `await asyncio.sleep(0.02)` in worker 2 to simulate concurrent locks.
  On Windows systems with 15.6ms timer resolution or under high CPU load, worker 1's sleep occasionally expired and committed its transaction before worker 2 executed its claim. Since the receipts' status was not updated within the test, worker 2 saw the unlocked rows and claimed the same receipts.
- **Engineering Fix**:
  Replaced arbitrary `asyncio.sleep` calls with deterministic `asyncio.Event` synchronization (`w1_locked` and `w2_done`):
  - Worker 1 executes `FOR UPDATE SKIP LOCKED`, acquires row locks, and signals `w1_locked.set()`.
  - Worker 2 waits on `w1_locked.wait()`, executes its claim while worker 1's transaction is guaranteed active, and signals `w2_done.set()`.
  - Worker 1 waits on `w2_done.wait()` before committing.
- **Verification**:
  `pytest backend/tests/integration/test_postgres_worker_concurrency.py` passes 100% deterministically in 0.66s without timing flakiness.

---

### Defect 4: Next.js Login Navigation & Unused Variable Lint Error
- **Severity**: Low (P3)
- **Subsystem**: Frontend Authentication UI
- **Affected Components**:
  - `frontend/src/app/login/page.tsx`
- **Symptom**:
  1. `router.push("/")` retained client router state after login, causing the AppHeader session badge to remain in unauthenticated state until manual page refresh.
  2. When updated to `window.location.href = "/"`, TypeScript compiler raised:
     ```text
     src/app/login/page.tsx(11,9): error TS6133: 'router' is declared but its value is never read.
     ```
- **Engineering Fix**:
  Updated login redirect to `window.location.href = "/"` to guarantee fresh session bootstrap and removed the unused `useRouter` import and variable declaration.
- **Verification**:
  `npm run type-check` passed with 0 errors. Real browser login redirected to `/` and rendered the active organization badge immediately.

---

### Defect 5: ESLint Scanning `.next` Build Artifact Directory
- **Severity**: Low (P3)
- **Subsystem**: Frontend Build & Quality Infrastructure
- **Affected Components**:
  - `frontend/eslint.config.mjs`
- **Symptom**:
  Running `npm run lint` checked compiled Webpack runtime files in `.next/server/webpack-runtime.js`, reporting 7 syntax errors (`@next/next/no-assign-module-variable`).
- **Root Cause Analysis**:
  Next.js 15 flat ESLint configuration did not specify `.next/**` in the global `ignores` list.
- **Engineering Fix**:
  Added an `ignores` block to `frontend/eslint.config.mjs`:
  ```javascript
  const eslintConfig = [
    {
      ignores: [".next/**", "node_modules/**", "out/**", "build/**"],
    },
    ...compat.extends("next/core-web-vitals"),
  ];
  ```
- **Verification**:
  `npm run lint` completed cleanly with 0 errors and 0 warnings.
