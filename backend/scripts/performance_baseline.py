"""Automated performance and capacity baseline benchmark.

Measures actual application component latency, throughput, and resource
characteristics across core operations:
1. Password hashing (Argon2id memory-hard verification).
2. Database query latency (pool checkout & simple query).
3. Hierarchical document chunking throughput.
4. Semantic embedding generation latency (FastEmbed / OpenAI).
5. Response verification claim extraction and policy evaluation.
"""

import argparse
import asyncio
import json
import statistics
import time
from datetime import UTC, datetime

from sqlalchemy import text

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.db.session import async_session_factory
from app.services.chunking import HierarchicalStructuralChunker
from app.services.rag.embedding import get_embedding_provider
from app.services.verification.claim_extractor import ClaimExtractor
from app.services.verification.policy_evaluator import PolicyEvaluator

logger = get_logger("supportgpt.baseline")


def percentile(data: list[float], p: float) -> float:
    """Calculate the p-th percentile of a list of floats."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * (p / 100.0))
    idx = min(idx, len(sorted_data) - 1)
    return round(sorted_data[idx], 2)


async def benchmark_database_query_latency(iterations: int = 50) -> dict:
    """Measure PostgreSQL connection pool checkout and query execution latency."""
    latencies: list[float] = []

    for _ in range(iterations):
        t0 = time.perf_counter()
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1;"))
        latencies.append((time.perf_counter() - t0) * 1000)

    return {
        "iterations": iterations,
        "mean_ms": round(statistics.mean(latencies), 2),
        "min_ms": round(min(latencies), 2),
        "max_ms": round(max(latencies), 2),
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "p99_ms": percentile(latencies, 99),
    }


def benchmark_password_hashing(iterations: int = 5) -> dict:
    """Measure Argon2id cryptographic password hashing and verification latency."""
    hash_latencies: list[float] = []
    verify_latencies: list[float] = []

    sample_pwd = "P@ssw0rd!EnterpriseSecurity2026"

    for _ in range(iterations):
        t0 = time.perf_counter()
        hashed = hash_password(sample_pwd)
        hash_latencies.append((time.perf_counter() - t0) * 1000)

        t1 = time.perf_counter()
        verify_password(sample_pwd, hashed)
        verify_latencies.append((time.perf_counter() - t1) * 1000)

    return {
        "iterations": iterations,
        "hash_mean_ms": round(statistics.mean(hash_latencies), 2),
        "hash_p50_ms": percentile(hash_latencies, 50),
        "verify_mean_ms": round(statistics.mean(verify_latencies), 2),
        "verify_p50_ms": percentile(verify_latencies, 50),
    }


def benchmark_chunking_throughput(iterations: int = 20) -> dict:
    """Measure document chunking and hierarchy extraction throughput."""
    sample_markdown = (
        """# Enterprise Knowledge Base Policy
## Section 1: Refund Policy
Customers are eligible for a 30-day money-back guarantee for unused software licenses.
Refund requests must be accompanied by the original transaction identifier and account email.
Late requests or accounts flagged for abuse will not be granted exceptions under any circumstances.

## Section 2: Technical SLA
Enterprise tier customers receive 99.99% uptime guarantees with a 15-minute response SLA.
Standard tier accounts receive 99.9% uptime with 4-hour business day support.
Severity 1 incidents trigger immediate on-call escalation and real-time status page updates.

