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

---

## 6. Authentication, Organization Membership, RBAC & Tenant Isolation (Phase 02)

### 6.1 User & Identity Management
- **User Accounts (`users`)**:
  - UUIDv4 primary key (`id`).
  - Canonical normalized email address (`email`, lowercase, trimmed, unique index).
  - Argon2id password hash (`password_hash`, 64MB memory, 3 iterations, 4 parallelism).
  - Explicit account status (`status`: `active`, `suspended`, `disabled`).
  - Account audit timestamps (`created_at`, `updated_at`, `last_login_at`, `password_changed_at`).
  - Constant-time verification with dummy hash execution for non-existent users to eliminate timing side-channels and account enumeration.

### 6.2 Session Lifecycle & Token Security
- **User Sessions (`user_sessions`)**:
  - Server-side revocable session table indexed on SHA-256 token hashes (`session_token_hash`).
  - Raw session tokens are 256-bit cryptographically random strings (`secrets.token_urlsafe(32)`), transported via secure `HttpOnly`, `SameSite=Lax` cookies (`supportgpt_session`) or `Authorization: Bearer <token>` headers.
  - Immediate invalidation on logout (`/api/v1/auth/logout`) and automatic expiration after 7 days.
  - Raw session secrets and password hashes are never exposed in API responses or structured logs.

### 6.3 Multi-Tenant Organization Membership & Centralized RBAC
- **Organization Memberships (`organization_memberships`)**:
  - UUIDv4 primary key (`id`).
  - Explicit foreign keys to `organizations` (`ON DELETE RESTRICT`) and `users` (`ON DELETE CASCADE`).
  - Database-enforced uniqueness per `(organization_id, user_id)`.
  - Roles: `owner`, `admin`, `agent`, `viewer`.
  - Statuses: `active`, `suspended`, `invited`, `revoked`. Suspended or revoked memberships immediately deny access.
- **Role-Permission Matrix & Least Privilege**:
  - `owner`: Full organizational authority, member provisioning, ownership transfer.
  - `admin`: Member management (excluding owners), operational oversight of tickets and customers.
  - `agent`: Operational support actions (read/write tickets and customers, assign tickets).
  - `viewer`: Read-only access to organization, tickets, and customers.
- **Privilege Escalation & Last-Owner Protections**:
  - `admin` cannot grant `owner` or `admin` roles, preventing unauthorized escalation.
  - Demoting or revoking the sole active `owner` in an organization is blocked with `403 Forbidden`.

### 6.4 Tenant Authorization & PostgreSQL Row-Level Security (RLS)
- **Application Layer**:
  - `OrganizationContext` dependency verifies caller's active membership in the target organization.
  - `TenantScopedQuery` ensures all entity queries unconditionally filter by `WHERE organization_id = :org_id`. Cross-tenant lookups return `None` (resulting in `404 Not Found`), preventing existence disclosure.
- **Database Layer**:
  - PostgreSQL Row-Level Security (RLS) enabled with `FORCE ROW LEVEL SECURITY` across all multi-tenant tables (`tickets`, `conversations`, `messages`, `attachments`, `ticket_events`, `customers`, `customer_identities`).
  - Transaction-local tenant context established via `SELECT set_config('app.current_organization_id', :org_id, true)`. The `is_local=true` flag ensures immediate cleanup on transaction end, guaranteeing safe connection pool reuse.
  - Missing or unset context defaults to 0 rows returned and blocks all inserts.

---

## 7. Ticket Management, Conversation Services & Concurrency Control (Phase 03)

### 7.1 Sequential Ticket Number Allocation
- Every organization maintains an atomic counter in `organization_ticket_counters`.
- During ticket creation, `allocate_next_ticket_number` acquires an exclusive row-level lock via `SELECT ... FOR UPDATE` inside the active transaction.
- Guarantees sequential human-readable numbering (`TICK-{number}`) without gaps or race conditions under high concurrent ticket creation.

