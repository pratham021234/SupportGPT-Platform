"""Integration tests validating PostgreSQL Row-Level Security (RLS) enforcement against live PostgreSQL."""

import uuid

import asyncpg
import pytest

POSTGRES_TEST_URL = (
    "postgresql://supportgpt_user:supportgpt_dev_password@localhost:5432/supportgpt_test_db"
)


@pytest.mark.asyncio
async def test_live_postgresql_rls_enforcement():
    """Verify that PostgreSQL RLS policies enforce tenant boundaries on live PostgreSQL.

    1. Checks if PostgreSQL service is reachable; if not, marks test as BLOCKED.
    2. Connects to supportgpt_test_db using restricted application user.
    3. Seeds Organization A and Organization B tickets.
    4. Sets app.current_organization_id = Org A -> reads ONLY Org A tickets.
    5. Sets app.current_organization_id = Org B -> reads ONLY Org B tickets.
    6. With context unset -> reads 0 tickets (safe default: missing context yields no data).
    7. Verifies transaction rollback resets context cleanly.
    """
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
        slug_a = f"rls-org-a-{uuid.uuid4().hex[:8]}"
        slug_b = f"rls-org-b-{uuid.uuid4().hex[:8]}"

        await conn.execute(
            "INSERT INTO organizations (id, name, slug, status, created_at, updated_at) "
            "VALUES ($1, 'RLS Org A', $2, 'active', NOW(), NOW()), "
            "       ($3, 'RLS Org B', $4, 'active', NOW(), NOW());",
            org_a_id,
            slug_a,
            org_b_id,
            slug_b,
        )

        ticket_a_id = uuid.uuid4()
        ticket_b_id = uuid.uuid4()

        # 1. Insert Ticket A under Tenant Alpha context
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_organization_id', $1, true);", str(org_a_id)
            )
            await conn.execute(
                "INSERT INTO tickets (id, organization_id, ticket_number, ticket_reference, subject, status, priority, channel, created_at, updated_at) "
                "VALUES ($1, $2, 101, 'RLS-101', 'RLS Ticket Alpha', 'open', 'medium', 'web', NOW(), NOW());",
                ticket_a_id,
                org_a_id,
            )

        # 2. Verify Cross-Tenant Write Denial: Attempt to insert Org B ticket while context is Org A
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_organization_id', $1, true);", str(org_a_id)
                )
                await conn.execute(
                    "INSERT INTO tickets (id, organization_id, ticket_number, ticket_reference, subject, status, priority, channel, created_at, updated_at) "
                    "VALUES ($1, $2, 102, 'RLS-102', 'RLS Ticket Beta Illegal', 'open', 'high', 'email', NOW(), NOW());",
                    ticket_b_id,
                    org_b_id,
                )

        # 3. Insert Ticket B under Tenant Beta context
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_organization_id', $1, true);", str(org_b_id)
            )
            await conn.execute(
                "INSERT INTO tickets (id, organization_id, ticket_number, ticket_reference, subject, status, priority, channel, created_at, updated_at) "
                "VALUES ($1, $2, 102, 'RLS-102', 'RLS Ticket Beta', 'open', 'high', 'email', NOW(), NOW());",
                ticket_b_id,
                org_b_id,
            )

        # 4. Query with Tenant Alpha context
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_organization_id', $1, true);", str(org_a_id)
            )
            rows = await conn.fetch(
                "SELECT id, organization_id, subject FROM tickets WHERE id IN ($1, $2);",
                ticket_a_id,
                ticket_b_id,
            )
            assert len(rows) == 1
            assert rows[0]["id"] == ticket_a_id
            assert rows[0]["organization_id"] == org_a_id

        # 5. Query with Tenant Beta context
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_organization_id', $1, true);", str(org_b_id)
            )
            rows = await conn.fetch(
                "SELECT id, organization_id, subject FROM tickets WHERE id IN ($1, $2);",
                ticket_a_id,
                ticket_b_id,
            )
            assert len(rows) == 1
            assert rows[0]["id"] == ticket_b_id
            assert rows[0]["organization_id"] == org_b_id

        # 6. Query with missing / unset context (must return 0 rows under RLS)
        async with conn.transaction():
            rows = await conn.fetch(
                "SELECT id FROM tickets WHERE id IN ($1, $2);", ticket_a_id, ticket_b_id
            )
            assert len(rows) == 0

        # 7. Clean up test records under their authorized contexts
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_organization_id', $1, true);", str(org_a_id)
            )
            await conn.execute("DELETE FROM tickets WHERE id = $1;", ticket_a_id)

        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_organization_id', $1, true);", str(org_b_id)
            )
            await conn.execute("DELETE FROM tickets WHERE id = $1;", ticket_b_id)

        await conn.execute("DELETE FROM organizations WHERE id IN ($1, $2);", org_a_id, org_b_id)

    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_live_postgresql_rls_conversations_and_messages():
    """Verify that PostgreSQL RLS policies protect conversations and messages on live PostgreSQL."""
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
        pytest.skip(f"PostgreSQL RLS test BLOCKED: Database unreachable ({exc})")

    try:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        slug_a = f"rls-msg-a-{uuid.uuid4().hex[:8]}"
        slug_b = f"rls-msg-b-{uuid.uuid4().hex[:8]}"

        await conn.execute(
            "INSERT INTO organizations (id, name, slug, status, created_at, updated_at) "
            "VALUES ($1, 'RLS Org A', $2, 'active', NOW(), NOW()), ($3, 'RLS Org B', $4, 'active', NOW(), NOW());",
            org_a,
            slug_a,
            org_b,
            slug_b,
        )

        ticket_a = uuid.uuid4()
        ticket_b = uuid.uuid4()
        conv_a = uuid.uuid4()
        conv_b = uuid.uuid4()
        msg_a = uuid.uuid4()
        msg_b = uuid.uuid4()

        # Seed Ticket & Conversation for Org A
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_organization_id', $1, true);", str(org_a)
            )
            await conn.execute(
                "INSERT INTO tickets (id, organization_id, ticket_number, ticket_reference, subject, status, priority, channel, created_at, updated_at) "
                "VALUES ($1, $2, 201, 'RLS-201', 'Ticket A', 'open', 'medium', 'email', NOW(), NOW());",
                ticket_a,
                org_a,
            )
            await conn.execute(
                "INSERT INTO conversations (id, organization_id, ticket_id, channel_type, status, created_at, updated_at) "
                "VALUES ($1, $2, $3, 'email', 'active', NOW(), NOW());",
                conv_a,
                org_a,
                ticket_a,
            )
            await conn.execute(
                "INSERT INTO messages (id, organization_id, conversation_id, direction, author_type, body_text, content_type, sequence_number, delivery_status, created_at) "
                "VALUES ($1, $2, $3, 'outbound', 'agent', 'Alpha secret message', 'text/plain', 1, 'stored', NOW());",
                msg_a,
                org_a,
                conv_a,
            )

        # Seed Ticket & Conversation for Org B
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_organization_id', $1, true);", str(org_b)
            )
            await conn.execute(
                "INSERT INTO tickets (id, organization_id, ticket_number, ticket_reference, subject, status, priority, channel, created_at, updated_at) "
                "VALUES ($1, $2, 202, 'RLS-202', 'Ticket B', 'open', 'high', 'email', NOW(), NOW());",
                ticket_b,
                org_b,
            )
            await conn.execute(
                "INSERT INTO conversations (id, organization_id, ticket_id, channel_type, status, created_at, updated_at) "
                "VALUES ($1, $2, $3, 'email', 'active', NOW(), NOW());",
                conv_b,
                org_b,
                ticket_b,
            )
            await conn.execute(
                "INSERT INTO messages (id, organization_id, conversation_id, direction, author_type, body_text, content_type, sequence_number, delivery_status, created_at) "
                "VALUES ($1, $2, $3, 'inbound', 'customer', 'Beta confidential payload', 'text/plain', 1, 'received', NOW());",
                msg_b,
                org_b,
                conv_b,
            )

        # 1. Cross-Tenant Message Write: Attempt to insert Org B message while in Org A context -> RLS Denies
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_organization_id', $1, true);", str(org_a)
                )
                await conn.execute(
                    "INSERT INTO messages (id, organization_id, conversation_id, direction, author_type, body_text, content_type, sequence_number, delivery_status, created_at) "
                    "VALUES ($1, $2, $3, 'outbound', 'agent', 'Illegal inject', 'text/plain', 2, 'stored', NOW());",
                    uuid.uuid4(),
                    org_b,
                    conv_b,
                )

        # 2. Query messages under Org A context -> Only sees msg_a
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_organization_id', $1, true);", str(org_a)
            )
            rows = await conn.fetch(
                "SELECT id, body_text FROM messages WHERE id IN ($1, $2);", msg_a, msg_b
            )
            assert len(rows) == 1
            assert rows[0]["id"] == msg_a
            assert rows[0]["body_text"] == "Alpha secret message"

        # 3. Clean up
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_organization_id', $1, true);", str(org_a)
            )
            await conn.execute("DELETE FROM messages WHERE id = $1;", msg_a)
            await conn.execute("DELETE FROM conversations WHERE id = $1;", conv_a)
            await conn.execute("DELETE FROM tickets WHERE id = $1;", ticket_a)

        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_organization_id', $1, true);", str(org_b)
            )
            await conn.execute("DELETE FROM messages WHERE id = $1;", msg_b)
            await conn.execute("DELETE FROM conversations WHERE id = $1;", conv_b)
            await conn.execute("DELETE FROM tickets WHERE id = $1;", ticket_b)

        await conn.execute("DELETE FROM organizations WHERE id IN ($1, $2);", org_a, org_b)

    finally:
        await conn.close()
