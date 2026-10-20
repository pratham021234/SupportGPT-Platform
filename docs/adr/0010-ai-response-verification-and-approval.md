# ADR 0010: AI Response Verification, Policy Enforcement & Human Approval

## Status
Accepted

## Context
SupportGPT AI platform generates customer support replies through retrieval-augmented generation (RAG) and AI provider abstractions. However, enterprise customer support carries strict fiduciary, legal, and operational risks. AI responses must not be sent directly to customers without passing structured safety and policy checks.

The objective is not merely to ask an LLM whether another LLM's response looks correct. The platform requires a structured verification pipeline with explicit rules, evidence references, policy evaluation, risk classification, approval requirements, durable state transitions, and an auditable human decision process:
1. **Verification is not a guarantee**: Passing verification means the response passed configured checks; it does not guarantee universal correctness.
2. **Evidence must be traceable**: Factual claims about refunds, warranties, account limits, and SLAs must be grounded in authorized retrieved evidence chunks.
3. **Policies are explicit and deterministic**: Critical rules (keyword prohibition, required disclaimers, maximum length, unsupported claim blocks) must be enforced deterministically, not solely by an LLM.
4. **Human approval is a real workflow**: Responses requiring approval must be explicitly reviewed and authorized by an authenticated user with appropriate permissions.
5. **Exact draft version binding**: Editing a response draft increments its version number and automatically invalidates any prior approval requests.
6. **Separation of duties**: A team member who authored or submitted a draft cannot self-approve their own response under separation-of-duties enforcement.
7. **Append-only audit trail**: All workflow events (draft creation, revisions, verification runs, approval requests, approvals, rejections, invalidations) are persisted in an append-only audit log.
8. **Multi-tenant isolation**: Every draft, verification run, claim finding, policy rule, approval request, and audit event is strictly isolated by `organization_id` with PostgreSQL Row-Level Security (RLS).

---

## Decision

### 1. Canonical Domain Model & PostgreSQL RLS
Introduced 6 new models in `backend/app/models/` and Alembic migration `0007_response_verification`:
- **`ResponseDraft` (`response_drafts`)**: Represents an AI-generated support response candidate. Tracks `organization_id`, `ticket_id`, `conversation_id`, `original_query`, `draft_text`, `version_number`, `lifecycle_status` (`draft`, `verification_pending`, `verified`, `verification_failed`, `approval_pending`, `approved`, `revision_required`, `rejected`, `superseded`), `evidence_references`, and author.
- **`VerificationRun` (`verification_runs`)**: Captures an execution of the verification pipeline for a specific draft version. Stores `verification_pipeline_version`, `policy_set_version`, `status` (`passed`, `passed_with_warnings`, `needs_revision`, `blocked`, `failed`), `risk_level` (`low`, `medium`, `high`, `critical`), `requires_human_approval`, `machine_readable_findings`, and execution latency.
- **`ClaimFinding` (`claim_findings`)**: Atomic claim breakdown recording `claim_text`, `claim_category` (`policy`, `pricing_refund`, `sla_commitment`, `product_fact`, `general`), `support_status` (`supported`, `partially_supported`, `unsupported`, `contradicted`, `not_verifiable`), `evidence_chunk_ids`, `confidence_score`, `reason`, and `verification_method`.
- **`PolicyRule` (`policy_rules`)**: Declarative organizational safety policies. Captures `policy_category`, `severity` (`low`, `medium`, `high`, `critical`), `rule_type` (`unsupported_claim_block`, `keyword_prohibition`, `required_phrase`, `max_length`, `refund_limit`, `mandatory_approval_on_risk`), JSON `rule_config`, `is_enabled`, and version number.
- **`ApprovalRequest` (`approval_requests`)**: Manages human review lifecycle. Binds to exact `draft_id` and `draft_version`. Captures `required_role`, `separation_of_duties`, `status` (`pending`, `approved`, `rejected`, `revision_requested`, `invalidated`, `cancelled`), `requested_by_user_id`, `decision_by_user_id`, `decision_reason`, and `decided_at`.
- **`VerificationAuditEvent` (`verification_audit_events`)**: Append-only audit record capturing event type, entity ID, actor ID, request ID, event summary, and metadata JSON.
- **PostgreSQL Row-Level Security (RLS)**: Enforced `FOR ALL` policies with `FORCE ROW LEVEL SECURITY` across all 6 tables, validating `organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid OR current_setting('app.is_system_admin', true) = 'true'`.

