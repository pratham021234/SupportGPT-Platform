# ADR 0004: Canonical Domain Model, Organization-Scoped Identifiers & Composite Foreign Key Tenant Boundaries

## Status
Accepted

## Date
2026-10-14

## Context
SupportGPT AI requires a normalized domain foundation for customer support operations across multiple tenant organizations. In complex support workflows, interaction threads (`Conversation`), individual communications (`Message`), files (`Attachment`), and audit entries (`TicketEvent`) are created under a parent `Ticket`. 

In multi-tenant relational schemas, two acute data integrity risks arise:
1. **Cross-Tenant Entity Association**: Application code or service handlers associating a child record (e.g. a Message or Conversation) with an Organization ID different from that of its parent Ticket. Relying solely on application-layer validation is brittle.
2. **Cascading Destructive Operations**: Unrestricted foreign key cascades (`ON DELETE CASCADE`) on `organizations` or `customers` could accidentally wipe out active support cases, historical interactions, and immutable audit logs.
3. **Sequential Ticket Race Conditions**: Allocating human-readable ticket references using `SELECT MAX(ticket_number) + 1` causes race conditions under concurrent ticket creation.

## Decision
1. **Composite Foreign Keys for Database-Enforced Tenant Consistency**:
   - `tickets` declares `UNIQUE (id, organization_id)`.
   - `conversations` declares `FOREIGN KEY (ticket_id, organization_id) REFERENCES tickets(id, organization_id)`.
   - `messages` declares `FOREIGN KEY (conversation_id, organization_id) REFERENCES conversations(id, organization_id)`.
   - `attachments` declares `FOREIGN KEY (message_id, organization_id) REFERENCES messages(id, organization_id)`.
   - `ticket_events` declares `FOREIGN KEY (ticket_id, organization_id) REFERENCES tickets(id, organization_id)`.
   - This architectural pattern ensures that it is physically impossible at the PostgreSQL engine level for any child record to point to a parent belonging to a different tenant organization.

2. **Explicit Deletion Safeguards (`ON DELETE RESTRICT`)**:
   - Deleting an `Organization` that contains active `customers`, `tickets`, `conversations`, or `ticket_events` is blocked via `ON DELETE RESTRICT`. Historical records are protected from accidental wholesale deletion.
   - Deleting a `Customer` sets `tickets.customer_id` to `NULL` (`ON DELETE SET NULL`) to preserve the ticket history.
   - Dependent `CustomerIdentity` records cascade with customer deletion (`ON DELETE CASCADE`) because they form part of the customer contact aggregate.

3. **Transactional Atomic Ticket Sequence Allocation**:
   - Sequential ticket numbers are generated via an atomic counter table `organization_ticket_counters(organization_id, next_ticket_number)`.
   - The sequence increment is performed within the transaction boundary using row-level locking (`SELECT FOR UPDATE`), guaranteeing strictly increasing, gap-free ticket numbers under concurrent ingestion.

4. **Inbound Event Idempotency**:
   - `IngestionReceipt` enforces a unique constraint on `(organization_id, source_provider, external_event_id)` to recognize and deduplicate external provider deliveries before processing.

## Consequences
### Positive
- Strict, database-enforced multi-tenant consistency independent of application query correctness.
- Complete auditability and preservation of customer support history.
- Concurrency-safe ticket numbering without distributed locking overhead.

### Negative
- Composite foreign keys require composite unique constraints on parent tables (`UNIQUE (id, organization_id)`), adding slight indexing overhead.
- Query joins must include composite keys when navigating parent-child relationships.
