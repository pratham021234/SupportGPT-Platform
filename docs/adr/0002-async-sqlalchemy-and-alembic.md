# ADR 0002: Asynchronous SQLAlchemy 2.x and Alembic Migrations

## Status
Accepted

## Date
2026-10-14

## Context
High-concurrency customer support platforms require non-blocking I/O to handle thousands of simultaneous chat sessions, streaming LLM tokens, and database queries without exhausting operating system threads. Python's `asyncio` event loop paired with FastAPI provides high I/O throughput. However, mixing synchronous database drivers with asynchronous route handlers risks blocking the event loop and degrading response latency.

## Decision
1. Standardize on **SQLAlchemy 2.0+** utilizing its native `ext.asyncio` extension and the high-performance `asyncpg` PostgreSQL driver.
2. Structure all session lifecycles using explicit FastAPI dependency injection (`get_db_session()`), ensuring single-request transaction boundaries, automatic rollbacks on unhandled exceptions, and explicit pool teardown on application shutdown.
3. Configure **Alembic** migrations to execute asynchronously using `async_engine_from_config` inside `env.py`, driven by application settings.
4. Mandate naming conventions on `MetaData` (`ix_`, `uq_`, `ck_`, `fk_`, `pk_`) to ensure generated DDL scripts remain deterministic across PostgreSQL releases.

## Consequences
### Positive
- Fully non-blocking database queries across all endpoints.
- High connection pool reuse and minimal thread starvation.
- Consistent index and constraint naming across all migration revisions.

### Negative
- Requires `greenlet` installation for SQLAlchemy's async context.
- Model attribute lazy loading is disabled; relationships must use explicit joined or selectin loading to prevent async attribute errors.
