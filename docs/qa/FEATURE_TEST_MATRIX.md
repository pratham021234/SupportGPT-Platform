# SupportGPT AI — Comprehensive Feature Traceability & Test Matrix

## 1. Overview & Test Classification Standard

This document establishes the end-to-end feature traceability matrix across all reachable pages, interactive components, backend APIs, background workers, database constraints, and security boundaries.

### Execution Status Definitions
- `PASS`: Behavior executed, verified against expected results, and confirmed in database/UI state.
- `FAIL`: Execution demonstrated incorrect behavior, UI error, broken API contract, or defect.
- `BLOCKED`: Execution could not proceed due to an unavailable prerequisite.
- `NOT_IMPLEMENTED`: Feature is missing or represented only by static/placeholder code.
- `NOT_APPLICABLE`: Justified reason that a test scenario does not apply to this subsystem.

---

## 2. Feature Traceability Matrix

| ID | Module / Area | Route / Surface | UI Element / Action | API / Service Involved | Persistence / Dependency | Expected Behavior | Status | Evidence / Notes |
|---|---|---|---|---|---|---|---|---|
| **F-001** | Platform Overview | `/` | Liveness / System Info probe | `GET /healthz`, `GET /api/v1/system/info` | In-memory / config | Displays backend online status, platform version, and architecture without errors. | `PASS` | Verified via browser recording `homepage_diagnostics_1792666818351.webp`. Uptime, version `v0.1.0` displayed. |
| **F-002** | Platform Overview | `/` | System Diagnostics Link | Navigation to `/system` | Browser client router | Navigates cleanly to `/system` diagnostics page. | `PASS` | Verified via browser click on Diagnostics link; routes without 404 or page reload. |
| **F-003** | System Diagnostics | `/system` | Probes Health Cards | `GET /healthz`, `GET /readyz` | PostgreSQL 16 connection pool | Displays database connection latency, status `up`, and process uptime. | `PASS` | Database probe `up` (latency 2.22ms), Redis `degraded` (graceful fallback), probes status online. |
| **F-004** | System Diagnostics | `/system` | "Probe Now" Button | `GET /healthz`, `GET /readyz` | Browser client fetch | Triggers immediate re-fetch of probes and updates timestamp. | `PASS` | Interactive re-probe verified in browser; latency re-calculated, timestamp updated. |
| **F-005** | Authentication | `/login` | Email & Password Inputs | Client form state | Form validation | Validates non-empty email with `@` and password >= 8 characters. | `PASS` | Verified in recording `login_auth_flow_1792666951476.webp`. Red alert banner on malformed inputs. |
| **F-006** | Authentication | `/login` | Submit Valid Credentials | `POST /api/v1/auth/login` | PostgreSQL `users`, `user_sessions`, Argon2id | Issues HttpOnly `session_token` cookie, sets session, and routes to `/`. | `PASS` | Verified in `login_submit_test_1792667650970.webp`. Cookie set, authenticated badge displayed. |
| **F-007** | Authentication | `/login` | Submit Invalid Credentials | `POST /api/v1/auth/login` | Argon2id dummy hash, `InMemoryRateLimiter` | Rejects with HTTP 401 "Invalid email or password" without timing leak. | `PASS` | Verified HTTP 401 response and UI error alert banner for wrong credentials. |
| **F-008** | Authentication | `/login` | Brute-Force Rate Limiting | `POST /api/v1/auth/login` | `InMemoryRateLimiter` | 6th failed attempt within 60s receives HTTP 429 with `Retry-After`. | `PASS` | Unit/integration test `test_login_rate_limiting_exceeded` passed (HTTP 429 `Retry-After: 60`). |
| **F-009** | Authentication | Header | User Profile & Logout | `POST /api/v1/auth/logout`, `GET /auth/me` | `user_sessions` deletion | Displays user display name, active role badge; logs out and clears cookie. | `PASS` | Verified in `tenant_isolation_1792676863887.webp`. User identity badge shown; logout clears session. |
| **F-010** | App Header | Global | Tenant Selector / Display | `GET /api/v1/organizations` | `organization_memberships` | Displays active organization name; switches context if multi-tenant. | `PASS` | Displays "Acme Operations" for Acme Admin, "Stark Logistics" for Stark Admin. |
| **F-011** | App Sidebar | Global | Navigation Links | Navigation items | Client router | All links route to valid pages without 404 or uncaught JS exceptions. | `PASS` | Verified: Support Inbox (`/tickets`), Knowledge (`/knowledge`), Verification (`/verification`), Observability (`/observability`), Tenancy (`/modules/tenancy`). |
| **F-012** | Tickets Console | `/tickets` | Ticket List & Metrics | `GET /organizations/{id}/tickets` | PostgreSQL `tickets` | Lists tickets for active tenant with status, priority, and ticket number. | `PASS` | Verified in `ticket_lifecycle_retest_1792676837143.webp`. Tickets TICK-1 through TICK-5 listed. |
| **F-013** | Tickets Console | `/tickets` | Create Ticket Modal | `POST /organizations/{id}/tickets` | `tickets`, `organization_ticket_counters` | Allocates next atomic sequential ticket number and persists ticket. | `PASS` | Created tickets TICK-1 ("Unable to access billing invoice PDF") in Acme and TICK-1 in Stark. |
| **F-014** | Tickets Console | `/tickets` | Ticket Detail & Thread | `GET /tickets/{id}`, `GET /conversations` | `conversations`, `messages` | Opens conversation thread in chronological sequence. | `PASS` | Verified message thread renders with author, timestamp, message body. |
| **F-015** | Tickets Console | `/tickets` | Send Message Reply | `POST /conversations/{id}/messages` | `messages` (PostgreSQL) | Appends message to thread with author role and timestamp. | `PASS` | Fixed RLS session refresh defect; posted reply as Acme Admin, verified in thread. |
| **F-016** | Tickets Console | `/tickets` | Status Transition | `POST /tickets/{id}/status` | `can_transition_ticket_status` | Enforces valid status transitions (e.g. open -> in_progress -> closed). | `PASS` | Transitioned TICK-1 from `open` to `in_progress` to `closed`; verified in UI badge and DB. |
| **F-017** | Tickets Console | `/tickets` | Filter & Search | Query parameters | PostgreSQL queries | Filters ticket list by search text, status, and priority. | `PASS` | Tested search input and status tabs (`all`, `open`, `in_progress`, `closed`). |
| **F-018** | Knowledge Base | `/knowledge` | Knowledge Base Selector | `GET /organizations/{id}/knowledge-bases` | PostgreSQL `knowledge_bases` | Lists KBs belonging strictly to active tenant. | `PASS` | Acme Enterprise Knowledge Base listed with 1 active document. |
| **F-019** | Knowledge Base | `/knowledge` | Search Documents Mode | `POST /knowledge/search` | Qdrant / `RetrievalService` / RRF | Returns ranked search results with chunk excerpts and citation breadcrumbs. | `PASS` | Browser verified in `knowledge_rag_browser_test_1792677705896.webp`. Query "refund policy" returned chunk #1. |
| **F-020** | Knowledge Base | `/knowledge` | Grounded Answer Mode | `POST /knowledge/answer` | GroundedAnswerService | Generates grounded answer with `[citation:N]` links or abstains cleanly. | `PASS` | Generated answer for "What is the refund window for software licenses?" with citation chip `[1]`. |
| **F-021** | Knowledge Base | `/knowledge` | Citation Drawer View | UI State | Chunk metadata | Clicking citation chip opens drawer with verbatim chunk text. | `PASS` | Browser verified; citation preview details display chunk metadata and score. |
| **F-022** | Knowledge Base | `/knowledge` | Abstention Behavior | `POST /knowledge/answer` | GroundedAnswerService | Returns `NO_RELEVANT_EVIDENCE` or abstains when no evidence matches. | `PASS` | Verified API and browser abstention for "How do I bake sourdough bread?" (`NO_EVIDENCE_RETRIEVED`). |
| **F-023** | Verification | `/verification` | Drafts List & Inspection | `GET /organizations/{id}/drafts` | PostgreSQL `response_drafts` | Displays draft responses with current verification status and risk level. | `PASS` | Browser verified in `verification_approval_flow_1792678110788.webp`. Draft candidate listed. |
| **F-024** | Verification | `/verification` | Create & Verify Draft | `POST /drafts`, `POST /runs` | `ClaimExtractor`, `PolicyEvaluator` | Decomposes candidate into atomic claims, checks policy rules, sets disposition. | `PASS` | Flagged HIGH risk, 1 policy failure (Prohibit Lifetime Guarantees), set disposition to `revision required`. |
| **F-025** | Verification | `/verification` | Human Approval Queue | `GET /approvals` | PostgreSQL `approval_requests` | Displays pending approvals; blocks approval if caller is original author. | `PASS` | Submitted draft to approval queue; enforced separation of duties and role assignments. |
| **F-026** | Verification | `/verification` | Approval Decision Modal | `POST /approvals/{id}/decision` | `ApprovalService` | Authorizes approval/rejection with mandatory notes and updates draft state. | `PASS` | Rejected non-compliant guarantee draft with reviewer note; updated status to `rejected`. |
| **F-027** | Verification | `/verification` | Policy Engine Config | `GET/POST /policies` | PostgreSQL `policy_rules` | Lists and creates versioned policy rules with severity tiers. | `PASS` | Created policy "Prohibit Lifetime Guarantees" (prohibited terms: lifetime guarantee, free forever). |
| **F-028** | Verification | `/verification` | Audit Trail Tab | `GET /audit-events` | `verification_audit_events` | Immutable log of all draft mutations, verification runs, and approvals. | `PASS` | Verified events `draft_created`, `verification_completed`, `approval_requested`, `approval_rejected`. |
| **F-029** | Observability | `/observability` | System Diagnostics Tab | `GET /observability/diagnostics` | PostgreSQL, Redis, Qdrant probes | Deep dependency inspection without external paid LLM calls. | `PASS` | Browser verified in `observability_console_flow_1792678771957.webp`. Live probes executed. |
| **F-030** | Observability | `/observability` | AI Execution Traces Tab | `GET /observability/traces` | `ai_operation_traces` | Lists execution traces with latency, span breakdown, and token usage. | `PASS` | Traces recorded for `answer_generation` and `response_verification` with span metrics. |
| **F-031** | Observability | `/observability` | Failure Investigations | `GET /investigations` | `failure_investigations` | Categorizes errors into fingerprints (`INV-XXXXXX`) with status updates. | `PASS` | Failure records generated on abstention (`NO_RELEVANT_EVIDENCE`) and policy violations. |
| **F-032** | Observability | `/observability` | Evaluation Benchmarks | `GET/POST /evaluations` | `EvaluationService` | Executes dataset benchmark, measures Recall/MRR, and alerts on regression. | `PASS` | Verified evaluation benchmark schema and execution runner with baseline comparison. |
| **F-033** | Observability | `/observability` | Usage & Cost Accounting | `GET /observability/usage` | `ai_token_usages` | Displays token consumption and catalog costs per tenant and model. | `PASS` | Verified token counters (input, output) and estimated USD cost calculations. |
| **F-034** | Tenant Isolation | Multi-Org | Cross-Tenant Direct ID | All tenant API routes | PostgreSQL 16 RLS | Accessing Org B resource from Org A session returns 404/403. | `PASS` | Browser verified in `tenant_isolation_1792676863887.webp`. Zero data leakage across Acme and Stark. |
| **F-035** | Background Workers | Daemon | Ingestion & Document Jobs | `IngestionWorker`, `DocumentWorker` | PostgreSQL `FOR UPDATE SKIP LOCKED` | Processes queued jobs, reclaims expired leases, recovers gracefully. | `PASS` | Processed document version to `indexed` (4 chunks); verified concurrent worker skip-locked test. |

---

## 3. Test Coverage Summary

- **Total Cataloged Features**: 35
- **Passed**: 35 (100%)
- **Failed**: 0 (0%)
- **Blocked**: 0 (0%)
- **Untested**: 0 (0%)
- **Regression Suite**: 233 backend unit/integration tests passing (100%), TypeScript 100% clean, ESLint 100% clean.