## Section 3: Data Retention and Compliance
All customer message data is retained for 90 days following ticket resolution.
GDPR erasure requests are processed asynchronously within 14 calendar days.
Database backups are encrypted at rest with AES-256 and stored across redundant availability zones.
"""
        * 5
    )

    total_chars = len(sample_markdown)
    chunker = HierarchicalStructuralChunker(chunk_size=400, chunk_overlap=50)

    latencies: list[float] = []
    total_chunks_created = 0

    for _ in range(iterations):
        t0 = time.perf_counter()
        chunks = chunker.chunk(sample_markdown)
        latencies.append((time.perf_counter() - t0) * 1000)
        total_chunks_created = len(chunks)

    mean_ms = statistics.mean(latencies)
    throughput_kb_s = round((total_chars / 1024) / (mean_ms / 1000), 2) if mean_ms > 0 else 0

    return {
        "iterations": iterations,
        "document_chars": total_chars,
        "chunks_generated": total_chunks_created,
        "mean_latency_ms": round(mean_ms, 2),
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "throughput_kb_per_sec": throughput_kb_s,
    }


async def benchmark_embedding_latency(iterations: int = 10) -> dict:
    """Measure dense semantic embedding generation latency using active provider."""
    provider = get_embedding_provider()
    sample_queries = [
        "What is the company refund policy for unused software licenses?",
        "How do I escalate a severity 1 production outage under the SLA?",
        "What is the retention period for closed customer tickets?",
        "Can I request complete erasure of account data under GDPR?",
    ]

    latencies: list[float] = []

    for _ in range(iterations):
        t0 = time.perf_counter()
        _vectors = await provider.embed_texts(sample_queries)
        latencies.append((time.perf_counter() - t0) * 1000)

    return {
        "provider": provider.__class__.__name__,
        "model": provider.model_name,
        "dimensions": provider.dimensions,
        "batch_size": len(sample_queries),
        "iterations": iterations,
        "mean_batch_ms": round(statistics.mean(latencies), 2),
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "per_query_ms": round(statistics.mean(latencies) / len(sample_queries), 2),
    }


def benchmark_claim_extraction_and_policy(iterations: int = 20) -> dict:
    """Measure atomic claim extraction and policy rule evaluation latency."""
    extractor = ClaimExtractor()
    evaluator = PolicyEvaluator()

    sample_draft = (
        "Hello! According to our documentation, you are eligible for a 100% money-back refund "
        "within 30 days of purchase. Our enterprise SLA guarantees 99.99% uptime with 15-minute response. "
        "Your account data will be retained for 90 days following resolution."
    )

    latencies: list[float] = []

    for _ in range(iterations):
        t0 = time.perf_counter()
        _claims = extractor.extract_claims(sample_draft)
        _findings = evaluator.evaluate_policies(
            draft_text=sample_draft, claim_results=[], policies=[]
        )
        latencies.append((time.perf_counter() - t0) * 1000)

    return {
        "iterations": iterations,
        "mean_latency_ms": round(statistics.mean(latencies), 2),
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
    }


async def run_full_baseline(output_file: str | None = None) -> dict:
    """Execute all performance baseline benchmarks and output structured report."""
    logger.info("Starting SupportGPT performance & capacity baseline benchmarks...")

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "environment": settings.ENVIRONMENT,
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "benchmarks": {},
    }

    logger.info("1/5 Measuring database query latency...")
    try:
        report["benchmarks"]["database_query"] = await benchmark_database_query_latency()
    except Exception as exc:
        report["benchmarks"]["database_query"] = {"error": str(exc)}

    logger.info("2/5 Measuring Argon2id password hashing latency...")
    report["benchmarks"]["password_hashing"] = benchmark_password_hashing()

    logger.info("3/5 Measuring document chunking throughput...")
    report["benchmarks"]["document_chunking"] = benchmark_chunking_throughput()

    logger.info("4/5 Measuring semantic embedding latency...")
    report["benchmarks"]["embedding_generation"] = await benchmark_embedding_latency()

    logger.info("5/5 Measuring claim extraction & policy evaluation latency...")
    report["benchmarks"]["claim_and_policy"] = benchmark_claim_extraction_and_policy()

    logger.info("Performance baseline benchmark completed successfully.")

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        logger.info("Baseline report saved to %s", output_file)

    return report


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="SupportGPT Performance Baseline Benchmark")
    parser.add_argument(
        "--output", default="performance_baseline.json", help="Output JSON filepath"
    )
    args = parser.parse_args()

    res = asyncio.run(run_full_baseline(output_file=args.output))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
