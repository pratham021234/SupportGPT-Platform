"""Integration tests validating PostgreSQL Row-Level Security (RLS) on knowledge subsystem tables."""

import uuid

import asyncpg
import pytest

POSTGRES_TEST_URL = (
    "postgresql://supportgpt_user:supportgpt_dev_password@localhost:5432/supportgpt_test_db"
)


@pytest.mark.asyncio
async def test_live_postgresql_knowledge_rls_enforcement():
    """Verify that PostgreSQL RLS policies enforce tenant boundaries on knowledge tables on live PostgreSQL."""
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
            f"PostgreSQL RLS integration test BLOCKED: Database is unreachable ({exc}). "
            "Ensure PostgreSQL is running to execute live RLS tests."
        )

    try:
        # Create isolated test organizations
        org_a_id = uuid.uuid4()
        org_b_id = uuid.uuid4()
        slug_a = f"rls-kb-org-a-{uuid.uuid4().hex[:8]}"
        slug_b = f"rls-kb-org-b-{uuid.uuid4().hex[:8]}"

        await conn.execute(
            "INSERT INTO organizations (id, name, slug, status, created_at, updated_at) "
            "VALUES ($1, 'RLS KB Org A', $2, 'active', NOW(), NOW()), "
            "       ($3, 'RLS KB Org B', $4, 'active', NOW(), NOW());",
            org_a_id,
            slug_a,
            org_b_id,
            slug_b,
        )

        kb_a_id = uuid.uuid4()
        kb_b_id = uuid.uuid4()
        doc_a_id = uuid.uuid4()
        doc_b_id = uuid.uuid4()
        ver_a_id = uuid.uuid4()
        ver_b_id = uuid.uuid4()
        chunk_a_id = uuid.uuid4()
        chunk_b_id = uuid.uuid4()

        # 1. Insert records under Tenant Alpha context
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_organization_id', $1, true);", str(org_a_id))
            await conn.execute(
                "INSERT INTO knowledge_bases (id, organization_id, name, status, config, created_at, updated_at) "
                "VALUES ($1, $2, 'KB Alpha', 'active', '{}'::jsonb, NOW(), NOW());",
                kb_a_id, org_a_id,
            )
            await conn.execute(
                "INSERT INTO documents (id, organization_id, knowledge_base_id, title, source_type, original_filename, media_type, status, lifecycle_status, current_version_number, size_bytes, checksum, created_at, updated_at) "
                "VALUES ($1, $2, $3, 'Doc Alpha', 'file_upload', 'doc_a.txt', 'text/plain', 'chunked', 'active', 1, 100, $4, NOW(), NOW());",
                doc_a_id, org_a_id, kb_a_id, "a" * 64,
            )
            await conn.execute(
                "INSERT INTO document_versions (id, organization_id, document_id, version_number, storage_key, original_filename, media_type, size_bytes, checksum, processing_status, created_at, updated_at) "
                "VALUES ($1, $2, $3, 1, 'key_a', 'doc_a.txt', 'text/plain', 100, $4, 'chunked', NOW(), NOW());",
                ver_a_id, org_a_id, doc_a_id, "a" * 64,
            )
            await conn.execute(
                "INSERT INTO document_chunks (id, organization_id, knowledge_base_id, document_id, version_id, sequence_number, content, checksum, pipeline_version, created_at, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, 0, 'Alpha Content', $6, '1.0.0', NOW(), NOW());",
                chunk_a_id, org_a_id, kb_a_id, doc_a_id, ver_a_id, "a" * 64,
            )

        # 2. Insert records under Tenant Beta context
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_organization_id', $1, true);", str(org_b_id))
            await conn.execute(
                "INSERT INTO knowledge_bases (id, organization_id, name, status, config, created_at, updated_at) "
                "VALUES ($1, $2, 'KB Beta', 'active', '{}'::jsonb, NOW(), NOW());",
                kb_b_id, org_b_id,
            )
            await conn.execute(
                "INSERT INTO documents (id, organization_id, knowledge_base_id, title, source_type, original_filename, media_type, status, lifecycle_status, current_version_number, size_bytes, checksum, created_at, updated_at) "
                "VALUES ($1, $2, $3, 'Doc Beta', 'file_upload', 'doc_b.txt', 'text/plain', 'chunked', 'active', 1, 200, $4, NOW(), NOW());",
                doc_b_id, org_b_id, kb_b_id, "b" * 64,
            )
            await conn.execute(
                "INSERT INTO document_versions (id, organization_id, document_id, version_number, storage_key, original_filename, media_type, size_bytes, checksum, processing_status, created_at, updated_at) "
                "VALUES ($1, $2, $3, 1, 'key_b', 'doc_b.txt', 'text/plain', 200, $4, 'chunked', NOW(), NOW());",
                ver_b_id, org_b_id, doc_b_id, "b" * 64,
            )
            await conn.execute(
                "INSERT INTO document_chunks (id, organization_id, knowledge_base_id, document_id, version_id, sequence_number, content, checksum, pipeline_version, created_at, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, 0, 'Beta Content', $6, '1.0.0', NOW(), NOW());",
                chunk_b_id, org_b_id, kb_b_id, doc_b_id, ver_b_id, "b" * 64,
            )

        # 3. Verify cross-tenant write denial (Alpha attempts to write into Beta org)
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.current_organization_id', $1, true);", str(org_a_id))
                await conn.execute(
                    "INSERT INTO knowledge_bases (id, organization_id, name, status, config, created_at, updated_at) "
                    "VALUES ($1, $2, 'Injected KB', 'active', '{}'::jsonb, NOW(), NOW());",
                    uuid.uuid4(), org_b_id,
                )

        # 4. Query under Tenant Alpha context
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_organization_id', $1, true);", str(org_a_id))
            kb_rows = await conn.fetch("SELECT id FROM knowledge_bases WHERE id IN ($1, $2);", kb_a_id, kb_b_id)
            assert len(kb_rows) == 1
            assert kb_rows[0]["id"] == kb_a_id

            doc_rows = await conn.fetch("SELECT id FROM documents WHERE id IN ($1, $2);", doc_a_id, doc_b_id)
            assert len(doc_rows) == 1
            assert doc_rows[0]["id"] == doc_a_id

            ver_rows = await conn.fetch("SELECT id FROM document_versions WHERE id IN ($1, $2);", ver_a_id, ver_b_id)
            assert len(ver_rows) == 1
            assert ver_rows[0]["id"] == ver_a_id

            chunk_rows = await conn.fetch("SELECT id FROM document_chunks WHERE id IN ($1, $2);", chunk_a_id, chunk_b_id)
            assert len(chunk_rows) == 1
            assert chunk_rows[0]["id"] == chunk_a_id

        # 5. Query under Tenant Beta context
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_organization_id', $1, true);", str(org_b_id))
            kb_beta_rows = await conn.fetch("SELECT id FROM knowledge_bases WHERE id IN ($1, $2);", kb_a_id, kb_b_id)
            assert len(kb_beta_rows) == 1
            assert kb_beta_rows[0]["id"] == kb_b_id

        # 6. Query with no context (safe default: 0 rows returned)
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_organization_id', '', true);")
            empty_rows = await conn.fetch("SELECT id FROM knowledge_bases WHERE id IN ($1, $2);", kb_a_id, kb_b_id)
            assert len(empty_rows) == 0

    finally:
        # Cleanup test records using system admin
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.is_system_admin', 'true', true);")
            await conn.execute("DELETE FROM document_chunks WHERE organization_id IN ($1, $2);", org_a_id, org_b_id)
            await conn.execute("DELETE FROM document_versions WHERE organization_id IN ($1, $2);", org_a_id, org_b_id)
            await conn.execute("DELETE FROM documents WHERE organization_id IN ($1, $2);", org_a_id, org_b_id)
            await conn.execute("DELETE FROM knowledge_bases WHERE organization_id IN ($1, $2);", org_a_id, org_b_id)
            await conn.execute("DELETE FROM organizations WHERE id IN ($1, $2);", org_a_id, org_b_id)
        await conn.close()

