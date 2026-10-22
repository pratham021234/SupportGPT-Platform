# SupportGPT AI Platform - Threat Model & Security Architecture

## 1. Executive Summary

This document establishes the security architecture and STRIDE threat analysis for the **SupportGPT Multi-Tenant AI Support Operations Platform**.

SupportGPT handles proprietary enterprise customer knowledge, support conversations, and automated AI generation. As a multi-tenant platform, tenant boundary isolation, cryptographic integrity, and prompt safety are primary security objectives.

---

## 2. System Boundaries & Trust Zones

```
+----------------------------------------------------------------------------------+
| Public / Untrusted Zone                                                          |
| - External Webhook Senders (Stripe, Zendesk, Email gateways)                     |
| - Customer Support End-Users                                                     |
| - Authenticated Tenant Operators (Browsers)                                      |
+----------------------------------------------------------------------------------+
                                        │
                                        │ TLS 1.3 / HTTPS
                                        ▼
+----------------------------------------------------------------------------------+
| Edge DMZ (Nginx Reverse Proxy)                                                   |
| - Rate Limiting & SSL Termination                                                |
| - HTTP Security Headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options)     |
| - Body Size Enforcement (25MB max)                                               |
+----------------------------------------------------------------------------------+
                                        │
                                        │ Internal Docker Network (Isolated)
                                        ▼
+----------------------------------------------------------------------------------+
| Application Zone (Least Privilege Containers)                                    |
| - Next.js 15 Frontend (Non-root 'nextjs' UID 1001)                               |
| - FastAPI Backend API (Non-root 'appuser' UID 10001, Multi-worker ASGI)          |
| - Background Ingestion & Document Workers (Dedicated Container, Non-root)       |
+----------------------------------------------------------------------------------+
                                        │
                         ┌──────────────┴──────────────┐
                         ▼                             ▼
+----------------------------------+         +-------------------------------------+
| Data Tier (Restricted Storage)   |         | External AI Services                |
| - PostgreSQL 16 (RLS Enforced)   |         | - OpenAI API (TLS 1.3)              |
| - Redis 7 (Authenticated)        |         | - Anthropic API (TLS 1.3)           |
| - Qdrant Vector Store (Private)  |         +-------------------------------------+
+----------------------------------+
```

---

## 3. STRIDE Threat Analysis

### 3.1: Spoofing (Identity Deception)
| Threat | Impact | Implemented Mitigations | Verification Status |
|---|---|---|---|
| Credential Brute-Forcing | Account takeover | `InMemoryRateLimiter` enforces sliding-window limit (5 attempts / 60s); returns HTTP 429. | **Verified** by unit & API integration tests |
| User Enumeration via Timing Side-Channels | Attacker learns valid user emails | Constant-time dummy Argon2id hash verification (`_DUMMY_ARGON2_HASH`) executed when user not found. | **Verified** |
| Session Hijacking | Attacker steals cookie | `HttpOnly=True`, `Secure=True` (strictly enforced in production), `SameSite=Lax`, and sliding window session invalidation. | **Verified** |
| Webhook Sender Impersonation | False events injected into queue | Cryptographic HMAC-SHA256 signature verification over raw request payloads with configurable clock skew tolerance (300s). | **Verified** |

### 3.2: Tampering (Data Modification)
| Threat | Impact | Implemented Mitigations | Verification Status |
|---|---|---|---|
| Cross-Tenant Data Modification | One tenant edits another's documents | PostgreSQL 16 Row-Level Security (`FORCE ROW LEVEL SECURITY`) with `SET LOCAL app.current_organization_id = ...` enforced in every database transaction. | **Verified** by cross-tenant tests |
| Document Chunk Modification | Inconsistent or falsified retrieval content | Immutable versions; SHA-256 checksum calculated on upload and for every individual chunk. | **Verified** |
| Corrupted or Tampered Database Backups | Malicious restoration into production | `restore_database.py` recalculates SHA-256 digest and verifies `.sha256` checksum before running `pg_restore`. | **Verified** by unit tests |
| Race Conditions in Migrations | Inconsistent schema or partial migration state | `run_migrations.py` acquires 64-bit PostgreSQL session advisory lock (`847291038`) before executing Alembic. | **Verified** |

