"""Evaluation Runner for SupportGPT RAG Subsystem.

Executes the reviewed evaluation dataset against reference enterprise knowledge documents,
computes deterministic retrieval and answer metrics, and records exact measured results.
"""

import asyncio
import json
import uuid

from qdrant_client import QdrantClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.enums import OrganizationStatus
from app.models.organization import Organization
from app.services.document_service import DocumentService
from app.services.document_worker import DocumentWorker
from app.services.rag.answer import GroundedAnswerService
from app.services.rag.embedding import FastEmbedEmbeddingProvider
from app.services.rag.evaluation import EVALUATION_DATASET, RAGEvaluator
from app.services.rag.qdrant_store import QdrantStoreManager
from app.services.rag.retrieval import RetrievalService

DOC_SECURITY_POLICY = b"""# Enterprise Security Policy

## Password Controls
All user accounts require a minimum password length of 16 characters with complexity. Passwords must include uppercase, lowercase, numbers, and symbols.

## Encryption Standard
All sensitive customer data must undergo data encryption at rest using AES-256 cipher standards with envelope key encryption.

## Session Management
Administrative user sessions automatically expire after 15 minutes of session idle timeout.
"""

DOC_SLA_AGREEMENT = b"""# Customer SLA Agreement

## Incident Severity Levels
Priority 1 Critical incidents have an initial response target of 15 minutes with 24/7 engineer dispatch.
Priority 2 Major degradation incidents have an initial response target of 2 hours.

## Refund Policy
Customers can request billing refunds within 30 days of invoice generation.
"""


async def run_evaluation() -> dict:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON;"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    org_id = uuid.uuid4()

    async with session_factory() as db:
        org = Organization(
            id=org_id, name="Eval Corp", slug="eval-corp", status=OrganizationStatus.ACTIVE
        )
        db.add(org)
        await db.commit()

    qdrant_store = QdrantStoreManager(
        collection_name="eval_knowledge_chunks",
        dimensions=384,
        client=QdrantClient(location=":memory:"),
    )
    embedding_provider = FastEmbedEmbeddingProvider(dimensions=384)
    worker = DocumentWorker(
        session_factory=session_factory,
        embedding_provider=embedding_provider,
        qdrant_store=qdrant_store,
    )

    # Ingest Reference Documents
    async with session_factory() as db:
        service = DocumentService(db)
        kb = await service.create_knowledge_base(org_id, name="Reference Policies")
        await service.upload_document(
            org_id, kb.id, "security.md", DOC_SECURITY_POLICY, title="Enterprise Security Policy"
        )
        await service.upload_document(
            org_id, kb.id, "sla.md", DOC_SLA_AGREEMENT, title="Customer SLA Agreement"
        )

    # Process all documents into Qdrant
    await worker.run_once()
    await worker.run_once()

    evaluator = RAGEvaluator(
        embedding_provider="fastembed", embedding_model="BAAI/bge-small-en-v1.5"
    )
    case_results = []

    answer_service = GroundedAnswerService()

    async with session_factory() as db:
        retrieval_service = RetrievalService(
            session=db,
            embedding_provider=embedding_provider,
            qdrant_store=qdrant_store,
        )

        for case in EVALUATION_DATASET:
            evidence, latency_ms = await retrieval_service.retrieve(
                query=case.question,
                organization_id=org_id,
                top_k=4,
                enable_hybrid=True,
            )
            answer_result = await answer_service.generate_answer(
                question=case.question,
                evidence=evidence,
                retrieval_latency_ms=latency_ms,
            )
            res = evaluator.evaluate_query(case, evidence, answer_result)
            case_results.append(res)

    report = evaluator.compile_report(case_results)
    await engine.dispose()
    return report.model_dump(mode="json")


if __name__ == "__main__":
    report_dict = asyncio.run(run_evaluation())
    print("=== RAG EVALUATION REPORT ===")
    print(json.dumps(report_dict, indent=2))
