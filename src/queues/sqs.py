"""Module: queues/sqs.py

SQS producer and consumer for VQMS.

Handles sending messages to and receiving messages from all 10 SQS
queues defined in the architecture. Each queue decouples a stage
in the pipeline so services can process at their own pace.

All queues use vqms-dlq as their dead letter queue (maxReceiveCount=3).

Queue list:
  vqms-email-intake      — new emails for ingestion
  vqms-analysis          — parsed emails for analysis agent
  vqms-vendor-resolution — analysis results for vendor lookup
  vqms-ticket-ops        — vendor matches for ticket creation
  vqms-routing           — tickets for orchestration routing
  vqms-communication     — routing decisions for draft generation
  vqms-escalation        — SLA alerts for escalation handling
  vqms-human-review      — cases needing manual review
  vqms-audit             — all actions for audit logging
  vqms-dlq               — failed messages from all queues

Usage:
    from src.queues.sqs import SQSClient

    sqs = SQSClient()
    await sqs.send_message("vqms-analysis", payload, correlation_id="...")
    messages = await sqs.receive_messages("vqms-analysis", max_messages=10)
"""

from __future__ import annotations

import logging
import os
from typing import Any

import boto3
import orjson
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class SQSError(Exception):
    """Raised when an SQS operation fails.

    Covers: queue not found, message too large, throttling, IAM errors.
    """


# Queue name prefix from environment
SQS_QUEUE_PREFIX = os.getenv("SQS_QUEUE_PREFIX", "vqms-")

# All queue names — used for validation and URL resolution
QUEUE_NAMES = [
    "vqms-email-intake",
    "vqms-analysis",
    "vqms-vendor-resolution",
    "vqms-ticket-ops",
    "vqms-routing",
    "vqms-communication",
    "vqms-escalation",
    "vqms-human-review",
    "vqms-audit",
    "vqms-dlq",
]


class SQSClient:
    """SQS client for sending and receiving messages across VQMS queues.

    Wraps boto3 SQS client with JSON serialization and queue URL
    resolution. Uses synchronous boto3 for development simplicity.

    Queue URLs are resolved lazily on first use and cached to avoid
    repeated GetQueueUrl API calls.
    """

    def __init__(self, region: str | None = None) -> None:
        """Initialize the SQS client.

        Args:
            region: AWS region. Defaults to AWS_REGION env var.
        """
        self._region = region or os.getenv("AWS_REGION", "us-east-1")
        self._client = boto3.client("sqs", region_name=self._region)
        # Cache queue URLs to avoid repeated lookups
        self._queue_urls: dict[str, str] = {}

    def _get_queue_url(self, queue_name: str) -> str:
        """Resolve a queue name to its URL, caching the result.

        Args:
            queue_name: The queue name (e.g., 'vqms-analysis').

        Returns:
            The queue URL.

        Raises:
            SQSError: If the queue does not exist.
        """
        if queue_name in self._queue_urls:
            return self._queue_urls[queue_name]

        try:
            response = self._client.get_queue_url(QueueName=queue_name)
            url = response["QueueUrl"]
            self._queue_urls[queue_name] = url
            return url
        except ClientError as exc:
            raise SQSError(
                f"Failed to resolve queue URL for '{queue_name}': {exc}"
            ) from exc

    def send_message(
        self,
        queue_name: str,
        payload: dict[str, Any],
        *,
        correlation_id: str | None = None,
        delay_seconds: int = 0,
    ) -> str:
        """Send a JSON message to an SQS queue.

        Args:
            queue_name: Target queue (e.g., 'vqms-analysis').
            payload: Message body as a dict (serialized to JSON).
            correlation_id: Tracing ID — added to message attributes.
            delay_seconds: Optional delivery delay (0-900 seconds).

        Returns:
            The SQS message ID.

        Raises:
            SQSError: If the send fails.
        """
        queue_url = self._get_queue_url(queue_name)

        # Build message attributes — correlation_id is always included
        # so consumers can trace messages without parsing the body
        message_attributes: dict[str, Any] = {}
        if correlation_id:
            message_attributes["correlation_id"] = {
                "StringValue": correlation_id,
                "DataType": "String",
            }

        try:
            response = self._client.send_message(
                QueueUrl=queue_url,
                MessageBody=orjson.dumps(payload).decode("utf-8"),
                MessageAttributes=message_attributes,
                DelaySeconds=delay_seconds,
            )
            sqs_message_id = response["MessageId"]
            logger.info(
                "Message sent to SQS",
                extra={
                    "queue": queue_name,
                    "sqs_message_id": sqs_message_id,
                    "correlation_id": correlation_id,
                },
            )
            return sqs_message_id
        except ClientError as exc:
            raise SQSError(
                f"Failed to send message to '{queue_name}': {exc}"
            ) from exc

    def receive_messages(
        self,
        queue_name: str,
        *,
        max_messages: int = 1,
        wait_time_seconds: int = 20,
        visibility_timeout: int = 300,
    ) -> list[dict[str, Any]]:
        """Receive messages from an SQS queue using long polling.

        Args:
            queue_name: Source queue (e.g., 'vqms-email-intake').
            max_messages: Maximum messages to receive (1-10).
            wait_time_seconds: Long polling duration (0-20 seconds).
                20 seconds reduces empty responses and API costs.
            visibility_timeout: How long the message is hidden from
                other consumers (seconds). Must be long enough for
                the consumer to process the message.

        Returns:
            List of dicts, each with 'body' (parsed JSON), 'receipt_handle',
            'message_id', and 'correlation_id' (if present).

        Raises:
            SQSError: If the receive fails.
        """
        queue_url = self._get_queue_url(queue_name)

        try:
            response = self._client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time_seconds,
                VisibilityTimeout=visibility_timeout,
                MessageAttributeNames=["correlation_id"],
            )

            messages = []
            for msg in response.get("Messages", []):
                # Extract correlation_id from message attributes
                attrs = msg.get("MessageAttributes", {})
                corr_id = None
                if "correlation_id" in attrs:
                    corr_id = attrs["correlation_id"].get("StringValue")

                messages.append({
                    "body": orjson.loads(msg["Body"]),
                    "receipt_handle": msg["ReceiptHandle"],
                    "message_id": msg["MessageId"],
                    "correlation_id": corr_id,
                })

            return messages
        except ClientError as exc:
            raise SQSError(
                f"Failed to receive messages from '{queue_name}': {exc}"
            ) from exc

    def delete_message(
        self,
        queue_name: str,
        receipt_handle: str,
        *,
        correlation_id: str | None = None,
    ) -> None:
        """Delete a message from a queue after successful processing.

        Must be called after processing to prevent the message from
        becoming visible again after the visibility timeout expires.

        Args:
            queue_name: Queue the message was received from.
            receipt_handle: The receipt handle from receive_messages.
            correlation_id: Tracing ID for log context.

        Raises:
            SQSError: If the delete fails.
        """
        queue_url = self._get_queue_url(queue_name)

        try:
            self._client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle,
            )
            logger.debug(
                "Message deleted from SQS",
                extra={
                    "queue": queue_name,
                    "correlation_id": correlation_id,
                },
            )
        except ClientError as exc:
            raise SQSError(
                f"Failed to delete message from '{queue_name}': {exc}"
            ) from exc
