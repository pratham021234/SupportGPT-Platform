"""Integration tests executing against live PostgreSQL 16 validating RLS on ingestion tables and concurrent FOR UPDATE SKIP LOCKED job claiming."""

import asyncio
import uuid

import asyncpg
import pytest


@pytest.mark.asyncio
async def test_live_postgresql_rls_on_sources_and_receipts():
    """Verify that PostgreSQL RLS policies enforce tenant boundaries on event_sources and ingestion_receipts."""
    try:
        conn = await asyncpg.connect(
            user="supportgpt_user",
            password="supportgpt_dev_password",
            database="supportgpt_test_db",
            host="localhost",
            port=5432,
            timeout=2.0,
        )
    except Exception as exc:
        pytest.skip(
            f"PostgreSQL integration test BLOCKED: Database is unreachable ({exc}). "
            "Ensure PostgreSQL is running to execute live tests."
        )

    try:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        slug_a = f"source-a-{uuid.uuid4().hex[:8]}"
        slug_b = f"source-b-{uuid.uuid4().hex[:8]}"

        await conn.execute(
            "INSERT INTO organizations (id, name, slug, status, created_at, updated_at) "
            "VALUES ($1, 'Source Org A', $2, 'active', NOW(), NOW()), "
            "       ($3, 'Source Org B', $4, 'active', NOW(), NOW());",
            org_a,
            slug_a,
            org_b,
            slug_b,
        )

        source_a_id = uuid.uuid4()
        source_b_id = uuid.uuid4()
        rec_a_id = uuid.uuid4()
        rec_b_id = uuid.uuid4()

        # 1. Insert Org A Source and Receipt under Org A RLS context
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_organization_id', $1, true);", str(org_a)
            )
            await conn.execute(
                "INSERT INTO event_sources (id, organization_id, name, provider, status, signing_secret_hash, created_at, updated_at) "
                "VALUES ($1, $2, 'Org A Source', 'generic_webhook', 'active', 'hash_a', NOW(), NOW());",
                source_a_id,
                org_a,
            )
            await conn.execute(
                "INSERT INTO ingestion_receipts (id, organization_id, source_id, source_provider, external_event_id, event_type, status, received_at) "
                "VALUES ($1, $2, $3, 'generic_webhook', 'evt-a-1', 'ticket.created', 'queued', NOW());",
                rec_a_id,
                org_a,
                source_a_id,
            )

        # 2. Insert Org B Source and Receipt under Org B RLS context
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_organization_id', $1, true);", str(org_b)
            )
            await conn.execute(
                "INSERT INTO event_sources (id, organization_id, name, provider, status, signing_secret_hash, created_at, updated_at) "
                "VALUES ($1, $2, 'Org B Source', 'generic_webhook', 'active', 'hash_b', NOW(), NOW());",
                source_b_id,
                org_b,
            )
            await conn.execute(
                "INSERT INTO ingestion_receipts (id, organization_id, source_id, source_provider, external_event_id, event_type, status, received_at) "
                "VALUES ($1, $2, $3, 'generic_webhook', 'evt-b-1', 'ticket.created', 'queued', NOW());",
                rec_b_id,
                org_b,
                source_b_id,
            )

        # 3. Query under Org A context: should see ONLY Org A records
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_organization_id', $1, true);", str(org_a)
            )
            sources_a = await conn.fetch("SELECT id FROM event_sources;")
            receipts_a = await conn.fetch("SELECT id FROM ingestion_receipts;")

            assert len(sources_a) == 1
            assert sources_a[0]["id"] == source_a_id
            assert len(receipts_a) == 1
            assert receipts_a[0]["id"] == rec_a_id

        # 4. Query under Org B context: should see ONLY Org B records
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_organization_id', $1, true);", str(org_b)
            )
            sources_b = await conn.fetch("SELECT id FROM event_sources;")
            receipts_b = await conn.fetch("SELECT id FROM ingestion_receipts;")

            assert len(sources_b) == 1
            assert sources_b[0]["id"] == source_b_id
            assert len(receipts_b) == 1
            assert receipts_b[0]["id"] == rec_b_id

        # 5. Query without context: must return 0 rows (safe default)
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_organization_id', '', true);")
            sources_none = await conn.fetch("SELECT id FROM event_sources;")
            receipts_none = await conn.fetch("SELECT id FROM ingestion_receipts;")

            assert len(sources_none) == 0
            assert len(receipts_none) == 0

        # 6. Query with system admin context: sees both
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.is_system_admin', 'true', true);")
            sources_sys = await conn.fetch(
                "SELECT id FROM event_sources WHERE id IN ($1, $2);",
                source_a_id,
                source_b_id,
            )
            assert len(sources_sys) == 2

    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_live_postgresql_concurrent_worker_skip_locked():
    """Verify that multiple concurrent workers using FOR UPDATE SKIP LOCKED claim disjoint batches without collision."""
    try:
        conn1 = await asyncpg.connect(
            user="supportgpt_user",
            password="supportgpt_dev_password",
            database="supportgpt_test_db",
            host="localhost",
            port=5432,
            timeout=2.0,
        )
        conn2 = await asyncpg.connect(
            user="supportgpt_user",
            password="supportgpt_dev_password",
            database="supportgpt_test_db",
            host="localhost",
            port=5432,
            timeout=2.0,
        )
    except Exception as exc:
        pytest.skip(
            f"PostgreSQL concurrency test BLOCKED: Database is unreachable ({exc}). "
            "Ensure PostgreSQL is running to execute live tests."
        )

    try:
        org_id = uuid.uuid4()
        slug = f"worker-org-{uuid.uuid4().hex[:8]}"

        await conn1.execute(
            "INSERT INTO organizations (id, name, slug, status, created_at, updated_at) "
            "VALUES ($1, 'Worker Concurrency Org', $2, 'active', NOW(), NOW());",
            org_id,
            slug,
        )

        # Seed 6 queued receipts under system admin context
        receipt_ids = [uuid.uuid4() for _ in range(6)]
        async with conn1.transaction():
            await conn1.execute("SELECT set_config('app.is_system_admin', 'true', true);")
            for i, rid in enumerate(receipt_ids):
                await conn1.execute(
                    "INSERT INTO ingestion_receipts (id, organization_id, source_provider, external_event_id, event_type, status, received_at) "
                    "VALUES ($1, $2, 'generic_webhook', $3, 'ticket.created', 'queued', NOW());",
                    rid,
                    org_id,
                    f"evt-conc-{i}",
                )

        # Worker 1 and Worker 2 claim concurrently in active transactions
        async def worker_1_claim():
            async with conn1.transaction():
                await conn1.execute("SELECT set_config('app.is_system_admin', 'true', true);")
                rows = await conn1.fetch(
                    "SELECT id FROM ingestion_receipts "
                    "WHERE id = ANY($1::uuid[]) AND status = 'queued' "
                    "ORDER BY received_at ASC "
                    "LIMIT 3 "
                    "FOR UPDATE SKIP LOCKED;",
                    receipt_ids,
                )
                claimed = [r["id"] for r in rows]
                # Hold transaction briefly so worker 2 attempts simultaneous claim
                await asyncio.sleep(0.1)
                return claimed

        async def worker_2_claim():
            # Small delay to ensure worker 1 has opened transaction and acquired locks
            await asyncio.sleep(0.02)
            async with conn2.transaction():
                await conn2.execute("SELECT set_config('app.is_system_admin', 'true', true);")
                rows = await conn2.fetch(
                    "SELECT id FROM ingestion_receipts "
                    "WHERE id = ANY($1::uuid[]) AND status = 'queued' "
                    "ORDER BY received_at ASC "
                    "LIMIT 3 "
                    "FOR UPDATE SKIP LOCKED;",
                    receipt_ids,
                )
                return [r["id"] for r in rows]

        w1_result, w2_result = await asyncio.gather(worker_1_claim(), worker_2_claim())

        # Assertions:
        # 1. Each worker claimed items
        assert len(w1_result) == 3
        assert len(w2_result) == 3

        # 2. Zero collision: intersection must be completely empty!
        intersection = set(w1_result).intersection(set(w2_result))
        assert len(intersection) == 0, f"Worker collision detected! Shared receipts: {intersection}"

        # 3. All 6 receipts were claimed across the two workers
        union = set(w1_result).union(set(w2_result))
        assert union == set(receipt_ids)

    finally:
        await conn1.close()
        await conn2.close()
