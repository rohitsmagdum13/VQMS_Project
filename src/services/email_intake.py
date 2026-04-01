"""Module: services/email_intake.py

Email Ingestion Service for VQMS.

This is the entry point of the entire pipeline. It fetches emails
from Exchange Online via Microsoft Graph API, parses them, stores
raw copies in S3, writes metadata to PostgreSQL, sets Redis
idempotency keys, and publishes events to EventBridge and SQS.

The full ingestion flow for a single email:
  1. Check Redis idempotency key — skip if already processed
  2. Fetch email from Graph API
  3. Store raw email in S3 (vqms-email-raw-prod)
  4. Parse email headers and body
  5. Fetch and store attachments in S3 (vqms-email-attachments-prod)
  6. Write metadata to PostgreSQL (intake.email_messages, intake.email_attachments)
  7. Set Redis idempotency key (7-day TTL)
  8. Publish EmailReceived event to EventBridge
  9. Publish EmailParsed event to EventBridge
  10. Send ParsedEmailPayload to vqms-analysis SQS queue

Corresponds to Steps 2-3 in the VQMS architecture document.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta, timezone

from src.adapters.graph_api import GraphAPIAdapter, GraphAPIError
from src.cache.redis_client import RedisClient
from src.db.connection import DatabasePool
from src.events.eventbridge import EventBridgePublisher
from src.models.email import EmailAttachment, ParsedEmailPayload
from src.queues.sqs import SQSClient
from src.storage.s3_client import S3Client
from src.utils.correlation import generate_correlation_id
from src.utils.helpers import html_to_plain_text

logger = logging.getLogger(__name__)


class EmailIntakeError(Exception):
    """Raised when email ingestion fails at any step.

    Includes the correlation_id so the error can be traced
    through the audit log and monitoring dashboards.
    """


async def process_single_email(
    message_id: str,
    *,
    graph_api: GraphAPIAdapter,
    redis_client: RedisClient,
    db_pool: DatabasePool,
    s3_client: S3Client,
    event_publisher: EventBridgePublisher,
    sqs_client: SQSClient,
    correlation_id: str | None = None,
) -> ParsedEmailPayload | None:
    """Process a single email through the full ingestion pipeline.

    This is the main function that orchestrates the 10-step flow.
    It is called once for each new email detected (either by
    polling or webhook notification).

    Args:
        message_id: Exchange Online message ID to process.
        graph_api: Adapter for Microsoft Graph API calls.
        redis_client: Redis client for idempotency checks.
        db_pool: Database pool for PostgreSQL writes.
        s3_client: S3 client for raw email and attachment storage.
        event_publisher: EventBridge publisher for pipeline events.
        sqs_client: SQS client for sending to analysis queue.
        correlation_id: Tracing ID. Generated if not provided.

    Returns:
        ParsedEmailPayload if the email was processed successfully.
        None if the email was a duplicate (already processed).

    Raises:
        EmailIntakeError: If any step in the pipeline fails.
    """
    if not correlation_id:
        correlation_id = generate_correlation_id()

    logger.info(
        "Starting email ingestion",
        extra={"message_id": message_id, "correlation_id": correlation_id},
    )

    # --------------------------------------------------
    # Step 1: Check Redis idempotency — skip duplicates
    # Exchange Online can redeliver emails up to 5 days
    # after original send, so we check before doing any work
    # --------------------------------------------------
    existing = await redis_client.get_idempotency(message_id)
    if existing is not None:
        logger.info(
            "Duplicate email detected — skipping",
            extra={"message_id": message_id, "correlation_id": correlation_id},
        )
        return None

    try:
        # --------------------------------------------------
        # Step 2: Fetch email from Graph API
        # --------------------------------------------------
        raw_email = await graph_api.fetch_message(
            message_id, correlation_id=correlation_id
        )

        # Extract fields from Graph API response
        sender_info = raw_email.get("sender", {}).get("emailAddress", {})
        sender_email = sender_info.get("address", "unknown@unknown.com")
        sender_name = sender_info.get("name")
        subject = raw_email.get("subject", "(no subject)")
        body_content = raw_email.get("body", {})
        body_html = body_content.get("content") if body_content.get("contentType") == "html" else None
        body_plain = body_content.get("content", "") if body_content.get("contentType") == "text" else ""
        received_at_str = raw_email.get("receivedDateTime", "")
        has_attachments = raw_email.get("hasAttachments", False)

        # Extract recipient addresses from Graph API response
        to_recipients = raw_email.get("toRecipients", [])
        to_address = (
            to_recipients[0].get("emailAddress", {}).get("address", "")
            if to_recipients
            else ""
        )

        # CC recipients — join multiple addresses with semicolons
        cc_recipients = raw_email.get("ccRecipients", [])
        cc_addresses: str | None = None
        if cc_recipients:
            cc_addresses = ";".join(
                r.get("emailAddress", {}).get("address", "")
                for r in cc_recipients
                if r.get("emailAddress", {}).get("address")
            ) or None

        # Thread ID — Graph API's conversationId groups related emails
        thread_id = raw_email.get("conversationId")

        # Reply detection — check if subject starts with common reply prefixes
        is_reply = subject.lower().startswith(("re:", "re :", "aw:", "sv:"))

        # Auto-reply detection — check for auto-submitted header or
        # specific Graph API flags that indicate automated responses
        is_auto_reply = False
        internet_headers = raw_email.get("internetMessageHeaders", [])
        for header in internet_headers:
            header_name = header.get("name", "").lower()
            header_value = header.get("value", "").lower()
            if header_name == "auto-submitted" and header_value != "no":
                is_auto_reply = True
                break
            if header_name == "x-auto-response-suppress":
                is_auto_reply = True
                break

        # Parse the received timestamp — Graph API returns ISO 8601 in UTC
        # (e.g., "2026-03-30T12:32:57Z"). We convert to IST (UTC+5:30)
        # and store as naive datetime since all our timestamps are IST.
        ist = timezone(timedelta(hours=5, minutes=30))
        if received_at_str:
            received_at_utc = datetime.fromisoformat(
                received_at_str.replace("Z", "+00:00")
            )
            received_at = received_at_utc.astimezone(ist).replace(tzinfo=None)
        else:
            received_at = datetime.now(ist).replace(tzinfo=None)

        # If body is HTML, extract clean plain text for PostgreSQL
        # and downstream agents. The raw HTML is preserved in body_html
        # for reference, but body_plain is what agents actually read.
        if body_html and not body_plain:
            body_plain = html_to_plain_text(body_html)

        # --------------------------------------------------
        # Step 3: Store raw email in S3
        # Raw storage happens BEFORE parsing so we never lose data
        # --------------------------------------------------
        import orjson

        raw_bytes = orjson.dumps(raw_email)
        s3_raw_path = s3_client.upload_raw_email(
            message_id, raw_bytes, correlation_id=correlation_id
        )

        # --------------------------------------------------
        # Step 4: Publish EmailReceived event
        # Signal that a new email was detected — monitoring picks this up
        # --------------------------------------------------
        event_publisher.publish_email_received(
            message_id=message_id,
            sender_email=sender_email,
            subject=subject,
            received_at=received_at,
            correlation_id=correlation_id,
        )

        # --------------------------------------------------
        # Step 5: Fetch and store attachments
        # Only if hasAttachments is True — avoids unnecessary API calls
        # --------------------------------------------------
        attachments: list[EmailAttachment] = []

        if has_attachments:
            raw_attachments = await graph_api.fetch_attachments(
                message_id, correlation_id=correlation_id
            )

            for att in raw_attachments:
                filename = att.get("name", "unnamed")
                content_type = att.get("contentType", "application/octet-stream")
                content_bytes_b64 = att.get("contentBytes", "")
                size = att.get("size", 0)

                # Graph API returns attachment content as base64
                content_bytes = base64.b64decode(content_bytes_b64) if content_bytes_b64 else b""

                # Upload to S3
                att_s3_path = s3_client.upload_attachment(
                    message_id,
                    filename,
                    content_bytes,
                    content_type,
                    correlation_id=correlation_id,
                )

                attachments.append(
                    EmailAttachment(
                        filename=filename,
                        mime_type=content_type,
                        file_size_bytes=size,
                        s3_path=att_s3_path,
                    )
                )

        # --------------------------------------------------
        # Step 6: Write to PostgreSQL
        # Insert into intake.email_messages and intake.email_attachments
        # --------------------------------------------------
        email_db_id = await _write_email_to_database(
            db_pool=db_pool,
            message_id=message_id,
            correlation_id=correlation_id,
            sender_email=sender_email,
            sender_name=sender_name,
            to_address=to_address,
            cc_addresses=cc_addresses,
            subject=subject,
            body_plain=body_plain,
            received_at=received_at,
            s3_raw_path=s3_raw_path,
            has_attachments=has_attachments,
            attachment_count=len(attachments),
            thread_id=thread_id,
            is_reply=is_reply,
            is_auto_reply=is_auto_reply,
            attachments=attachments,
        )

        # --------------------------------------------------
        # Step 7: Set Redis idempotency key
        # 7-day TTL because Exchange can redeliver emails up to 5 days
        # We set this AFTER successful storage so that failed attempts
        # are retried rather than silently dropped
        # --------------------------------------------------
        await redis_client.set_idempotency(
            message_id,
            {
                "correlation_id": correlation_id,
                "processed_at": datetime.now().isoformat(),
                "email_db_id": email_db_id,
            },
        )

        # --------------------------------------------------
        # Step 8: Build the parsed payload
        # --------------------------------------------------
        parsed_payload = ParsedEmailPayload(
            message_id=message_id,
            correlation_id=correlation_id,
            sender_email=sender_email,
            sender_name=sender_name,
            to_address=to_address,
            cc_addresses=cc_addresses,
            subject=subject,
            body_plain=body_plain,
            body_html=body_html,
            received_at=received_at,
            thread_id=thread_id,
            is_reply=is_reply,
            is_auto_reply=is_auto_reply,
            language="en",
            status="INGESTED",
            has_attachments=has_attachments,
            attachment_count=len(attachments),
            s3_raw_path=s3_raw_path,
            attachments=attachments,
            is_duplicate=False,
        )

        # --------------------------------------------------
        # Step 9: Publish EmailParsed event
        # Signals that this email is ready for analysis
        # --------------------------------------------------
        event_publisher.publish_email_parsed(
            message_id=message_id,
            correlation_id=correlation_id,
            s3_raw_path=s3_raw_path,
            has_attachments=has_attachments,
            attachment_count=len(attachments),
        )

        # --------------------------------------------------
        # Step 10: Send to vqms-analysis SQS queue
        # The Email Analysis Agent will consume this message
        # --------------------------------------------------
        sqs_client.send_message(
            "vqms-analysis",
            parsed_payload.model_dump(mode="json"),
            correlation_id=correlation_id,
        )

        # Mark the email as read in Exchange Online so the
        # polling mechanism doesn't pick it up again
        try:
            await graph_api.mark_as_read(
                message_id, correlation_id=correlation_id
            )
        except GraphAPIError:
            # Non-critical — the idempotency key prevents reprocessing
            # even if the email stays unread
            logger.warning(
                "Failed to mark email as read — idempotency key will prevent reprocessing",
                extra={"message_id": message_id, "correlation_id": correlation_id},
            )

        logger.info(
            "Email ingestion completed successfully",
            extra={
                "message_id": message_id,
                "correlation_id": correlation_id,
                "attachment_count": len(attachments),
            },
        )

        return parsed_payload

    except GraphAPIError as exc:
        raise EmailIntakeError(
            f"Graph API error during ingestion [{correlation_id}]: {exc}"
        ) from exc
    except Exception as exc:
        raise EmailIntakeError(
            f"Unexpected error during ingestion [{correlation_id}]: {exc}"
        ) from exc


async def poll_for_new_emails(
    *,
    graph_api: GraphAPIAdapter,
    redis_client: RedisClient,
    db_pool: DatabasePool,
    s3_client: S3Client,
    event_publisher: EventBridgePublisher,
    sqs_client: SQSClient,
) -> list[ParsedEmailPayload]:
    """Poll Exchange Online for unread emails and process each one.

    This is the polling-based email detection mechanism. It lists
    all unread messages in the shared mailbox and processes each
    one through the ingestion pipeline.

    In development mode, this is called manually or on a timer.
    In production, this runs as a backup alongside webhook-based
    detection to catch any missed notifications.

    Args:
        graph_api: Adapter for Microsoft Graph API.
        redis_client: Redis client for idempotency.
        db_pool: Database pool for PostgreSQL.
        s3_client: S3 client for storage.
        event_publisher: EventBridge publisher.
        sqs_client: SQS client.

    Returns:
        List of ParsedEmailPayload objects for successfully processed emails.
        Duplicates are filtered out (not included in the list).
    """
    logger.info("Starting email polling cycle")

    processed: list[ParsedEmailPayload] = []

    try:
        unread_messages = await graph_api.list_unread_messages()
        logger.info(
            "Found unread messages",
            extra={"count": len(unread_messages)},
        )

        for msg in unread_messages:
            msg_id = msg.get("id", "")
            if not msg_id:
                continue

            try:
                result = await process_single_email(
                    msg_id,
                    graph_api=graph_api,
                    redis_client=redis_client,
                    db_pool=db_pool,
                    s3_client=s3_client,
                    event_publisher=event_publisher,
                    sqs_client=sqs_client,
                )
                if result is not None:
                    processed.append(result)
            except EmailIntakeError:
                # Log the error but continue processing other emails
                # The failed email will be retried on the next poll cycle
                logger.exception(
                    "Failed to process email — will retry on next cycle",
                    extra={"message_id": msg_id},
                )

    except GraphAPIError:
        logger.exception("Failed to list unread messages from Graph API")

    logger.info(
        "Email polling cycle complete",
        extra={"processed_count": len(processed)},
    )
    return processed


# ============================================================
# Private helper: database write
# ============================================================


async def _write_email_to_database(
    *,
    db_pool: DatabasePool,
    message_id: str,
    correlation_id: str,
    sender_email: str,
    sender_name: str | None,
    to_address: str,
    cc_addresses: str | None,
    subject: str,
    body_plain: str,
    received_at: datetime,
    s3_raw_path: str,
    has_attachments: bool,
    attachment_count: int,
    thread_id: str | None,
    is_reply: bool,
    is_auto_reply: bool,
    attachments: list[EmailAttachment],
) -> int:
    """Write email metadata to PostgreSQL.

    Inserts into intake.email_messages and intake.email_attachments.
    Returns the database ID of the inserted email_messages row.
    body_html is NOT stored in DB — the raw HTML is in S3.
    All timestamps are computed in IST (UTC+5:30) in Python — we do
    NOT rely on PostgreSQL DEFAULT to avoid timezone display issues.

    This is a private helper — not part of the public API.
    """
    # Compute IST timestamp in Python so we have full control
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist).replace(tzinfo=None)

    # Insert the email message and get back the auto-generated ID
    row = await db_pool.fetchrow(
        """
        INSERT INTO intake.email_messages
            (message_id, correlation_id, sender_email, sender_name,
             to_address, cc_addresses, subject, body_plain,
             received_at, s3_raw_path, has_attachments, attachment_count,
             thread_id, is_reply, is_auto_reply,
             parsed_at, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $16, $16)
        RETURNING id
        """,
        message_id,
        correlation_id,
        sender_email,
        sender_name,
        to_address,
        cc_addresses,
        subject,
        body_plain,
        received_at,
        s3_raw_path,
        has_attachments,
        attachment_count,
        thread_id,
        is_reply,
        is_auto_reply,
        now_ist,
        correlation_id=correlation_id,
    )

    email_db_id = row["id"] if row else 0

    # Insert attachments
    for att in attachments:
        await db_pool.execute(
            """
            INSERT INTO intake.email_attachments
                (message_id, filename, file_size_bytes, mime_type, s3_path)
            VALUES ($1, $2, $3, $4, $5)
            """,
            email_db_id,
            att.filename,
            att.file_size_bytes,
            att.mime_type,
            att.s3_path,
            correlation_id=correlation_id,
        )

    logger.info(
        "Email written to database",
        extra={
            "email_db_id": email_db_id,
            "attachment_count": len(attachments),
            "correlation_id": correlation_id,
        },
    )

    return email_db_id
