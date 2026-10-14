# SupportGPT AI — Architecture & Engineering Standards

## 1. System Mission & Scope
SupportGPT AI is an enterprise-grade multi-tenant B2B SaaS platform engineered for customer support automation with factual reliability, claim-level response verification, human-in-the-loop approvals, and forensic failure investigation.

Phase 00 established the greenfield technical foundation and architectural standards across the frontend, backend, database, and infrastructure tiers.
Phase 01 establishes the canonical customer support domain models, normalized schemas, composite tenant boundaries, and Alembic database migration foundation.

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
        DomainModels["Canonical Domain Models (Phase 01)"]
        
        ErrMW --> HealthSvc
        ErrMW --> SystemSvc
        ErrMW --> AIBoundary
        ErrMW --> DomainModels
    end

    subgraph Persistence ["Persistence & Caching Tier"]
        AsyncEngine["SQLAlchemy 2.x Async Engine (asyncpg)"]
        BaseModels["Declarative Base (UUIDv4 + UTC Timestamps)"]
        Postgres[(PostgreSQL 16 Primary Datastore)]
        RedisCache[(Redis 7 Cache / Task Broker)]
        QdrantStore[(Qdrant Vector Engine)]
        
        HealthSvc --> AsyncEngine
        HealthSvc --> RedisCache
        DomainModels --> AsyncEngine
        AsyncEngine --> Postgres
    end

    APIClient -->|HTTP/JSON + X-Request-ID| HTTPGateway
```

---

## 3. Domain Model Architecture & Entity Relationship (Phase 01)

### 3.1 Domain Glossary
- **`Organization`**: Authoritative enterprise customer workspace and root multi-tenant boundary.
- **`OrganizationTicketCounter`**: Concurrency-safe atomic sequential counter table allocating per-organization ticket numbers.
- **`Customer`**: External person or business contacting customer support.
- **`CustomerIdentity`**: Specific contact handle (email, phone, channel identifier) owned by a customer, normalized for deduplication.
- **`Ticket`**: Canonical customer support case record tracking subject, lifecycle status, priority, and assignment.
- **`Conversation`**: Interactive communication thread within a ticket (e.g. email thread, live chat session).
- **`Message`**: Immutable individual communication entry within a conversation thread with deterministic chronological ordering.
- **`Attachment`**: Opaque file metadata reference attached to a message without storing file bytes in relational rows.
- **`TicketEvent`**: Append-only historical lifecycle audit record capturing state transitions, assignments, and mutations.
- **`IngestionReceipt`**: Inbound event idempotency record tracking external provider event IDs to prevent duplicate processing.

### 3.2 Entity Relationship Diagram

```mermaid
erDiagram
    ORGANIZATION ||--o{ ORGANIZATION_TICKET_COUNTER : "maintains sequence"
    ORGANIZATION ||--o{ CUSTOMER : "owns"
    ORGANIZATION ||--o{ CUSTOMER_IDENTITY : "scopes lookup"
    ORGANIZATION ||--o{ TICKET : "owns"
    ORGANIZATION ||--o{ CONVERSATION : "scopes thread"
    ORGANIZATION ||--o{ MESSAGE : "scopes communication"
    ORGANIZATION ||--o{ ATTACHMENT : "scopes file"
    ORGANIZATION ||--o{ TICKET_EVENT : "scopes audit log"
    ORGANIZATION ||--o{ INGESTION_RECEIPT : "deduplicates"

    CUSTOMER ||--o{ CUSTOMER_IDENTITY : "has multiple"
    CUSTOMER ||--o{ TICKET : "initiates"

    TICKET ||--o{ CONVERSATION : "contains threads"
    TICKET ||--o{ TICKET_EVENT : "tracks lifecycle"

    CONVERSATION ||--o{ MESSAGE : "contains ordered"
    MESSAGE ||--o{ ATTACHMENT : "references metadata"
```

---

## 4. Key Integrity Rules & Database Invariants

### 4.1 Tenant-Boundary Composite Foreign Keys
To guarantee multi-tenant data consistency at the PostgreSQL engine level, child entities enforce composite foreign keys spanning both the parent ID and the `organization_id`:
1. `conversations` enforces `FOREIGN KEY (ticket_id, organization_id) REFERENCES tickets(id, organization_id)` on `RESTRICT`.
2. `messages` enforces `FOREIGN KEY (conversation_id, organization_id) REFERENCES conversations(id, organization_id)` on `RESTRICT`.
3. `attachments` enforces `FOREIGN KEY (message_id, organization_id) REFERENCES messages(id, organization_id)` on `RESTRICT`.
4. `ticket_events` enforces `FOREIGN KEY (ticket_id, organization_id) REFERENCES tickets(id, organization_id)` on `RESTRICT`.
5. `customer_identities` enforces `FOREIGN KEY (customer_id, organization_id) REFERENCES customers(id, organization_id)` on `CASCADE`.

**Impact**: It is physically impossible in the database for a conversation, message, attachment, or event to point to an entity in a different organization.

### 4.2 Deletion Safeguards (`ON DELETE RESTRICT`)
- Deleting an `Organization` with active customers, tickets, or audit events is blocked via `ON DELETE RESTRICT`. Historical records are safeguarded from accidental deletion.
- Deleting a `Customer` sets `tickets.customer_id = NULL` (`ON DELETE SET NULL`), preserving the ticket case history.
- `CustomerIdentity` records cascade on customer deletion (`ON DELETE CASCADE`) as they are components of the customer aggregate.

### 4.3 Ticket Number Generation Strategy
- Uses a dedicated transactional table: `organization_ticket_counters(organization_id, next_ticket_number)`.
- Allocated within transaction boundaries via `SELECT FOR UPDATE` with row-level locking.
- Prevents race conditions and guarantees gap-free, monotonically increasing ticket numbers per organization.

### 4.4 Idempotency & Deduplication
- `IngestionReceipt` enforces `UNIQUE (organization_id, source_provider, external_event_id)`. Duplicate webhook/email events from upstream providers are immediately recognized and deduplicated before downstream processing.
- `Message` indexes `(organization_id, external_message_id)` to prevent duplicate deliveries within the thread.

---

## 5. Lifecycle Statuses & Transition Rules

### Ticket Status Lifecycle
- Valid Statuses: `open`, `pending`, `in_progress`, `resolved`, `closed`
- Priorities: `urgent`, `high`, `medium`, `low`
- Channels: `email`, `chat`, `api`, `web`, `internal`
- Valid Transition Matrix:
  - `open` -> `pending`, `in_progress`, `resolved`, `closed`
  - `pending` -> `open`, `in_progress`, `resolved`, `closed`
  - `in_progress` -> `pending`, `resolved`, `closed`, `open`
  - `resolved` -> `open` (customer re-open), `closed`
  - `closed` -> `open` (authorized re-open)

---

## 6. Known Limitations & Deferred Work (Out of Scope for Phase 01)
1. **Authentication & Authorization**: Handled in Phase 02. `organization_id` values currently act as relational integrity anchors, not authorization authority.
2. **PostgreSQL Row-Level Security (RLS)**: Scheduled for Phase 02.
3. **Ingestion Pipelines**: Webhook endpoints, email MIME parsing, and background workers are scheduled for subsequent phases.
4. **File Storage**: `Attachment` models persist storage references (`storage_key`), not raw bytes. Object storage integrations (S3/GCS) and malware scanning will be integrated in future phases.
