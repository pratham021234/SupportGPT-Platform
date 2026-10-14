# ADR 0005: Production Authentication, Organization Membership, RBAC & Tenant Isolation

## Status
Accepted

## Context
SupportGPT AI is a multi-tenant B2B AI customer support platform. Securing tenant data requires a server-enforced, tamper-proof authentication and authorization foundation. Client-supplied headers, request bodies, or user IDs must never serve as authorization authority. The platform requires:
1. Secure user account management with modern cryptographic password hashing.
2. Server-managed, instantly revocable sessions with HttpOnly cookies and bearer token fallback for API consumers.
3. Multi-tenant organization membership linking users to workspaces with granular roles.
4. Centralized, explicit Role-Based Access Control (RBAC) adhering to least privilege.
5. Strict request-level tenant authorization and database-enforced row-level security (RLS).
6. Prevention of privilege escalation, unauthorized self-promotion, and last-owner abandonment.

## Decision

### 1. Password Security
- **Algorithm**: Argon2id (`argon2-cffi`), configured with memory cost 64MB (65536 KiB), time cost 3 iterations, parallelism 4 threads.
- **Verification**: Constant-time verification with automatic dummy hashing on non-existent accounts to eliminate user enumeration side-channels.
- **Email Normalization**: Strict lowercase, whitespace-trimmed canonicalization prior to database lookups or constraints.

### 2. Session Architecture
- **Storage**: Server-side revocable session table (`user_sessions`) indexed on SHA-256 token hashes (`session_token_hash`).
- **Token Entropy**: 256-bit cryptographically secure random opaque tokens generated via `secrets.token_urlsafe(32)`. Raw tokens are never stored in the database.
- **Transport**:
  - Web Browsers: Secure `HttpOnly`, `SameSite=Lax` cookie (`supportgpt_session`).
  - API Clients: `Authorization: Bearer <token>` header support.
- **Lifecycle & Invalidation**: Immediate server-side revocation on `/api/v1/auth/logout`. Automatic expiration enforcement after 7 days (`SESSION_DURATION_SECONDS`).

### 3. Organization Membership & Centralized RBAC
- **Roles**:
  - `owner`: Full organizational control, billing, member provisioning, and ownership transfer.
  - `admin`: Member invitation/management (except owners), operational ticket and customer oversight.
  - `agent`: Operational support actions (read/write tickets and customers, assign tickets).
  - `viewer`: Read-only operational oversight.
- **Protections**:
  - **No Insecure Default Admin**: Provisioned via secure seeding or operational bootstrap CLI.
  - **Escalation Prevention**: Only `owner` can assign `owner` or `admin` roles. `admin` cannot grant `owner` or promote peers.
  - **Last-Owner Protection**: Demoting or revoking the final active owner in an organization is blocked with `403 Forbidden`.
  - **Membership Lifecycle**: Suspended or revoked memberships immediately terminate access to organizational endpoints.

### 4. Tenant Isolation & PostgreSQL RLS
- **Dual-Layer Enforcement**:
  1. **Application-Layer**: `OrganizationContext` dependency verifies active caller membership in the target organization. All data access occurs via `TenantScopedQuery` which unconditionally appends `WHERE organization_id = :org_id`.
  2. **Database-Layer**: PostgreSQL Row-Level Security (RLS) enabled with `FORCE ROW LEVEL SECURITY` on all tenant-owned tables (`tickets`, `conversations`, `messages`, `attachments`, `ticket_events`, `customers`, `customer_identities`).
- **Transaction-Local Isolation**: Context is established via `SELECT set_config('app.current_organization_id', :org_id, true)`. The `is_local=true` flag ensures the setting automatically reverts on commit or rollback, guaranteeing connection pool hygiene.

## Consequences

### Positive
- Strict defense-in-depth: Even if an application bug omits a `WHERE` clause, PostgreSQL RLS prevents cross-tenant data leakage.
- Opaque session tokens and SHA-256 storage prevent credential theft in the event of database snapshots.
- Privilege escalation and self-promotion are structurally impossible through centralized authorization dependencies.
- Constant-time password verification prevents timing-based account enumeration attacks.

### Negative / Trade-offs
- Setting transaction-local configuration adds lightweight overhead per transaction when using RLS.
- In-memory SQLite test harnesses in unit tests must rely on foreign-key cascades and `TenantScopedQuery`, while live PostgreSQL integration tests verify RLS policies directly.
