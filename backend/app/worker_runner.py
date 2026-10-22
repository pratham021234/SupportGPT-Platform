"""Standalone background worker runner for production container deployments.

Decouples asynchronous background worker execution (event ingestion,
document extraction, chunking, and vector indexing) from the web API processes.
Supports graceful shutdown on SIGTERM / SIGINT signals.
"""

import argparse
import asyncio
import signal
import sys

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.db.session import async_engine, async_session_factory
from app.services.document_worker import DocumentWorker
from app.services.ingestion_worker import get_default_worker

logger = get_logger("supportgpt.worker_runner")


async def run_workers(mode: str = "all") -> None:
    """Run specified background worker loop(s) with graceful shutdown."""
    setup_logging(log_level=settings.LOG_LEVEL, environment=settings.ENVIRONMENT)
    logger.info("Initializing standalone worker runner in mode: '%s'", mode)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    # Register OS signal handlers (Unix SIGTERM/SIGINT; Windows SIGINT/SIGTERM where supported)
    def handle_signal(sig: int) -> None:
        logger.info("Received termination signal %s. Initiating graceful shutdown...", sig)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))
        except NotImplementedError:
            # Windows may not support add_signal_handler on ProactorEventLoop
            signal.signal(sig, lambda s, f: handle_signal(s))

    tasks: list[asyncio.Task] = []
    ingestion_worker = None
    doc_worker = None

    try:
        if mode in ("all", "ingestion"):
            ingestion_worker = get_default_worker()
            tasks.append(asyncio.create_task(ingestion_worker.start(), name="ingestion_worker"))
            logger.info("IngestionWorker background task launched.")

        if mode in ("all", "document"):
            doc_worker = DocumentWorker(session_factory=async_session_factory)
            tasks.append(
                asyncio.create_task(
                    doc_worker.run_worker_loop(
                        stop_event=stop_event,
                        poll_interval=settings.DOCUMENT_PROCESSING_POLL_INTERVAL_SECONDS,
                    ),
                    name="document_worker",
                )
            )
            logger.info("DocumentWorker background task launched.")

        # Wait until stop event is signaled
        await stop_event.wait()
        logger.info("Graceful shutdown signaled. Stopping active workers...")

    finally:
        # Graceful teardown
        if ingestion_worker:
            ingestion_worker.stop()

        # Allow tasks up to 10 seconds to finish in-flight work cleanly
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=10.0)
            for p in pending:
                logger.warning("Cancelling uncompleted worker task %s after timeout", p.get_name())
                p.cancel()

        logger.info("Disposing worker database engine...")
        await async_engine.dispose()
        logger.info("Standalone worker runner terminated cleanly.")


def main() -> None:
    """CLI entrypoint for standalone worker runner."""
    parser = argparse.ArgumentParser(description="SupportGPT Background Worker Daemon")
    parser.add_argument(
        "--mode",
        choices=["all", "ingestion", "document"],
        default="all",
        help="Worker mode to run (default: all)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run_workers(mode=args.mode))
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)


if __name__ == "__main__":
    main()
