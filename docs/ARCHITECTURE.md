# SupportGPT AI — Architecture & Engineering Standards

## 1. System Mission & Scope
SupportGPT AI is an enterprise-grade multi-tenant B2B SaaS platform engineered for customer support automation with factual reliability, claim-level response verification, human-in-the-loop approvals, and forensic failure investigation.

Phase 00 establishes the greenfield technical foundation and architectural standards across the frontend, backend, database, and infrastructure tiers.

---

## 2. High-Level Architecture Diagram

```mermaid
graph TD
    subgraph Client ["Client Presentation Tier (Next.js App Router)"]
        BrowserUI["Browser UI Shell (TypeScript Strict)"]
        UIState["Component State & Skeletons"]
        APIClient["Typed API Client (Fetch + AbortController)"]
        BrowserUI --> UIState
        UIState --> APIClient
    end

    subgraph Transport ["Transport & Edge Security (FastAPI)"]
        HTTPGateway["FastAPI Gateway (:8000)"]
        CorsMW["Validated CORS Middleware"]
        CorrMW["Correlation ID Middleware (X-Request-ID)"]
        ErrMW["RFC 7807 Error Interceptor"]
        
        HTTPGateway --> CorsMW
        CorsMW --> CorrMW
        CorrMW --> ErrMW
    end

    subgraph MonolithCore ["Modular Monolith Core"]
        Config["Validated Settings (Pydantic v2)"]
        HealthSvc["Health & Readiness Probes (/healthz, /readyz)"]
        SystemSvc["Platform Metadata (/api/v1/system/info)"]
        AIBoundary["AI Vendor-Neutral Abstraction Boundary"]
        
        ErrMW --> HealthSvc
        ErrMW --> SystemSvc
        ErrMW --> AIBoundary
    end

    subgraph Persistence ["Persistence & Caching Tier"]
        AsyncEngine["SQLAlchemy 2.x Async Engine (asyncpg)"]
        BaseModels["Declarative Base (UUIDv4 + UTC Timestamps)"]
        Postgres[(PostgreSQL 16 Primary Datastore)]
        RedisCache[(Redis 7 Cache / Task Broker)]
        QdrantStore[(Qdrant Vector Engine)]
        
        HealthSvc --> AsyncEngine
        HealthSvc --> RedisCache
        AsyncEngine --> Postgres
    end

    APIClient -->|HTTP/JSON + X-Request-ID| HTTPGateway
```

---

## 3. Layer Boundaries & Component Responsibilities

| Layer | Directory | Responsibilities | Forbidden Patterns |
|---|---|---|---|
| **Transport** | `backend/app/api/` | HTTP request parsing, response status codes, route grouping. | No direct SQL queries, no business calculations. |
| **Core & Settings** | `backend/app/core/` | Configuration loading, production invariants, structured logging, correlation ID, error translation. | No credentials committed, no unredacted logs. |
| **Schemas** | `backend/app/schemas/` | Typed Pydantic request/response transfer objects. | No ORM models leaked directly without schema mapping. |
| **Domain Models** | `backend/app/models/` | SQLAlchemy 2.x declarative definitions, table constraints, indexes. | No business logic in model definitions. |
| **Database Session** | `backend/app/db/` | Async engine pool, session dependency injection, connection verification. | No unclosed sessions or uncontrolled transactions. |
| **AI Boundary** | `backend/app/ai/` | Vendor-neutral abstract base classes (`BaseLLMProvider`, `BaseEmbeddingProvider`), `AIActionProposal` invariants. | No hardcoded SDK calls, no AI action executed without proposal status. |
| **Frontend Shell** | `frontend/src/` | Next.js App Router, accessible design system, live diagnostic views, typed client. | No fake metrics, no simulated nonfunctional controls. |

---

## 4. End-to-End Request Flow

```mermaid
sequenceDiagram
    autonumber
    actor User as Enterprise Operator
    participant FE as Next.js Client Shell
    participant MW as FastAPI Correlation MW
    participant Handler as Route Handler
    participant DB as PostgreSQL 16
    
    User->>FE: Navigate to /system (Diagnostics)
    FE->>MW: GET /readyz (Accept: application/json)
    Note over MW: Generates or extracts X-Request-ID<br/>Sets contextvar for structured logging
    MW->>Handler: Dispatch readiness_probe()
    Handler->>DB: SELECT 1 (Timeout: 2.0s)
    DB-->>Handler: Connection probe successful (0.8ms)
    Handler-->>MW: 200 OK + ReadinessResponse
    Note over MW: Attaches X-Request-ID & X-Response-Time-Ms
    MW-->>FE: HTTP 200 OK
    FE-->>User: Render operational cards & latency table
```

---

## 5. Architectural Standards Enforced
1. **Correlation Tracking**: Every HTTP request receives an `X-Request-ID` header (UUID4), which is propagated through all log records and error envelopes.
2. **Standardized Error Envelope**: API exceptions adhere to the RFC 7807 problem details specification without leaking stack traces or internal implementation paths.
3. **Database Conventions**:
   - Primary Keys: Non-sequential `UUIDv4`.
   - Timestamps: UTC-aware `created_at` and `updated_at`.
   - Naming Conventions: Deterministic metadata constraints (`ix_`, `uq_`, `ck_`, `fk_`, `pk_`).
4. **AI Safety Invariant**: All AI-generated actions are typed as `AIActionProposal` with immutable `is_proposal=True`. They require authenticated human approval or deterministic policy execution before mutation.
