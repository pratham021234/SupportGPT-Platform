# ADR 0007: Reliable Event Ingestion, Webhook Verification, Deduplication, and Background Worker Architecture

## Status
Accepted

## Context
SupportGPT AI must ingest high-volume support events from external channels (generic webhooks, Zendesk, SendGrid, Twilio, Slack) and normalize them into SupportGPT's canonical domain model (`Ticket`, `Conversation`, `Message`, `Customer`).

External webhooks present critical reliability and security challenges:
1. **At-Least-Once Delivery**: Providers retry aggressively upon network timeouts, resulting in frequent duplicate deliveries.
2. **Payload Mismatch on Retried Identifiers**: Providers may resend an existing event ID with differing payloads or corrupted bytes.
3. **Slow Domain Mutations**: Processing inbound events involves customer resolution, ticket lookups, database sequence counter allocation, and audit events. A synchronous webhook handler could cause upstream timeouts and duplicate cascade storms.
4. **Secret Management & Cryptographic Boundaries**: Inbound requests must be authenticated via cryptographic signatures (HMAC-SHA256) and replay timestamp windows. Signing secrets must never be committed, returned in API responses, or stored in plain text.
5. **Worker Crashes & Concurrency**: Multiple background workers must claim pending events without lock contention or duplicate execution (`FOR UPDATE SKIP LOCKED`). If a worker crashes mid-processing, abandoned leases must be reclaimed automatically without human intervention.
6. **Multi-Tenant Isolation**: Event sources, inbound receipts, and replay operations must be strictly scoped to their owning organization and enforced at both the API level and PostgreSQL Row-Level Security (RLS).

## Decision

### 1. Database-Backed Outbox / Event Receipts as Durable Source of Truth
- PostgreSQL serves as the authoritative, durable system of record for accepted events via the `ingestion_receipts` table.
- Webhook endpoints durably insert an `IngestionReceipt` record before responding.
- An HTTP `202 Accepted` response indicates durable acceptance into PostgreSQL queue state (`queued`), NOT domain completion.
- Duplicate deliveries of previously received events return HTTP `200 OK` idempotently with `"action": "duplicate_receipt_ignored"`.
- If an event arrives with an existing `(organization_id, source_provider, external_event_id)` but a mismatched payload SHA-256 digest, the request is rejected immediately with HTTP `409 Conflict` (`PAYLOAD_DIGEST_MISMATCH`).

### 2. Provider Source Configuration & Symmetric Secret Protection
- Created `event_sources` table scoped to `organization_id` with status tracking (`active`, `inactive`, `revoked`).
- Signing secrets are generated with high entropy (`secrets.token_urlsafe(32)` prefixed with `whsec_`).
- In API responses, secrets are masked (`signing_secret_preview`, e.g. `whsec_abc...`).
- When stored in the database, secrets are encrypted at rest using AES-CTR-mode stream cipher with per-secret random IVs derived from `settings.signing_secret_encryption_key`.
- Secret hashes (`SHA-256`) are stored for rapid indexing without revealing plaintext secret material.
- Secure rotation is supported via dedicated endpoints (`POST /api/v1/organizations/{org_id}/sources/{source_id}/rotate-secret`).

### 3. Webhook Cryptographic Verification Boundary
- Verified via `WebhookVerifier`:
  - **HMAC-SHA256**: Calculated strictly over raw request bytes (`await request.body()`) and compared in constant time (`hmac.compare_digest`).
  - **Replay Window**: Enforces a 300-second (5-minute) maximum clock-skew window via `x-supportgpt-timestamp` or equivalent provider header.
  - **Payload Limits**: Requests exceeding 1 MB (`MAX_WEBHOOK_PAYLOAD_BYTES`) are rejected immediately with HTTP `413 Content Too Large`.
  - **Content Type**: Requires `application/json`. Invalid payloads are rejected with HTTP `415 Unsupported Media Type` or `422 Unprocessable Content`.

### 4. Canonical Event Normalization
- Decouples external provider formats from domain entities through `EventNormalizer` and provider-specific adapters (`StandardWebhookAdapter`).
- Normalizes external payloads into strongly typed `CanonicalEvent` schemas:
  - `external_event_id`, `event_type`, `provider`, `event_timestamp`
  - `external_ticket_id`, `external_conversation_id`, `external_message_id`
  - `customer` (`email`, `external_id`, `name`)
  - `subject`, `message_body`, `priority`
  - `metadata` (sanitized dictionary)

### 5. Transactional Background Worker (`FOR UPDATE SKIP LOCKED`)
- Implemented `IngestionWorker` operating independently of HTTP request handlers.
- **Job Claiming**:
  ```sql
  SELECT id FROM ingestion_receipts
  WHERE status IN ('queued', 'retry_wait')
    AND next_attempt_at <= NOW()
  ORDER BY received_at ASC
  LIMIT :batch_size
  FOR UPDATE SKIP LOCKED;
  ```
  - Multiple concurrent worker processes claim completely disjoint batches of receipts with zero lock contention.
- **Crash Recovery & Lease Reclamation**:
  - Worker acquires a lease stamping `locked_by` (worker instance identifier) and `processing_started_at`.
  - If a worker crashes, any job in `processing` status exceeding `lease_timeout_seconds` (default 300s) is automatically reclaimed on subsequent passes.
- **Backoff & Retries**:
  - Transient errors trigger exponential backoff with jitter up to `max_attempts` (default 5).
  - Failed receipts enter `retry_wait` until `next_attempt_at`.
  - Exhausted attempts or fatal validation errors transition to `dead_letter` or `quarantined`.

### 6. Idempotent Domain Mapping (`IngestionProcessor`)
- Normalized events are applied to domain entities:
  - **Customer Resolution**: Resolves existing `CustomerIdentity` by normalized email or external provider ID. If not found, provisions a new `Customer` and `CustomerIdentity` transactionally.
  - **Ticket Creation**: Evaluates `external_reference`. If a ticket with that external reference exists within the organization, reuses the existing ticket instead of creating duplicates.
  - **Message Ingestion**: Appends to the ticket conversation. Deduplicates on `external_message_id` to prevent message replication during worker retries.
  - **Ticket Status & OCC**: Updates ticket status and increments `lock_version` safely, recording atomic `TicketEvent` audit entries.

### 7. Restricted Operational APIs & Safe Replay
- Authorized operators with `ingestion:manage` permission can query failed events, view sanitized error summaries, and trigger safe replays (`POST /api/v1/organizations/{org_id}/ingestion/receipts/{receipt_id}/replay`).
- Replay reuses the durable receipt identity and transitions it back to `queued` with reset attempt counts, preserving deduplication invariants and preventing synthetic domain duplicates.

## Consequences

### Positive
- Strict separation between durable acceptance (HTTP 202) and asynchronous domain execution.
- High-throughput horizontal worker scaling without distributed lock managers (PostgreSQL `FOR UPDATE SKIP LOCKED`).
- Complete idempotency across duplicate deliveries and worker crash recoveries.
- Strong cryptographic boundary preventing spoofed or replayed webhook payloads.
- Multi-tenant isolation enforced continuously through application queries and PostgreSQL RLS.

### Trade-offs & Limitations
- Worker batch claiming relies on PostgreSQL transactional concurrency. In SQLite testing environments, a fallback locking strategy is utilized.
- Redis was evaluated for accelerated queue dispatch; however, durable PostgreSQL-backed queueing was prioritized to eliminate data loss upon Redis failover. Redis remains optional for acceleration.
- Raw provider payload digests are retained for deduplication; raw personal data retention should be bounded by scheduled privacy cleanup jobs in future phases.
