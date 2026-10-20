"""Authoritative domain service for source administration, webhook reception, and receipt replay."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ConflictException,
    ForbiddenException,
    InvalidContentTypeException,
    ResourceNotFoundException,
)
from app.core.logging import get_logger
from app.db.tenant import set_tenant_rls_context
from app.models.enums import IngestionStatus, SourceStatus
from app.models.event_source import EventSource
from app.models.ingestion_receipt import IngestionReceipt
from app.schemas.event_source import SourceCreateRequest, SourceUpdateRequest
from app.services.secret_resolver import SecretResolver
from app.services.webhook_verifier import WebhookVerifier

logger = get_logger("supportgpt.ingestion.service")


class IngestionService:
    """Manages source integrations, webhook authentication, receipt storage, and operator replay."""

    # --------------------------------------------------------------------------
    # 1. Source Integrations Administration
    # --------------------------------------------------------------------------

    @classmethod
    async def create_source(
        cls,
        session: AsyncSession,
        organization_id: uuid.UUID,
        payload: SourceCreateRequest,
    ) -> tuple[EventSource, str]:
        """Provision a new external event source and generate a signing secret returned exactly once."""
        try:
            await set_tenant_rls_context(session, organization_id)
        except Exception:
            pass

        # Generate or resolve secret
        raw_secret = SecretResolver.generate_secret()
        secret_hash = SecretResolver.hash_secret(raw_secret)
        preview = SecretResolver.make_preview(raw_secret)
        encrypted_secret = SecretResolver.encrypt_secret(raw_secret)

        source = EventSource(
            organization_id=organization_id,
            name=payload.name,
            provider=payload.provider.value,
            status=SourceStatus.ACTIVE,
            external_account_id=payload.external_account_id,
            signing_secret_hash=secret_hash,
            signing_secret_encrypted=encrypted_secret,
            secret_reference=payload.secret_reference,
            signing_secret_preview=preview,
            supported_event_types=payload.supported_event_types,
        )
        session.add(source)
        await session.flush()
        await session.refresh(source)

        logger.info(
            f"Created event source [{source.id}] for provider [{source.provider}] in organization [{organization_id}]"
        )
        return source, raw_secret

    @classmethod
    async def get_source(
        cls,
        session: AsyncSession,
        organization_id: uuid.UUID,
        source_id: uuid.UUID,
    ) -> EventSource:
        """Retrieve source configuration strictly scoped to organization."""
        query = select(EventSource).where(
            EventSource.id == source_id,
            EventSource.organization_id == organization_id,
        )
        res = await session.execute(query)
        source = res.scalar_one_or_none()
        if not source:
            raise ResourceNotFoundException("EventSource", source_id)
        return source

    @classmethod
    async def list_sources(
        cls,
        session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> list[EventSource]:
        """List all external sources configured for the organization."""
        query = (
            select(EventSource)
            .where(EventSource.organization_id == organization_id)
            .order_by(EventSource.created_at.desc())
        )
        res = await session.execute(query)
        return list(res.scalars().all())

    @classmethod
    async def update_source(
        cls,
        session: AsyncSession,
        organization_id: uuid.UUID,
        source_id: uuid.UUID,
        payload: SourceUpdateRequest,
    ) -> EventSource:
        """Update mutable properties of an event source."""
        source = await cls.get_source(session, organization_id, source_id)

        if payload.name is not None:
            source.name = payload.name
        if payload.status is not None:
            source.status = payload.status.value
        if payload.external_account_id is not None:
            source.external_account_id = payload.external_account_id
        if payload.secret_reference is not None:
            source.secret_reference = payload.secret_reference
        if payload.supported_event_types is not None:
            source.supported_event_types = payload.supported_event_types

        source.updated_at = datetime.now(UTC)
        await session.flush()
        await session.refresh(source)
        return source

    @classmethod
    async def rotate_secret(
        cls,
        session: AsyncSession,
        organization_id: uuid.UUID,
        source_id: uuid.UUID,
    ) -> tuple[EventSource, str]:
        """Rotate the signing secret for an event source, invalidating previous credentials."""
        source = await cls.get_source(session, organization_id, source_id)

        raw_secret = SecretResolver.generate_secret()
        source.signing_secret_hash = SecretResolver.hash_secret(raw_secret)
        source.signing_secret_encrypted = SecretResolver.encrypt_secret(raw_secret)
        source.signing_secret_preview = SecretResolver.make_preview(raw_secret)
        source.updated_at = datetime.now(UTC)

        await session.flush()
        await session.refresh(source)
        logger.info(f"Rotated signing secret for source [{source.id}] in org [{organization_id}]")
        return source, raw_secret

    # --------------------------------------------------------------------------
    # 2. Inbound Webhook Reception & Verification
    # --------------------------------------------------------------------------

    @classmethod
    async def receive_webhook(
        cls,
        session: AsyncSession,
        source_id: uuid.UUID,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> tuple[IngestionReceipt, bool]:
        """Verify, authenticate, and durably record an inbound external webhook event.

        Returns:
            tuple[IngestionReceipt, is_duplicate]
        """
        # 1. Transport Constraints
        content_type = headers.get("content-type")
        WebhookVerifier.validate_content_type(content_type)
        WebhookVerifier.validate_payload_size(raw_body)

        # 2. Resolve Source Configuration
        # Query source by source_id across all organizations
        src_res = await session.execute(select(EventSource).where(EventSource.id == source_id))
        source = src_res.scalar_one_or_none()
        if not source:
            raise ResourceNotFoundException("EventSource", source_id)

        if source.status != SourceStatus.ACTIVE:
            raise ForbiddenException(f"Event source '{source_id}' is inactive or revoked.")

        # 3. Resolve Secret & Verify Authenticity
        secret = SecretResolver.resolve_source_signing_secret(source)
        sig_header = headers.get("x-supportgpt-signature") or headers.get("x-signature")
        ts_header = headers.get("x-supportgpt-timestamp") or headers.get("x-timestamp")

        WebhookVerifier.verify_timestamp(ts_header)
        WebhookVerifier.verify_signature(raw_body, sig_header, secret)

        # 4. Parse JSON & Extract Event Identifiers
        try:
            payload_json: dict[str, Any] = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except Exception:
            raise InvalidContentTypeException("Malformed JSON request body.") from None

        external_event_id = (
            headers.get("x-supportgpt-event-id")
            or payload_json.get("event_id")
            or payload_json.get("id")
        )
        if not external_event_id:
            raise ConflictException(
                "Missing required external event identifier ('event_id' or 'X-SupportGPT-Event-ID').",
                code="MISSING_EVENT_IDENTIFIER",
            )

        event_type = (
            headers.get("x-supportgpt-event-type")
            or payload_json.get("event_type")
            or payload_json.get("type")
            or "generic.event"
        )

        # Check supported event types
        if source.supported_event_types and event_type not in source.supported_event_types:
            logger.warning(f"Source [{source_id}] received unsupported event type [{event_type}]")

        # 5. Compute Payload Digest for Deduplication & Conflict Detection
        payload_digest = hashlib.sha256(raw_body).hexdigest()
        correlation_id = headers.get("x-correlation-id") or headers.get("x-request-id")

        # Set tenant context before querying/inserting receipts
        try:
            await set_tenant_rls_context(session, source.organization_id)
        except Exception:
            pass

        # 6. Database-Level Deduplication Check
        existing_res = await session.execute(
            select(IngestionReceipt).where(
                IngestionReceipt.organization_id == source.organization_id,
                IngestionReceipt.source_provider == source.provider,
                IngestionReceipt.external_event_id == str(external_event_id),
            )
        )
        existing = existing_res.scalar_one_or_none()

        if existing:
            # Check if payload matches
            if existing.payload_digest and existing.payload_digest != payload_digest:
                logger.warning(
                    f"Deduplication conflict: Event ID [{external_event_id}] arrived with differing payload digest"
                )
                raise ConflictException(
                    "Event ID already exists with differing payload digest.",
                    code="EVENT_PAYLOAD_MISMATCH",
                )

            logger.info(
                f"Idempotent duplicate webhook received for [{source.provider}:{external_event_id}]"
            )
            return existing, True

        # 7. Create Durable Ingestion Receipt in QUEUED State
        now = datetime.now(UTC)
        receipt = IngestionReceipt(
            organization_id=source.organization_id,
            source_id=source.id,
            source_provider=source.provider,
            external_event_id=str(external_event_id),
            event_type=str(event_type),
            status=IngestionStatus.QUEUED,
            received_at=now,
            attempt_count=0,
            next_attempt_at=now,
            payload_digest=payload_digest,
            payload=payload_json,
            correlation_id=str(correlation_id) if correlation_id else None,
            schema_version="1.0",
        )
        session.add(receipt)
        await session.flush()

        logger.info(
            f"Durable receipt [{receipt.id}] recorded in QUEUED state for source [{source_id}]"
        )
        return receipt, False

    # --------------------------------------------------------------------------
    # 3. Operational Receipts Inspection & Replay
    # --------------------------------------------------------------------------

    @classmethod
    async def list_receipts(
        cls,
        session: AsyncSession,
        organization_id: uuid.UUID,
        status: IngestionStatus | None = None,
        provider: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[IngestionReceipt], int]:
        """List ingestion receipts strictly scoped to organization with optional filtering."""
        limit = min(max(1, limit), 100)
        offset = max(0, offset)

        base_query = select(IngestionReceipt).where(
            IngestionReceipt.organization_id == organization_id
        )
        if status:
            base_query = base_query.where(IngestionReceipt.status == status.value)
        if provider:
            base_query = base_query.where(IngestionReceipt.source_provider == provider)

        # Count total
        count_stmt = select(func.count()).select_from(base_query.subquery())
        count_res = await session.execute(count_stmt)
        total = count_res.scalar() or 0

        # Query items
        items_stmt = (
            base_query.order_by(IngestionReceipt.received_at.desc()).limit(limit).offset(offset)
        )
        items_res = await session.execute(items_stmt)
        items = list(items_res.scalars().all())

        return items, total

    @classmethod
    async def get_receipt(
        cls,
        session: AsyncSession,
        organization_id: uuid.UUID,
        receipt_id: uuid.UUID,
    ) -> IngestionReceipt:
        """Retrieve single ingestion receipt with tenant isolation enforcement."""
        query = select(IngestionReceipt).where(
            IngestionReceipt.id == receipt_id,
            IngestionReceipt.organization_id == organization_id,
        )
        res = await session.execute(query)
        receipt = res.scalar_one_or_none()
        if not receipt:
            raise ResourceNotFoundException("IngestionReceipt", receipt_id)
        return receipt

    @classmethod
    async def replay_receipt(
        cls,
        session: AsyncSession,
        organization_id: uuid.UUID,
        receipt_id: uuid.UUID,
        force: bool = False,
    ) -> IngestionReceipt:
        """Reset a dead-lettered or failed receipt back to QUEUED for background reprocessing."""
        receipt = await cls.get_receipt(session, organization_id, receipt_id)

        eligible_states = (
            IngestionStatus.DEAD_LETTER,
            IngestionStatus.FAILED,
            IngestionStatus.QUARANTINED,
        )
        if not force and receipt.status not in eligible_states:
            raise ConflictException(
                f"Receipt [{receipt_id}] is in state '{receipt.status}'. Only events in {list(eligible_states)} can be replayed unless force=True.",
                code="RECEIPT_NOT_REPLAYABLE",
            )

        now = datetime.now(UTC)
        receipt.status = IngestionStatus.QUEUED
        receipt.attempt_count = 0
        receipt.next_attempt_at = now
        receipt.processing_started_at = None
        receipt.locked_by = None
        receipt.error_code = None
        receipt.error_summary = None
        receipt.processed_at = None

        await session.flush()
        await session.refresh(receipt)
        logger.info(
            f"Receipt [{receipt_id}] re-queued for replay by operator in org [{organization_id}]"
        )
        return receipt
