import asyncio
import uuid
from app.db.session import async_session_factory
from app.models.document_version import DocumentVersion
from app.models.enums import DocumentProcessingStatus
from app.services.document_worker import DocumentWorker
from sqlalchemy import select, text

async def main():
    async with async_session_factory() as session:
        await session.execute(text("SELECT set_config('app.is_system_admin', 'true', true)"))
        # Find failed or queued versions
        vers = (await session.execute(select(DocumentVersion))).scalars().all()
        for v in vers:
            print(f"Resetting version {v.id} from {v.processing_status} to QUEUED...")
            v.processing_status = DocumentProcessingStatus.QUEUED
            v.attempt_count = 0
            v.error_code = None
            v.error_summary = None
            v.locked_by = None
            v.next_attempt_at = None
        await session.commit()

    worker = DocumentWorker(session_factory=async_session_factory)
    claimed = await worker.claim_batch(batch_size=5)
    print(f"Claimed {len(claimed)} versions: {claimed}")
    for vid in claimed:
        success = await worker.process_version(vid)
        print(f"Processing version {vid}: success={success}")

    async with async_session_factory() as session:
        await session.execute(text("SELECT set_config('app.is_system_admin', 'true', true)"))
        vers = (await session.execute(select(DocumentVersion))).scalars().all()
        for v in vers:
            print(f"Final Version Status: {v.id} | Status: {v.processing_status} | Chunks: {v.chunk_count}")

if __name__ == "__main__":
    asyncio.run(main())
