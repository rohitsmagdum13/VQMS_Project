"""Module: events/eventbridge.py

EventBridge publisher for VQMS.

Publishes all 17 event types to the vqms-event-bus. Each event
follows a standard envelope with source, detail-type, and a
JSON detail payload.

Events drive the loosely-coupled pipeline — services publish
events after completing work, and downstream services consume
them via SQS queue subscriptions.

Usage:
    from src.events.eventbridge import EventBridgePublisher

    publisher = EventBridgePublisher()
    await publisher.publish_email_received(message_id, sender, subject, received_at, correlation_id)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import boto3
import orjson
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class EventBridgePublishError(Exception):
    """Raised when an EventBridge publish operation fails.

    Covers: bus not found, payload too large, throttling, IAM errors.
    """


# EventBridge configuration from environment
EVENT_BUS_NAME = os.getenv("EVENTBRIDGE_BUS_NAME", "vqms-event-bus")
EVENT_SOURCE = os.getenv("EVENTBRIDGE_SOURCE", "com.vqms")


class EventBridgePublisher:
    """Publishes events to the VQMS EventBridge bus.

    Each event type has a dedicated method with typed parameters
    to prevent malformed events. All methods are synchronous wrappers
    around boto3 — production may switch to async.

    All methods accept correlation_id for log tracing.
    """

    def __init__(self, region: str | None = None) -> None:
        """Initialize the EventBridge client.

        Args:
            region: AWS region. Defaults to AWS_REGION env var.
        """
        self._region = region or os.getenv("AWS_REGION", "us-east-1")
        self._client = boto3.client("events", region_name=self._region)

    def _publish(
        self,
        detail_type: str,
        detail: dict[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> None:
        """Publish a single event to EventBridge.

        This is the internal method that all public methods call.
        It handles serialization, error handling, and logging.

        Args:
            detail_type: The EventBridge detail-type (e.g., 'EmailReceived').
            detail: The event payload as a dict.
            correlation_id: Tracing ID for log context.

        Raises:
            EventBridgePublishError: If the publish fails.
        """
        # Always include correlation_id in the event payload
        # so downstream consumers can trace the event back to a case
        if correlation_id:
            detail["correlation_id"] = correlation_id

        try:
            self._client.put_events(
                Entries=[
                    {
                        "Source": EVENT_SOURCE,
                        "DetailType": detail_type,
                        "Detail": orjson.dumps(detail).decode("utf-8"),
                        "EventBusName": EVENT_BUS_NAME,
                    }
                ]
            )
            logger.info(
                "Event published to EventBridge",
                extra={
                    "detail_type": detail_type,
                    "correlation_id": correlation_id,
                },
            )
        except ClientError as exc:
            raise EventBridgePublishError(
                f"Failed to publish {detail_type} event: {exc}"
            ) from exc

    # --------------------------------------------------------
    # Phase 2 Events: Email Ingestion
    # --------------------------------------------------------

    def publish_email_received(
        self,
        *,
        message_id: str,
        sender_email: str,
        subject: str,
        received_at: datetime,
        correlation_id: str,
    ) -> None:
        """Publish EmailReceived event — triggered when a new email is detected.

        This is the very first event in the pipeline. It signals
        that a new email has been fetched from Exchange Online.
        """
        self._publish(
            "EmailReceived",
            {
                "message_id": message_id,
                "sender_email": sender_email,
                "subject": subject,
                "received_at": received_at.isoformat(),
            },
            correlation_id=correlation_id,
        )

    def publish_email_parsed(
        self,
        *,
        message_id: str,
        correlation_id: str,
        s3_raw_path: str,
        has_attachments: bool,
        attachment_count: int,
    ) -> None:
        """Publish EmailParsed event — triggered after email is parsed and stored.

        This signals that the email has been successfully:
        1. Stored in S3 (raw + attachments)
        2. Written to PostgreSQL (email_messages + email_attachments)
        3. Marked in Redis (idempotency key set)

        The vqms-analysis queue subscribes to this event to trigger
        the Email Analysis Agent.
        """
        self._publish(
            "EmailParsed",
            {
                "message_id": message_id,
                "s3_raw_path": s3_raw_path,
                "has_attachments": has_attachments,
                "attachment_count": attachment_count,
            },
            correlation_id=correlation_id,
        )

    # --------------------------------------------------------
    # Phase 6+ Events (stubs — implemented in later phases)
    # --------------------------------------------------------

    def publish_analysis_completed(
        self, *, correlation_id: str, **detail: Any
    ) -> None:
        """Publish AnalysisCompleted event. TODO: Phase 5."""
        self._publish("AnalysisCompleted", detail, correlation_id=correlation_id)

    def publish_vendor_resolved(
        self, *, correlation_id: str, **detail: Any
    ) -> None:
        """Publish VendorResolved event. TODO: Phase 6."""
        self._publish("VendorResolved", detail, correlation_id=correlation_id)

    def publish_ticket_created(
        self, *, correlation_id: str, **detail: Any
    ) -> None:
        """Publish TicketCreated event. TODO: Phase 6."""
        self._publish("TicketCreated", detail, correlation_id=correlation_id)

    def publish_ticket_updated(
        self, *, correlation_id: str, **detail: Any
    ) -> None:
        """Publish TicketUpdated event. TODO: Phase 6."""
        self._publish("TicketUpdated", detail, correlation_id=correlation_id)

    def publish_draft_prepared(
        self, *, correlation_id: str, **detail: Any
    ) -> None:
        """Publish DraftPrepared event. TODO: Phase 7."""
        self._publish("DraftPrepared", detail, correlation_id=correlation_id)

    def publish_validation_passed(
        self, *, correlation_id: str, **detail: Any
    ) -> None:
        """Publish ValidationPassed event. TODO: Phase 7."""
        self._publish("ValidationPassed", detail, correlation_id=correlation_id)

    def publish_validation_failed(
        self, *, correlation_id: str, **detail: Any
    ) -> None:
        """Publish ValidationFailed event. TODO: Phase 7."""
        self._publish("ValidationFailed", detail, correlation_id=correlation_id)

    def publish_email_sent(
        self, *, correlation_id: str, **detail: Any
    ) -> None:
        """Publish EmailSent event. TODO: Phase 7."""
        self._publish("EmailSent", detail, correlation_id=correlation_id)

    def publish_sla_warning(
        self, *, correlation_id: str, threshold_percent: int, **detail: Any
    ) -> None:
        """Publish SLA warning/escalation event. TODO: Phase 8."""
        event_type = f"SLAWarning{threshold_percent}"
        if threshold_percent >= 85:
            event_type = f"SLAEscalation{threshold_percent}"
        self._publish(event_type, detail, correlation_id=correlation_id)

    def publish_ticket_closed(
        self, *, correlation_id: str, **detail: Any
    ) -> None:
        """Publish TicketClosed event. TODO: Phase 9."""
        self._publish("TicketClosed", detail, correlation_id=correlation_id)

    def publish_ticket_reopened(
        self, *, correlation_id: str, **detail: Any
    ) -> None:
        """Publish TicketReopened event. TODO: Phase 9."""
        self._publish("TicketReopened", detail, correlation_id=correlation_id)