### 3.3: Repudiation (Disavowing Actions)
| Threat | Impact | Implemented Mitigations | Verification Status |
|---|---|---|---|
| Denying Approval of AI Response | Operator denies publishing sensitive response | Append-only `ApprovalRequest` entity logging reviewer user ID, source version ID, timestamp, and review status. | **Verified** |
| Unaudited Configuration Changes | Unknown source of policy edits | Comprehensive `AuditEvent` records capture actor, organization, resource ID, action, and JSON diffs. | **Verified** |
| Denial of Retrieval Origin | Disputing where AI acquired factual claims | Atomic claims linked to exact chunk IDs and heading breadcrumbs in `ClaimGroundingResult`. | **Verified** |

### 3.4: Information Disclosure (Data Leakage)
| Threat | Impact | Implemented Mitigations | Verification Status |
|---|---|---|---|
| Cross-Tenant Retrieval in RAG | Customer sees competitor support docs | Qdrant vector queries strictly include `organization_id` filter; raw chunk text retrieved from PostgreSQL via RLS session. | **Verified** by tenant isolation tests |
| Secret Leakage into Logs | API keys, passwords exposed in log streams | Multi-pattern centralized redaction (`redact_sensitive_data`) in `logging.py` scrubs JWTs, OpenAI keys, bearer tokens, passwords, and PII before JSON emission. | **Verified** |
| Debug Mode Leakage | Stack traces & env vars exposed to browsers | Production invariant validator strictly blocks startup if `DEBUG=True` in staging or production. | **Verified** |
| Container Filesystem Inspection | Attacker reads secrets in image layers | Zero committed secrets; secrets injected exclusively via environment variables; multi-stage Docker builds. | **Verified** |

### 3.5: Denial of Service (Resource Exhaustion)
| Threat | Impact | Implemented Mitigations | Verification Status |
|---|---|---|---|
| Oversized File Uploads | Server disk or RAM exhaustion | Edge proxy enforces 25MB body limit; backend validates content lengths and media types before streaming to disk. | **Verified** |
| Worker Process Hangs | Ingestion pipeline stalls indefinitely | Ingestion and Document workers enforce lease timeouts (300s). Stale leases are automatically reclaimed. | **Verified** |
| Poison Pill Document Extraction | Infinite loop in document parser | Worker increments attempt counters; failures beyond 5 retries move to `dead_letter` / `failed` status with failure investigation (`INV-XXXXXX`). | **Verified** |
| Database Connection Starvation | Web server exhausts database connections | Bounded connection pool (`DB_POOL_SIZE=20`, `DB_MAX_OVERFLOW=10`, `DB_POOL_TIMEOUT=30s`). | **Verified** |

### 3.6: Elevation of Privilege
| Threat | Impact | Implemented Mitigations | Verification Status |
|---|---|---|---|
| Viewer Approving AI Drafts | Unauthorized response sent to customer | Role-based access control (`MembershipRole`) strictly enforced: only `OWNER`, `ADMIN`, or `AGENT` can approve or edit drafts. | **Verified** |
| Direct Object ID Access (IDOR) | User guesses UUID of another tenant's ticket | Every query joins on `organization_id`; backend validates tenant membership before returning entity. | **Verified** |
| Container Breakout | Attacker gains host root access | Containers run under unprivileged service users (`appuser` UID 10001, `nextjs` UID 1001) with `no-new-privileges`. | **Verified** |

---

## 4. AI-Specific Security: Prompt Injection & Grounding

SupportGPT implements layered defense-in-depth against prompt injection and model hallucinations:

1. **System Prompt Segregation:** Knowledge context is clearly encapsulated in structured markdown blocks rather than concatenated directly with user instructions.
2. **Deterministic Response Verification:** Even if an LLM is manipulated by an adversarial prompt, the output draft must undergo **Atomic Claim Extraction** (`ClaimExtractor`) and **Policy Rule Evaluation** (`PolicyEvaluator`):
   - Prohibited topics, unauthorized promises (e.g. ungrounded refund guarantees or SLA claims), and missing citations automatically flag the draft as `FAILED` or `NEEDS_APPROVAL`.
   - Direct transmission to end customers is strictly blocked pending human review.
3. **No Autonomous External Actions:** AI cannot trigger external financial transactions, email dispatches, or webhooks without explicit, authenticated human intervention.
