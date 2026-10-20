"""Knowledge Base domain model representing an organization-scoped collection of knowledge."""

import uuid

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import KnowledgeBaseStatus


class KnowledgeBase(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Logical collection of company knowledge owned by an organization."""

    __tablename__ = "knowledge_bases"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Organization owner of this knowledge base",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable name of the knowledge collection",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional description or operational purpose of the collection",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=KnowledgeBaseStatus.ACTIVE,
        nullable=False,
        comment="Lifecycle status (active, archived)",
    )
    config: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        nullable=False,
        comment="Optional collection-specific processing configuration",
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who created the knowledge base",
    )

    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_knowledge_bases_id_org"),
        UniqueConstraint("organization_id", "name", name="uq_knowledge_bases_org_name"),
        Index("ix_knowledge_bases_org_status", "organization_id", "status"),
        CheckConstraint(
            f"status IN ('{KnowledgeBaseStatus.ACTIVE}', '{KnowledgeBaseStatus.ARCHIVED}')",
            name="ck_knowledge_bases_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<KnowledgeBase(id={self.id}, name='{self.name}', status='{self.status}')>"
