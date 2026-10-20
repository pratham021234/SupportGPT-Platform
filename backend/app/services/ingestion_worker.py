"""Durable background worker for asynchronous event processing, claiming, and crash recovery."""

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.errors import EventNormalizationException
from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.db.tenant import set_tenant_rls_context
from app.models.enums import IngestionStatus
from app.models.event_source import EventSource
from app.models.ingestion_receipt import IngestionReceipt
from app.schemas.ingestion import WorkerHealthResponse
from app.services.event_normalizer import EventNormalizer
from app.services.ingestion_processor import IngestionProcessor

logger = get_logger("supportgpt.ingestion.worker")


class IngestionWorker:
    """Authoritative background worker claiming and executing durable event processing jobs."""

    def __init__(
        self,
        worker_id: str | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.session_factory = session_factory or async_session_factory
        self.is_running = False
        self._task: asyncio.Task | None = None

    async def claim_batch(
        self,
        session: AsyncSession,
        batch_size: int | None = None,
        lease_timeout_seconds: int | None = None,
    ) -> list[uuid.UUID]:
        """Claim a batch of queued or expired-lease events using PostgreSQL FOR UPDATE SKIP LOCKED.

        Ensures multiple workers never process the same event concurrently.
        """
        limit = batch_size or settings.INGESTION_WORKER_BATCH_SIZE
        timeout_sec = lease_timeout_seconds or settings.INGESTION_LEASE_TIMEOUT_SECONDS
        now = datetime.now(UTC)
        lease_cutoff = now - timedelta(seconds=timeout_sec)

        # 1. Identify eligible candidates
        # Eligible: queued/retry_wait with due timestamp OR hung processing lease
        stmt = (
            select(IngestionReceipt.id)
            .where(
                or_(
                    (
                        IngestionReceipt.status.in_(
                            [IngestionStatus.QUEUED, IngestionStatus.RETRY_WAIT]
                        )
                        & (
                            IngestionReceipt.next_attempt_at.is_(None)
                            | (IngestionReceipt.next_attempt_at <= now)
                        )
                    ),
                    (
                        (IngestionReceipt.status == IngestionStatus.PROCESSING)
                        & (IngestionReceipt.processing_started_at < lease_cutoff)
                    ),
                )
            )
            .order_by(IngestionReceipt.received_at.asc())
            .limit(limit)
        )

        # Attempt FOR UPDATE SKIP LOCKED if dialect supports it (PostgreSQL)
        bind = session.bind
        dialect_name = bind.dialect.name if bind else ""
        if dialect_name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)

        result = await session.execute(stmt)
        candidate_ids = [row[0] for row in result.all()]

        if not candidate_ids:
            return []

        # 2. Atomically transition claimed records to PROCESSING
        claim_update = (
            update(IngestionReceipt)
            .where(IngestionReceipt.id.in_(candidate_ids))
            .values(
                status=IngestionStatus.PROCESSING,
                processing_started_at=now,
                locked_by=self.worker_id,
                attempt_count=IngestionReceipt.attempt_count + 1,
            )
        )
        await session.execute(claim_update)
        await session.commit()

        logger.info(
            f"Worker [{self.worker_id}] claimed {len(candidate_ids)} event(s) for processing"
        )
        return candidate_ids

    async def process_single_receipt(
        self,
        receipt_id: uuid.UUID,
    ) -> bool:
        """Execute normalization and domain transformation for one claimed receipt in its own transaction."""
        now = datetime.now(UTC)

        async with self.session_factory() as session:
            # 1. Fetch receipt
            res = await session.execute(
                select(IngestionReceipt).where(IngestionReceipt.id == receipt_id)
            )
            receipt = res.scalar_one_or_none()
            if not receipt:
                return False

            # Set RLS context for tenant isolation
            try:
                await set_tenant_rls_context(session, receipt.organization_id)
            except Exception:
                pass

            # 2. Fetch associated EventSource
            source = None
            if receipt.source_id:
                src_res = await session.execute(
                    select(EventSource).where(EventSource.id == receipt.source_id)
                )
                source = src_res.scalar_one_or_none()

            # If no source record exists, construct a synthetic provider source descriptor
            if not source:
                source = EventSource(
                    id=receipt.source_id or uuid.uuid4(),
                    organization_id=receipt.organization_id,
                    provider=receipt.source_provider,
                    name=f"Provider-{receipt.source_provider}",
                    signing_secret_hash="",
                )

            # 3. Normalize Event
            try:
                raw_payload = receipt.payload or {}
                canonical_event = EventNormalizer.normalize(
                    source=source,
                    payload=raw_payload,
                    headers={"x-correlation-id": receipt.correlation_id or ""},
                )
            except (EventNormalizationException, ValueError) as norm_err:
                logger.warning(
                    f"Receipt [{receipt_id}] permanent normalization failure: {norm_err}"
                )
                await session.rollback()
                await self._mark_failed(
                    receipt_id,
                    status=IngestionStatus.DEAD_LETTER,
                    error_code="NORMALIZATION_FAILED",
                    error_summary=str(norm_err)[:255],
                )
                return False

            # 4. Apply Domain Mutation
            try:
                await IngestionProcessor.process_event(session, canonical_event, receipt)

                # Successful processing: transition receipt to PROCESSED
                receipt.status = IngestionStatus.PROCESSED
                receipt.processed_at = now
                receipt.locked_by = None
                receipt.error_code = None
                receipt.error_summary = None

                await session.commit()
                logger.info(f"Receipt [{receipt_id}] processed successfully to domain models")
                return True

            except Exception as proc_exc:
                logger.exception(f"Receipt [{receipt_id}] processing error: {proc_exc}")
                await session.rollback()

                # Determine whether failure is transient or permanent
                is_transient = not isinstance(proc_exc, (EventNormalizationException, ValueError))
                await self._handle_failure(receipt_id, proc_exc, is_transient=is_transient)
                return False

    async def _handle_failure(
        self,
        receipt_id: uuid.UUID,
        error: Exception,
        is_transient: bool = True,
    ) -> None:
        """Record retry schedule with exponential backoff or dead-letter transition."""
        now = datetime.now(UTC)
        error_msg = str(error)[:255]

        async with self.session_factory() as session:
            res = await session.execute(
                select(IngestionReceipt).where(IngestionReceipt.id == receipt_id)
            )
            receipt = res.scalar_one_or_none()
            if not receipt:
                return

            if not is_transient or receipt.attempt_count >= settings.INGESTION_MAX_ATTEMPTS:
                # Transition to DEAD_LETTER
                receipt.status = IngestionStatus.DEAD_LETTER
                receipt.error_code = "MAX_ATTEMPTS_EXCEEDED" if is_transient else "PERMANENT_ERROR"
                receipt.error_summary = error_msg
                receipt.processed_at = now
                receipt.locked_by = None
                logger.warning(
                    f"Receipt [{receipt_id}] moved to DEAD_LETTER after {receipt.attempt_count} attempts"
                )
            else:
                # Retry with exponential backoff and jitter
                backoff_base = 2 ** (receipt.attempt_count - 1) * 5
                jitter = random.uniform(0.1, 1.0)
                delay_sec = min(3600, backoff_base + jitter)

                receipt.status = IngestionStatus.RETRY_WAIT
                receipt.next_attempt_at = now + timedelta(seconds=delay_sec)
                receipt.error_code = "TRANSIENT_ERROR"
                receipt.error_summary = error_msg
                receipt.locked_by = None
                logger.info(
                    f"Receipt [{receipt_id}] scheduled for retry #{receipt.attempt_count + 1} in {delay_sec:.1f}s"
                )

            await session.commit()

    async def _mark_failed(
        self,
        receipt_id: uuid.UUID,
        status: IngestionStatus,
        error_code: str,
        error_summary: str,
    ) -> None:
        """Atomically mark receipt in terminal or quarantine state."""
        async with self.session_factory() as session:
            await session.execute(
                update(IngestionReceipt)
                .where(IngestionReceipt.id == receipt_id)
                .values(
                    status=status,
                    error_code=error_code,
                    error_summary=error_summary,
                    processed_at=datetime.now(UTC),
                    locked_by=None,
                )
            )
            await session.commit()

    async def run_once(self, batch_size: int | None = None) -> dict[str, int]:
        """Claim a single batch and process all claimed items to completion."""
        async with self.session_factory() as claim_session:
            claimed_ids = await self.claim_batch(claim_session, batch_size=batch_size)

        if not claimed_ids:
            return {"claimed": 0, "processed": 0, "failed": 0}

        processed = 0
        failed = 0
        for rid in claimed_ids:
            success = await self.process_single_receipt(rid)
            if success:
                processed += 1
            else:
                failed += 1

        return {"claimed": len(claimed_ids), "processed": processed, "failed": failed}

    async def start(self) -> None:
        """Start the continuous background worker loop."""
        if self.is_running:
            return
        self.is_running = True
        logger.info(f"IngestionWorker [{self.worker_id}] starting loop...")

        while self.is_running:
            try:
                stats = await self.run_once()
                if stats["claimed"] == 0:
                    await asyncio.sleep(settings.INGESTION_WORKER_POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                logger.info(f"IngestionWorker [{self.worker_id}] received shutdown signal.")
                break
            except Exception as loop_exc:
                logger.error(f"IngestionWorker [{self.worker_id}] loop error: {loop_exc}")
                await asyncio.sleep(settings.INGESTION_WORKER_POLL_INTERVAL_SECONDS)

        self.is_running = False
        logger.info(f"IngestionWorker [{self.worker_id}] stopped gracefully.")

    def stop(self) -> None:
        """Signal the worker to stop processing."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()

    @classmethod
    async def get_health_metrics(cls, session: AsyncSession) -> WorkerHealthResponse:
        """Query queue health, backlog counts, and dead-letter statistics."""
        # 1. Queue depth (queued or retry_wait)
        qd_res = await session.execute(
            select(func.count(IngestionReceipt.id)).where(
                IngestionReceipt.status.in_([IngestionStatus.QUEUED, IngestionStatus.RETRY_WAIT])
            )
        )
        queue_depth = qd_res.scalar() or 0

        # 2. In-flight processing
        proc_res = await session.execute(
            select(func.count(IngestionReceipt.id)).where(
                IngestionReceipt.status == IngestionStatus.PROCESSING
            )
        )
        processing_count = proc_res.scalar() or 0

        # 3. Dead letter
        dl_res = await session.execute(
            select(func.count(IngestionReceipt.id)).where(
                IngestionReceipt.status == IngestionStatus.DEAD_LETTER
            )
        )
        dead_letter_count = dl_res.scalar() or 0

        # 4. Quarantined
        q_res = await session.execute(
            select(func.count(IngestionReceipt.id)).where(
                IngestionReceipt.status == IngestionStatus.QUARANTINED
            )
        )
        quarantined_count = q_res.scalar() or 0

        return WorkerHealthResponse(
            status="running" if default_worker and default_worker.is_running else "stopped",
            worker_id=default_worker.worker_id if default_worker else None,
            queue_depth=queue_depth,
            processing_count=processing_count,
            dead_letter_count=dead_letter_count,
            quarantined_count=quarantined_count,
            lease_timeout_seconds=settings.INGESTION_LEASE_TIMEOUT_SECONDS,
            active_workers=1 if default_worker and default_worker.is_running else 0,
        )


# Singleton worker instance for application lifecycle
default_worker: IngestionWorker | None = None


def get_default_worker() -> IngestionWorker:
    """Provide singleton worker instance."""
    global default_worker
    if default_worker is None:
        default_worker = IngestionWorker()
    return default_worker
