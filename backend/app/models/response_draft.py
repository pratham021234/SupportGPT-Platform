"""Response draft model representing an AI-generated support response candidate."""

import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DraftLifecycleStatus


class ResponseDraft(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Canonical model for an AI-generated support response draft and its revision history."""

    __tablename__ = "response_drafts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant owning this response draft",
    )
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Optional ticket associated with this response draft",
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Optional conversation associated with this response draft",
    )
    original_query: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Original customer query or message context prompting this draft",
    )
    draft_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Content of the AI-generated or revised response draft",
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Monotonically increasing version number for this draft",
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DraftLifecycleStatus.DRAFT.value,
        index=True,
        comment="Current verification and approval lifecycle state",
    )
    evidence_references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Serialized retrieved evidence references linked to this draft",
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who created or initiated the draft, if applicable",
    )
    lock_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Optimistic concurrency control lock version",
    )

    __table_args__ = (
        CheckConstraint(
            "version_number >= 1",
            name="ck_response_drafts_version_positive",
        ),
        CheckConstraint(
            "length(draft_text) > 0",
            name="ck_response_drafts_text_nonempty",
        ),
        ForeignKeyConstraint(
            ["ticket_id", "organization_id"],
            ["tickets.id", "tickets.organization_id"],
            name="fk_response_drafts_ticket_tenant",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["conversations.id", "conversations.organization_id"],
            name="fk_response_drafts_conversation_tenant",
            ondelete="SET NULL",
        ),
        Index(
            "ix_response_drafts_org_status",
            "organization_id",
            "lifecycle_status",
        ),
        Index(
            "ix_response_drafts_org_ticket",
            "organization_id",
            "ticket_id",
        ),
    )
