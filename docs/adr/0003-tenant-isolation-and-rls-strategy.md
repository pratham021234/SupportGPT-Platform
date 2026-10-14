# ADR 0003: Multi-Tenancy Architecture and PostgreSQL Row-Level Security (RLS) Strategy

## Status
Proposed (Scheduled for Phase 02 Execution)

## Date
2026-10-14

## Context
SupportGPT AI is a multi-tenant B2B SaaS platform serving distinct enterprise organizations. A catastrophic risk in B2B customer support is cross-tenant data leakage (e.g. Organization A retrieving Organization B's customer tickets, knowledge base documents, or LLM audit traces). 

Relying solely on application-level filtering (e.g. `WHERE organization_id = :org_id` in developer queries) is brittle and prone to human error, regression leaks, or developer omission during complex joins.

## Architectural Decision (For Phase 02)
1. **PostgreSQL Row-Level Security (RLS)** will be enforced directly at the database engine level for all organization-scoped tables.
2. Every tenant entity will include a non-nullable `organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE`.
3. An RLS policy will be applied to every organization-scoped table:
   ```sql
   ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
   CREATE POLICY tenant_isolation_policy ON conversations
     AS RESTRICTIVE
     USING (organization_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
   ```
4. **Transaction-Local Tenant Context Establishment**:
   - The tenant context is NEVER authorized based on an untrusted query parameter or request body payload provided by the client.
   - Authentication middleware in Phase 02 validates the cryptographically signed JWT / session token, extracts the authenticated user identity, checks active membership against verified database roles, and resolves the authoritative `organization_id`.
   - Before handing the database session to application handlers, the session executes a transaction-local setting:
     ```sql
     SET LOCAL app.current_tenant_id = 'c5a45659-...';
     ```
   - Because `SET LOCAL` is scoped strictly to the current database transaction, connection pool reuse does not risk leaking tenant context across requests.
5. **Quality Gate**:
   - Multi-tenant isolation will NOT be declared complete until Phase 02 adversarial tests (attempting to bypass tenant filters with tampered headers and direct SQL access) are executed and verified.

## Consequences
### Positive
- Defense-in-depth: Even if application code omits an explicit tenant filter, PostgreSQL denies access to rows belonging to other tenants.
- Clean application queries without redundant where clauses.
- Tamper-proof: Clients cannot spoof tenant IDs.

### Negative
- Local migration runners and superuser roles bypass RLS by default; test fixtures must run under a non-superuser application role to validate RLS policies.
