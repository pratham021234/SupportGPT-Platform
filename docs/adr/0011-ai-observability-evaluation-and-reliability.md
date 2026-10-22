# ADR 0011: AI Observability, Benchmark Evaluations, Failure Investigations, and Reliability Hardening

## Status
Accepted

## Context
In Phase 07, SupportGPT introduced structured response verification, deterministic policy enforcement, and auditable human approval workflows. While verification decisions were strictly recorded in append-only audit tables, the platform lacked an enterprise observability and evaluation framework capable of answering:
1. **Lifecycle & Span Decomposition:** Which processing stages executed during an AI request (embedding, vector retrieval, reranking, LLM generation, claim verification, policy evaluation), and where did latency bottlenecks occur?
2. **Failure Classification & Deduplication:** When an operation fails or abstains, what was the underlying category (e.g. `embedding_failure`, `no_relevant_evidence`, `policy_violation`), and how can thousands of repeated errors be deduplicated into actionable operator investigations without flooding the on-call team?
3. **Reproducible Benchmark Evaluations:** How do retrieval and answer quality change across code or model updates? How can operators detect precision regressions (Recall@k, MRR, citation validity, abstention accuracy) using versioned test datasets before promoting releases?
4. **Token Consumption & Cost Accounting:** What is the per-tenant and per-operation token usage and dollar cost, cleanly distinguishing actual provider-reported tokens from inferred baseline estimates?
5. **Non-blocking Deep Diagnostics:** How can operators probe PostgreSQL, Redis, Qdrant, worker loops, and embedding models without triggering costly paid external LLM calls or risking cascading health probe failures?
6. **Privacy & Centralized Redaction:** How can sensitive credentials (passwords, JWTs, Bearer tokens, OpenAI API keys, credit cards, SSNs, database URLs) be systematically scrubbed from structured log streams before emission?

## Decision
We implemented a unified, standards-compliant observability and evaluation architecture in `backend/app/services/observability/` backed by PostgreSQL 16 Row-Level Security, Alembic migration `0008_ai_observability`, and an interactive Next.js operator console.

### 1. Four Pillars of Observability
The architecture rigorously separates four operational concepts without data duplication:
- **Logs:** Structured RFC 5424 JSON logs with centralized pre-emission redaction (`StructuredJsonFormatter`), propagating `request_id`, `trace_id`, and `organization_id` context variables.
- **Metrics:** Real execution counters, span latencies, retrieval document counts, and token tallies computed directly from database records.
- **Traces:** Logical operation records (`AIOperationTrace`) storing execution stage spans (`spans` JSONB array), token counts, estimated costs, and correlation references.
- **Investigations:** Deduplicated failure records (`FailureInvestigation`) grouping recurrent errors under stable SHA-256 fingerprints (`INV-XXXXXX`) with diagnostic hypotheses and resolution workflows.

### 2. Centralized Multi-Pattern Redaction
Centralized in `backend/app/core/logging.py`, `redact_sensitive_data` recursively filters payloads before they reach log formatters or storage:
- **Key-Based Redaction:** Automatically masks case-insensitive sensitive keys: `password`, `token`, `secret`, `authorization`, `api_key`, `access_token`, `refresh_token`, `cookie`, `credit_card`, `ssn`.
- **String Pattern Redaction:** Applies high-precision regular expressions detecting:
  - `Bearer [A-Za-z0-9_\-\.]+` -> `Bearer [REDACTED_TOKEN]`
  - `sk-[A-Za-z0-9]{20,}` / `sk-proj-[A-Za-z0-9_\-]{20,}` -> `[REDACTED_API_KEY]`
  - Standard JWTs (`eyJ...`) -> `[REDACTED_JWT]`
  - Database URI credentials (`postgres://user:pass@host...`) -> `[REDACTED_DB_CREDENTIALS]`
  - Payment Cards (13-16 digit Luhn formats) -> `[REDACTED_CARD]`
  - Social Security Numbers (`\d{3}-\d{2}-\d{4}`) -> `[REDACTED_SSN]`

### 3. Execution Trace Model (`AIOperationTrace`)
AI operations wrap critical stages using the `AITracer` asynchronous context manager:
```python
async with AITracer(
    session=db,
    organization_id=org_id,
    operation_type=AIOperationType.ANSWER_GENERATION,
    request_id=request_id,
) as tracer:
    with tracer.span("evidence_retrieval", stage="retrieval"):
        # retrieve documents...
    with tracer.span("llm_generation", stage="generation"):
        # invoke LLM provider...
```
- Spans track start offsets, durations, outcomes, and stage metadata.
- Execution traces persist safely without blocking business operations.
- Failures are captured even during unexpected timeouts or early pipeline terminations.