### 7.2 Optimistic Concurrency Control (OCC)
- The `tickets` table includes an integer column `lock_version` (default 1, non-nullable).
- State-changing updates accept an optional `lock_version` token.
- If the client's token does not match the database version, the update is rejected with `409 Conflict` (`CONCURRENCY_CONFLICT`), preventing lost updates between concurrent operators.
- Successful updates atomically increment `lock_version += 1`.

### 7.3 Domain-Enforced Status Transitions & Assignment Rules
- Ticket status movements (`open` -> `in_progress` -> `resolved` -> `closed`) are governed centrally by `can_transition_ticket_status()`. Invalid transitions return `409 Conflict` (`INVALID_STATUS_TRANSITION`).
- Entering `resolved` or `closed` statuses automatically records timestamps (`resolved_at`, `closed_at`).
- Ticket assignment is restricted to active members of the same organization holding `owner`, `admin`, or `agent` roles. Assigning to read-only `viewer` members or external users is rejected with `409 Conflict` (`INVALID_ASSIGNEE`).

### 7.4 Deterministic Conversation Sequencing & Idempotency
- Communication threads in `conversations` contain ordered `messages`.
- Messages are assigned a monotonic `sequence_number` per thread, and queries order by `(created_at ASC, sequence_number ASC, id ASC)` to ensure deterministic rendering.
- An optional `external_message_id` enforces delivery idempotency per organization, returning the existing record when duplicate provider deliveries occur.
- Plain text bodies are bounded to 65,536 bytes (64 KB). Author role impersonation (`system` or `ai`) by ordinary agents is blocked with `403 Forbidden`.

### 7.5 Atomic Lifecycle Audit Events
- Mutations (creation, status changes, priority changes, assignments, customer associations) emit immutable `TicketEvent` records within the identical database transaction.
- If an update payload specifies unchanged attributes, no redundant event is generated.
- Events capture previous values, new values, actor classification, user ID, and HTTP correlation IDs.

---

## 8. Reliable Event Ingestion, Webhook Reception & Background Worker Architecture (Phase 04)

### 8.1 Ingestion Subsystem Overview
SupportGPT AI ingests external customer support events across multiple providers (generic webhooks, Zendesk, Twilio, SendGrid) and applies them idempotently to canonical domain models (`Ticket`, `Conversation`, `Message`, `Customer`).

```mermaid
sequenceDiagram
    autonumber
    actor Provider as External Provider
    participant Edge as Webhook API Boundary
    participant DB as PostgreSQL (ingestion_receipts)
    participant Worker as Background IngestionWorker
    participant Processor as IngestionProcessor
    participant Domain as Domain Services (Tickets/Conversations)

    Provider->>Edge: POST /api/v1/webhooks/sources/{id} (HMAC signature, timestamp)
    Edge->>Edge: Verify Signature (constant-time HMAC-SHA256)
    Edge->>Edge: Validate Timestamp Replay Window (<= 300s)
    Edge->>DB: Check Deduplication (org_id, provider, external_event_id)
    alt Duplicate Event with Same Digest
        Edge-->>Provider: 200 OK (Duplicate Ignored)
    else Duplicate Event with Differing Digest
        Edge-->>Provider: 409 Conflict (Payload Digest Mismatch)
    else New Valid Event
        Edge->>DB: INSERT IngestionReceipt (status='queued', payload_digest)
        Edge-->>Provider: 202 Accepted (receipt_id, status='queued')
    end

    loop Asynchronous Processing Pass
        Worker->>DB: SELECT FOR UPDATE SKIP LOCKED (status IN ('queued', 'retry_wait'))
        Worker->>DB: UPDATE locked_by, processing_started_at, status='processing'
        Worker->>Processor: process_event(CanonicalEvent, receipt)
        Processor->>Domain: Resolve/Create Customer & Identities
        Processor->>Domain: Find/Create Ticket (external_reference)
        Processor->>Domain: Append Inbound Message (external_message_id)
        alt Success
            Processor->>DB: UPDATE IngestionReceipt (status='processed', processed_at=NOW())
        else Transient Error
            Worker->>DB: UPDATE status='retry_wait', next_attempt_at=NOW()+backoff
        else Fatal/Max Attempts Exceeded
            Worker->>DB: UPDATE status='dead_letter', error_code='...'
        end
    end
```

