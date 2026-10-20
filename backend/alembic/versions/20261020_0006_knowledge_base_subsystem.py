"""Knowledge base subsystem: knowledge_bases, documents, document_versions, document_chunks, and tenant RLS.

Revision ID: 0006_knowledge_base_subsystem
Revises: 0005_event_ingestion_subsystem
Create Date: 2026-10-20 14:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_knowledge_base_subsystem"
down_revision: str | None = "0005_event_ingestion_subsystem"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Create knowledge_bases table
    op.create_table(
        "knowledge_bases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Organization owner of this knowledge base",
        ),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
            comment="Human-readable name of the knowledge collection",
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="Optional description or operational purpose of the collection",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="active",
            nullable=False,
            comment="Lifecycle status (active, archived)",
        ),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.Text(),
            server_default="{}" if is_postgres else "{}",
            nullable=False,
            comment="Optional collection-specific processing configuration",
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="User who created the knowledge base",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_knowledge_bases_id_org"),
        sa.UniqueConstraint("organization_id", "name", name="uq_knowledge_bases_org_name"),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_knowledge_bases_status",
        ),
    )
    op.create_index(
        op.f("ix_knowledge_bases_organization_id"),
        "knowledge_bases",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_bases_org_status",
        "knowledge_bases",
        ["organization_id", "status"],
        unique=False,
    )

    # 2. Create documents table
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Organization owner of this document",
        ),
        sa.Column(
            "knowledge_base_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Parent knowledge base collection",
        ),
        sa.Column(
            "title",
            sa.String(length=255),
            nullable=False,
            comment="Display title of the document",
        ),
        sa.Column(
            "source_type",
            sa.String(length=50),
            server_default="file_upload",
            nullable=False,
            comment="Source origin (file_upload, manual_entry, api)",
        ),
        sa.Column(
            "original_filename",
            sa.String(length=255),
            nullable=False,
            comment="Sanitized original filename as uploaded",
        ),
        sa.Column(
            "media_type",
            sa.String(length=100),
            nullable=False,
            comment="Verified MIME media type",
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default="uploaded",
            nullable=False,
            comment="Processing pipeline state of the active version",
        ),
        sa.Column(
            "lifecycle_status",
            sa.String(length=20),
            server_default="active",
            nullable=False,
            comment="Lifecycle state (active, archived, deleted)",
        ),
        sa.Column(
            "current_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Foreign key identifier of the currently published usable version",
        ),
        sa.Column(
            "current_version_number",
            sa.Integer(),
            server_default="1",
            nullable=False,
            comment="Monotonic version number of the active revision",
        ),
        sa.Column(
            "size_bytes",
            sa.BigInteger(),
            nullable=False,
            comment="Byte size of the current version binary object",
        ),
        sa.Column(
            "checksum",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 cryptographic digest of the source binary file",
        ),
        sa.Column(
            "error_code",
            sa.String(length=100),
            nullable=True,
            comment="Safe error classification code if processing failed",
        ),
        sa.Column(
            "error_summary",
            sa.Text(),
            nullable=True,
            comment="Redacted error summary for operator inspection",
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="User who created the document",
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when document was soft deleted",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_documents_id_org"),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id", "organization_id"],
            ["knowledge_bases.id", "knowledge_bases.organization_id"],
            name="fk_documents_kb_org",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('active', 'archived', 'deleted')",
            name="ck_documents_lifecycle_status",
        ),
    )
    op.create_index(
        op.f("ix_documents_organization_id"), "documents", ["organization_id"], unique=False
    )
    op.create_index(
        op.f("ix_documents_knowledge_base_id"), "documents", ["knowledge_base_id"], unique=False
    )
    op.create_index(
        "ix_documents_org_kb", "documents", ["organization_id", "knowledge_base_id"], unique=False
    )
    op.create_index(
        "ix_documents_org_status", "documents", ["organization_id", "status"], unique=False
    )
    op.create_index(
        "ix_documents_org_lifecycle",
        "documents",
        ["organization_id", "lifecycle_status"],
        unique=False,
    )

    # 3. Create document_versions table
    op.create_table(
        "document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Organization owner of this version",
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Parent document identity",
        ),
        sa.Column(
            "version_number",
            sa.Integer(),
            nullable=False,
            comment="Sequential version counter",
        ),
        sa.Column(
            "storage_key",
            sa.String(length=500),
            nullable=False,
            comment="Opaque internal object storage locator key",
        ),
        sa.Column(
            "original_filename",
            sa.String(length=255),
            nullable=False,
            comment="Original filename submitted for this revision",
        ),
        sa.Column(
            "media_type",
            sa.String(length=100),
            nullable=False,
            comment="MIME media type detected for this revision",
        ),
        sa.Column(
            "size_bytes",
            sa.BigInteger(),
            nullable=False,
            comment="Binary size in bytes",
        ),
        sa.Column(
            "checksum",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 hash of the binary file",
        ),
        sa.Column(
            "processing_status",
            sa.String(length=50),
            server_default="uploaded",
            nullable=False,
            comment="Active processing state",
        ),
        sa.Column(
            "extractor_name",
            sa.String(length=100),
            nullable=True,
            comment="Name of extractor that parsed the document text",
        ),
        sa.Column(
            "extractor_version",
            sa.String(length=50),
            nullable=True,
            comment="Version of extractor component",
        ),
        sa.Column(
            "chunker_name",
            sa.String(length=100),
            nullable=True,
            comment="Name of chunker algorithm used",
        ),
        sa.Column(
            "chunker_version",
            sa.String(length=50),
            nullable=True,
            comment="Version of chunker algorithm",
        ),
        sa.Column(
            "chunk_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Number of text chunks generated for this version",
        ),
        sa.Column(
            "word_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Total word count extracted from document",
        ),
        sa.Column(
            "character_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Total character count extracted from document",
        ),
        sa.Column(
            "error_code",
            sa.String(length=100),
            nullable=True,
            comment="Error code if processing failed",
        ),
        sa.Column(
            "error_summary",
            sa.Text(),
            nullable=True,
            comment="Safe redacted failure summary",
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Number of worker processing attempts",
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when next retry is scheduled",
        ),
        sa.Column(
            "processing_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when current worker lease started",
        ),
        sa.Column(
            "locked_by",
            sa.String(length=100),
            nullable=True,
            comment="Worker instance identifier holding the active lease",
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="User who uploaded this revision",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_document_versions_id_org"),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_versions_doc_ver"),
        sa.ForeignKeyConstraint(
            ["document_id", "organization_id"],
            ["documents.id", "documents.organization_id"],
            name="fk_document_versions_doc_org",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_document_versions_organization_id"),
        "document_versions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_versions_document_id"), "document_versions", ["document_id"], unique=False
    )
    op.create_index(
        "ix_document_versions_queue",
        "document_versions",
        ["processing_status", "next_attempt_at", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_document_versions_org_doc",
        "document_versions",
        ["organization_id", "document_id"],
        unique=False,
    )

    # 4. Create document_chunks table
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Organization owner of this chunk",
        ),
        sa.Column(
            "knowledge_base_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Parent knowledge base",
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Parent document identity",
        ),
        sa.Column(
            "version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Specific document version from which this chunk was derived",
        ),
        sa.Column(
            "sequence_number",
            sa.Integer(),
            nullable=False,
            comment="Sequential chunk ordering within the version",
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            comment="Normalized text content of this chunk",
        ),
        sa.Column(
            "word_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Word count in chunk content",
        ),
        sa.Column(
            "character_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Character length of chunk content",
        ),
        sa.Column(
            "start_char_idx",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Character start offset in the normalized version text",
        ),
        sa.Column(
            "end_char_idx",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Character end offset in the normalized version text",
        ),
        sa.Column(
            "heading_hierarchy",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.Text(),
            server_default="[]" if is_postgres else "[]",
            nullable=False,
            comment="Structural breadcrumbs/headings leading to this chunk",
        ),
        sa.Column(
            "checksum",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 digest of normalized chunk text",
        ),
        sa.Column(
            "pipeline_version",
            sa.String(length=50),
            server_default="1.0.0",
            nullable=False,
            comment="Chunker pipeline version that produced this record",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_document_chunks_id_org"),
        sa.UniqueConstraint("version_id", "sequence_number", name="uq_document_chunks_ver_seq"),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id", "organization_id"],
            ["knowledge_bases.id", "knowledge_bases.organization_id"],
            name="fk_document_chunks_kb_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "organization_id"],
            ["documents.id", "documents.organization_id"],
            name="fk_document_chunks_doc_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "organization_id"],
            ["document_versions.id", "document_versions.organization_id"],
            name="fk_document_chunks_ver_org",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_document_chunks_organization_id"),
        "document_chunks",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_chunks_knowledge_base_id"),
        "document_chunks",
        ["knowledge_base_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_chunks_document_id"), "document_chunks", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_document_chunks_version_id"), "document_chunks", ["version_id"], unique=False
    )
    op.create_index(
        "ix_document_chunks_org_doc",
        "document_chunks",
        ["organization_id", "document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_chunks_org_ver",
        "document_chunks",
        ["organization_id", "version_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_chunks_ver_seq",
        "document_chunks",
        ["version_id", "sequence_number"],
        unique=False,
    )

    # 5. Row-Level Security (RLS) policies on PostgreSQL
    if is_postgres:
        kb_tables = [
            "knowledge_bases",
            "documents",
            "document_versions",
            "document_chunks",
        ]
        for table in kb_tables:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
            op.execute(
                f"""
                CREATE POLICY {table}_tenant_isolation ON {table}
                FOR ALL
                USING (
                    organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid
                    OR current_setting('app.is_system_admin', true) = 'true'
                );
                """
            )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    kb_tables = [
        "document_chunks",
        "document_versions",
        "documents",
        "knowledge_bases",
    ]

    if is_postgres:
        for table in kb_tables:
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_table("document_chunks")
    op.drop_table("document_versions")
    op.drop_table("documents")
    op.drop_table("knowledge_bases")
