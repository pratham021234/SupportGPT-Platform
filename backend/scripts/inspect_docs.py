import asyncio
from app.db.session import async_session_factory
from app.models.document_version import DocumentVersion
from app.models.document_chunk import DocumentChunk
from sqlalchemy import select, text

async def check():
    async with async_session_factory() as session:
        await session.execute(text("SELECT set_config('app.is_system_admin', 'true', true)"))
        vers = (await session.execute(select(DocumentVersion))).scalars().all()
        for v in vers:
            print(f"Version: {v.id} | {v.original_filename} | Status: {v.processing_status} | Chunks: {v.chunk_count} | Error: {v.error_summary}")
        chunks = (await session.execute(select(DocumentChunk))).scalars().all()
        print(f"Total Chunks in DB: {len(chunks)}")
        for c in chunks[:5]:
            print(f"  Chunk #{c.sequence_number} ({c.word_count} words): {c.content[:80]}...")

if __name__ == "__main__":
    asyncio.run(check())