### 8.2 Inbound Security & Verification Boundary
1. **Constant-Time HMAC-SHA256**: Signatures are evaluated strictly over raw request bytes (`await request.body()`) and compared using `hmac.compare_digest` to prevent timing side-channel attacks.
2. **Replay Window Guard**: Enforces a strict 300-second (5-minute) clock skew threshold via `x-supportgpt-timestamp`. Requests older than 300 seconds are rejected with `400 Bad Request` (`TIMESTAMP_OUTSIDE_TOLERANCE`).
3. **Payload Size Bounds**: Requests exceeding 1 MB are terminated immediately with `413 Content Too Large` (`PAYLOAD_TOO_LARGE`).
4. **Media Type Validation**: Enforces `application/json`. Invalid payloads return `415 Unsupported Media Type` or `422 Unprocessable Content`.
5. **Secret Protection**: Source signing secrets are generated via `secrets.token_urlsafe(32)` prefixed with `whsec_`. Plaintext secrets are never stored in plain text; secrets are encrypted at rest via AES-CTR stream cipher with random IVs derived from `settings.signing_secret_encryption_key`. Public APIs expose only masked previews (e.g., `whsec_abc...`).

### 8.3 Durable Receipt State Machine
Accepted events progress through explicit, deterministic lifecycle states:

```mermaid
stateDiagram-v2
    [*] --> queued: Durable Webhook Acceptance (202 Accepted)
    queued --> processing: Worker Claims via FOR UPDATE SKIP LOCKED
    processing --> processed: Domain Mutations Committed Atomically
    processing --> retry_wait: Transient Failure (Attempt < Max)
    retry_wait --> processing: Backoff Expired, Re-claimed by Worker
    processing --> dead_letter: Fatal Error or Max Attempts (5) Exceeded
    processing --> quarantined: Ambiguous Identity or Schema Mismatch
    processing --> processing: Lease Timeout (> 300s) Reclaimed after Crash
    dead_letter --> queued: Authorized Operator Replay (Re-queued)
    processed --> [*]
```

### 8.4 Concurrency & Crash Recovery Guarantee
1. **Multi-Worker Claiming**: Workers execute transactional queries using PostgreSQL `FOR UPDATE SKIP LOCKED`. Concurrent worker threads claim completely disjoint batches of receipts with zero lock contention.
2. **Crash Recovery & Lease Expiration**: Jobs claimed by a worker stamp `locked_by` and `processing_started_at`. If a worker process crashes, abandoned jobs exceeding `lease_timeout_seconds` (default 300s) are automatically reclaimed on subsequent passes without operator intervention.
3. **Exponential Backoff with Jitter**: Retried receipts calculate next execution via `base * 2^(attempt - 1) + jitter`, bounded to a maximum backoff window.

### 8.5 Operational Inspection & Replay
- Restricted endpoints (`GET /api/v1/organizations/{org_id}/ingestion/receipts`, `POST .../replay`) require `ingestion:read` and `ingestion:manage` permissions.
- Replaying a failed event reuses the original durable receipt record and resets attempt counters rather than creating duplicate event records, preserving database deduplication constraints.

---

## 9. Known Limitations & Deferred Work (Out of Scope for Phase 04)
1. **AI Classification & Response Drafting**: LLM prompt pipelines, retrieval-augmented generation (RAG), and response verification are strictly deferred to Phase 05+.
2. **Outbound Customer Dispatch**: Automatic webhook replies or email dispatch are deferred.
3. **Email IMAP/SMTP Ingestion**: Specialized email polling and MIME attachments are deferred.
4. **Billing & Subscriptions**: Stripe/Paddle billing and seat quotas are deferred.