### 4. Failure Investigation & Deduplication (`FailureInvestigation`)
- **Classification:** Every error is mapped into standard categories: `configuration_error`, `authentication_error`, `authorization_error`, `input_validation_error`, `embedding_failure`, `retrieval_failure`, `no_relevant_evidence`, `generation_failure`, `citation_validation_failure`, `verification_failure`, `policy_violation`, `approval_conflict`, `document_processing_failure`, `indexing_failure`, `database_failure`, `queue_failure`, `unknown_error`.
- **Fingerprint Calculation:** Errors are fingerprinted via SHA-256 hash over `(org_id, category, provider, normalized_error_message[:120])`. The first 6 characters form a readable identifier: `INV-A1B2C3`.
- **Deduplication:** Subsequent occurrences increment `occurrence_count` and update `last_seen_at` without duplicating investigation entries.
- **Hypotheses Generation:** Automatically generates confidence-rated explanations (`high`, `medium`, `low`) and concrete remediation steps.
- **Operator Workflow:** Operators can transition statuses (`open` -> `investigating` -> `mitigated` -> `resolved` -> `false_positive`) and record audit resolution notes.

### 5. Reproducible Benchmark Evaluation & Regression Detection (`EvaluationRunRecord`)
- Versioned evaluation runs store benchmark dataset metadata, configuration, execution duration, and measured metrics:
  - `recall_at_k`: Fraction of queries where ground-truth reference chunk appears in top-k retrieved documents.
  - `mean_reciprocal_rank` (MRR): Average reciprocal rank of the first relevant document.
  - `citation_validity_rate`: Proportion of generated citation IDs matching retrieved document IDs.
  - `evidence_groundedness_rate`: Proportion of claims grounded in retrieved evidence.
  - `abstention_accuracy`: Proportion of unanswerable queries correctly abstained from.
- **Regression Detection:** Comparing runs against baselines using a configurable tolerance threshold (default 5.0%). If metric delta exceeds tolerance, `has_regression` is set to `True` with structured alert findings.

### 6. Token Usage & Cost Accounting (`AITokenUsageRecord`)
- Authoritative `MODEL_PRICING_CATALOG` schedules:
  - `openai/gpt-4o`: $5.00 / 1M input tokens, $15.00 / 1M output tokens.
  - `openai/gpt-4o-mini`: $0.15 / 1M input tokens, $0.60 / 1M output tokens.
  - `openai/text-embedding-3-small`: $0.02 / 1M tokens.
  - `fastembed/BAAI/bge-small-en-v1.5`: $0.00 infrastructure baseline.
  - `deterministic/rules`: $0.00 compute baseline.
- Summaries report input, output, and total tokens, cost in USD, and explicitly distinguish provider-reported tokens from inferred approximations.

### 7. Non-blocking System Diagnostics (`DiagnosticsService`)
- Probes PostgreSQL 16 connection latency (`SELECT 1`).
- Probes Redis queue connectivity and latency (`PING`).
- Inspects Qdrant vector engine collections without expensive scans.
- Inspects background worker loop configurations (polling intervals, batch sizes).
- Inspects local embedding engine dimensions and initialization latency without calling external paid LLM APIs.

### 8. Strict Multi-Tenant Isolation
All tables (`ai_operation_traces`, `failure_investigations`, `evaluation_run_records`, `ai_token_usage_records`) enforce PostgreSQL Row-Level Security:
- `ALTER TABLE ... ENABLE ROW LEVEL SECURITY;`
- `ALTER TABLE ... FORCE ROW LEVEL SECURITY;`
- `CREATE POLICY tenant_isolation_... ON ... USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid);`
Cross-tenant access attempts are rejected with 403 or 404.

## Consequences
- **Positive:**
  - Complete operational visibility into AI workflows without leaking customer PII or API secrets.
  - Automatic grouping of repeated errors prevents alert fatigue.
  - Continuous regression detection ensures prompt or model changes do not silently degrade retrieval or citation validity.
  - Exact token consumption and cost accounting enables granular per-tenant billing and capacity planning.
- **Negative:**
  - Additional database write per AI operation (mitigated via background async tasks and short span JSON payloads).
  - Trace retention policies must be executed periodically to bound disk storage growth.
