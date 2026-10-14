# ADR 0001: Modular Monolith Architecture

## Status
Accepted

## Date
2026-10-14

## Context
SupportGPT AI is an enterprise multi-tenant B2B SaaS platform that coordinates customer conversations, company knowledge retrieval, claim-level AI verification, human approvals, and failure investigation. In the initial phases, engineering velocity, transactional consistency, code discoverability, and rapid refactoring are paramount. Premature microservice decomposition introduces distributed transaction complexity, network latency, multiple schema synchronizations, and high DevOps overhead without justifiable organizational or scale benefits.

## Decision
We adopt a **Modular Monolith** architecture for the backend application:
1. A single deployable codebase (`backend/`) structured into strictly segregated internal domains (`api/`, `core/`, `db/`, `models/`, `schemas/`, `ai/`).
2. Layer boundaries are enforced:
   - **Transport Layer (`api/`)**: HTTP routing, request parsing, and response status mapping. No business rules or raw database queries.
   - **Application & Domain Services**: Coordinate domain validation, persistence, and external adapters.
   - **Persistence Layer (`db/`, `models/`)**: Authoritative SQLAlchemy 2.x declarative models and async sessions.
   - **AI Boundary (`ai/`)**: Abstract Base Classes ensuring core business logic is vendor-neutral and not coupled to any proprietary LLM SDK.
3. Services share a single authoritative PostgreSQL database instance with isolated tables and Row-Level Security (RLS) in Phase 02.

## Consequences
### Positive
- Unified transaction boundaries across related entities.
- Zero distributed state or network RPC overhead between core modules.
- Single migration sequence via Alembic.
- Simple local development: one command boots backend and frontend.

### Negative
- Developers must maintain self-discipline to prevent direct cross-module coupling.
- Enforced via code reviews, linting, and future domain boundary checks.