### 2. Claim Extraction & Evidence Grounding Engine
Implemented in `backend/app/services/verification/`:
- **`ClaimExtractor`**: Decomposes response drafts into atomic declarative propositions, strips conversational salutations and pleasantries ("Hello", "Thanks for reaching out"), and classifies claims into domain categories.
- **`EvidenceGrounder`**: Compares claims against retrieved evidence chunks using word/token overlap and keyword alignment. Detects direct documentary contradictions (e.g. drafting promises of "100% unconditional refund" when policy states "non-refundable"). Identifies unsupported material assertions when evidence is missing.

### 3. Declarative Versioned Policy Engine
Implemented in `backend/app/services/verification/policy_evaluator.py`:
- Evaluates declarative policy rules (`keyword_prohibition`, `required_phrase`, `max_length`, `refund_limit`, `unsupported_claim_block`, `mandatory_approval_on_risk`).
- Executes deterministic evaluation independent of LLM judgment.
- Evaluates baseline safety rules (unsupported material claims and refund commitments) even if no custom organizational policies are active.

### 4. Verification Pipeline & Disposition Calculation
Implemented in `backend/app/services/verification/pipeline.py`:
- Deterministic disposition calculation:
  - Any critical policy failure or contradicted claim &rarr; `BLOCKED`, `CRITICAL` risk, mandatory approval flag.
  - Any high-severity policy failure or unsupported material claim &rarr; `NEEDS_REVISION`, `HIGH` risk, mandatory approval flag.
  - Any medium-severity policy failure or partially supported claim &rarr; `PASSED_WITH_WARNINGS`, `MEDIUM` risk.
  - Clean evidence corroboration with zero policy violations &rarr; `PASSED`, `LOW` risk.
- Generates structured, machine-readable findings and diagnostic summary.

### 5. Durable Human Approval Workflow & Separation of Duties
Implemented in `backend/app/services/verification/approval_service.py`:
- **Role Enforcement**: Requires `VERIFICATION_APPROVE` permission (granted to `agent`, `admin`, `owner`).
- **Separation of Duties**: When `separation_of_duties` is active, the requesting user cannot self-approve (`SelfApprovalForbiddenException`, HTTP 403).
- **Exact Version Binding**: Before committing an approval decision, verifies `draft.version_number == approval_req.draft_version`. If the draft was updated, rejects with `StaleDraftApprovalException` (HTTP 409) and invalidates the request.
- **Revision Invalidation**: Calling `revise_response_draft` automatically increments draft version and invalidates all prior pending/approved approval requests for that draft.

### 6. Strict Scope Boundaries
- Zero automatic sending of customer emails or messages.
- Zero autonomous customer support actions or tool calling.
- Verification and approval are strictly governance and trust layers.

---

## Consequences

### Positive
- AI responses cannot be marked safe-to-send if they contain contradicted or unsupported factual assertions.
- Separation of duties is enforced at the server level, preventing self-approval by rogue or mistaken agents.
- Full auditability: every claim evaluation, policy version, and approval decision is immutably recorded in PostgreSQL.
- Multi-tenant isolation is enforced at both application layer (RBAC) and database layer (PostgreSQL RLS).

### Limitations & Deferred Capabilities
- Outbound customer messaging and email dispatch are strictly deferred to future phases.
- Real-time LLM calibration scoring is not implemented; confidence scores represent heuristic grounding metrics.
