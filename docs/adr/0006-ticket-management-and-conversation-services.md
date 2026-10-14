# ADR 0006: Ticket Management, Conversation Services, Concurrency Control & Lifecycle Audit Trail

## Status
Accepted

## Context
Phase 01 provided the canonical domain tables (`tickets`, `conversations`, `messages`, `ticket_events`, `attachments`, `customers`), and Phase 02 established authentication, session lifecycle, organization membership, and PostgreSQL Row-Level Security (RLS).

Phase 03 transforms these structural models into an operational, secure support ticket management backend. In a multi-tenant enterprise support SaaS, tickets, customer communications, agent notes, and lifecycle history require:
1. **Sequential Human-Readable Ticket Numbering**: Safe per-organization ticket numbering (e.g., `TICK-101`) without race conditions, duplicates, or gaps.
2. **Deterministic Message Ordering**: Conversations must present messages in exact chronological and sequence order without clock drift ambiguity.
3. **Optimistic Concurrency Control (OCC)**: Two support agents opening and updating the same ticket simultaneously must not overwrite each other's changes silently (lost update anomaly).
4. **Controlled Lifecycle Transitions**: Ticket status movements (`open` -> `in_progress` -> `resolved` -> `closed`) must adhere to strict domain state rules.
5. **Atomic Lifecycle Audit Trail**: Every status transition, priority change, assignment, and customer association must record a tamper-evident audit event within the same database transaction.
6. **Parent-Child Authorization & Tenant Scoping**: Child records (`conversations`, `messages`, `attachments`, `events`) must be validated against their parent ticket and organization boundary to prevent direct-ID access leakage.

## Decision

### 1. Concurrency-Safe Sequential Ticket Allocation
- Every organization maintains an atomic counter in `organization_ticket_counters`.
- During ticket creation, `allocate_next_ticket_number` locks the counter row using `SELECT ... FOR UPDATE` within the active transaction.
- Returns an incremented integer formatted as `TICK-{number}` guaranteed unique per organization.

### 2. Optimistic Concurrency Control (OCC)
- Added an integer column `lock_version` (default 1, non-nullable) to `tickets` via migration `0004_ticket_concurrency_version`.
- Mutating endpoints (`PATCH /api/v1/organizations/{org_id}/tickets/{ticket_id}`) accept an optional `lock_version`.
- If the supplied `lock_version` differs from the current database state, the operation is aborted immediately with `409 Conflict` (`CONCURRENCY_CONFLICT`).
- On successful mutation, `lock_version` increments by 1 atomically.

### 3. Centralized Lifecycle Transitions
- Status transitions are evaluated via `can_transition_ticket_status()`.
- Invalid transitions (e.g. `closed` -> `pending`) are rejected with `409 Conflict` (`INVALID_STATUS_TRANSITION`).
- Resolved and closed timestamps (`resolved_at`, `closed_at`) are automatically stamped by the domain service upon entering final states.

### 4. Assignment Eligibility Rules
- Assigning tickets requires `tickets:assign` permission.
- The target assignee must hold an active membership in the ticket's organization with `owner`, `admin`, or `agent` role.
- Read-only `viewer` members and non-organization actors are rejected with `409 Conflict` (`INVALID_ASSIGNEE`).

### 5. Deterministic Conversation Sequencing & Idempotency
- Messages inside a conversation are allocated an integer `sequence_number` (`MAX(sequence_number) + 1`).
- Queries order messages deterministically by `(created_at ASC, sequence_number ASC, id ASC)`.
- Inbound/external communications support an `external_message_id`. If an identical identifier is submitted within an organization, the existing record is returned idempotently to prevent duplicate delivery.

### 6. Atomic Audit Events
- Mutations create append-only `TicketEvent` records within the identical database transaction.
- If an update payload specifies unchanged attributes, no redundant event is generated.
- All events capture previous values, new values, executing actor ID, actor type (`agent`, `customer`, `system`), and HTTP correlation trace IDs.

### 7. Attachment Metadata Protection
- Endpoints return safe attachment metadata (`filename`, `content_type`, `size_bytes`, `scan_status`).
- Internal object storage keys (`storage_key`) and raw credentials are never exposed in public API contracts.

## Consequences

### Positive
- Prevents lost updates through database-enforced optimistic locking.
- Eliminates ticket counter collisions under high concurrent load.
- Provides complete operational auditability for every ticket modification.
- Enforces multi-tenant isolation across all parent-child relationships.

### Negative / Trade-offs
- Clients must handle `409 Conflict` responses and reload state when concurrent modifications occur.
- Additional database rows written per mutation to record audit events.
