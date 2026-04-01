"""Run the full VQMS email intake pipeline.

Polls Exchange Online for unread emails and processes each one
through the 10-step ingestion pipeline defined in email_intake.py.

Uses existing VQMS utilities for logging, correlation IDs, and
service initialization — does not duplicate any configuration.

Run with: uv run python scripts/run_email_intake.py
"""

from __future__ import annotations

import asyncio
import os
import sys

# Add project root to path so src/ imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

# Use the existing VQMS structured logging — do NOT reconfigure
from src.utils.logger import setup_logging, get_logger

setup_logging(log_level=os.getenv("LOG_LEVEL", "DEBUG"))
logger = get_logger(__name__)


async def run_pipeline() -> None:
    """Initialize all services and run one polling cycle."""

    # --- Import all VQMS services ---
    from src.adapters.graph_api import GraphAPIAdapter
    from src.cache.redis_client import RedisClient
    from src.db.connection import DatabasePool
    from src.events.eventbridge import EventBridgePublisher
    from src.queues.sqs import SQSClient
    from src.services.email_intake import poll_for_new_emails, EmailIntakeError
    from src.storage.s3_client import S3Client

    logger.info("pipeline_starting", phase="initialization")

    # --- Initialize services using existing constructors ---
    graph_api = GraphAPIAdapter()

    redis_client = RedisClient(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD"),
        db=int(os.getenv("REDIS_DB", "0")),
        ssl=os.getenv("REDIS_SSL", "false").lower() == "true",
    )
    await redis_client.connect()

    # DatabasePool.connect() reads POSTGRES_* env vars and
    # POSTGRES_SSLMODE for Neon SSL — no manual override needed
    db_pool = DatabasePool()
    await db_pool.connect()

    s3_client = S3Client()
    event_publisher = EventBridgePublisher()
    sqs_client = SQSClient()

    logger.info("pipeline_starting", phase="all_services_ready")

    # --- Run one polling cycle ---
    try:
        results = await poll_for_new_emails(
            graph_api=graph_api,
            redis_client=redis_client,
            db_pool=db_pool,
            s3_client=s3_client,
            event_publisher=event_publisher,
            sqs_client=sqs_client,
        )

        if results:
            logger.info(
                "pipeline_complete",
                emails_processed=len(results),
            )
            for payload in results:
                logger.info(
                    "email_processed",
                    correlation_id=payload.correlation_id,
                    sender_email=payload.sender_email,
                    subject=payload.subject,
                    attachment_count=len(payload.attachments),
                    s3_raw_path=payload.s3_raw_path,
                )
        else:
            logger.info(
                "pipeline_complete",
                emails_processed=0,
                mailbox=os.getenv("GRAPH_API_MAILBOX"),
            )

    except EmailIntakeError as exc:
        logger.error("pipeline_failed", error=str(exc))
    finally:
        # --- Cleanup all connections ---
        await graph_api.close()
        await redis_client.close()
        await db_pool.close()
        logger.info("pipeline_shutdown", phase="connections_closed")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
