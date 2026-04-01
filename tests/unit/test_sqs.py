"""Tests for VQMS SQS client.

Uses moto to mock AWS SQS. Tests verify message send/receive
round trips and queue name resolution.
"""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from src.queues.sqs import QUEUE_NAMES, SQSClient


@pytest.fixture()
def _create_sqs_queues():
    """Create mock SQS queues before each test."""
    with mock_aws():
        sqs = boto3.client("sqs", region_name="us-east-1")
        for name in QUEUE_NAMES:
            sqs.create_queue(QueueName=name)
        yield


class TestQueueNames:
    """Test queue name constants."""

    def test_all_10_queues_defined(self) -> None:
        """There should be exactly 10 queue names defined."""
        assert len(QUEUE_NAMES) == 10

    def test_all_queues_start_with_vqms(self) -> None:
        """All queue names should start with 'vqms-'."""
        for name in QUEUE_NAMES:
            assert name.startswith("vqms-"), f"Queue '{name}' missing vqms- prefix"

    def test_dlq_is_included(self) -> None:
        """The dead letter queue must be in the list."""
        assert "vqms-dlq" in QUEUE_NAMES

    def test_analysis_queue_exists(self) -> None:
        """The analysis queue (Phase 2 target) must exist."""
        assert "vqms-analysis" in QUEUE_NAMES


class TestSQSClient:
    """Test SQS message send and receive."""

    @mock_aws
    def test_send_and_receive_message(self) -> None:
        """A message sent to a queue should be receivable."""
        sqs = boto3.client("sqs", region_name="us-east-1")
        sqs.create_queue(QueueName="vqms-analysis")

        client = SQSClient(region="us-east-1")
        payload = {"message_id": "msg-001", "subject": "Test"}
        client.send_message(
            "vqms-analysis",
            payload,
            correlation_id="vqms-test-001",
        )

        messages = client.receive_messages(
            "vqms-analysis",
            max_messages=1,
            wait_time_seconds=0,
        )
        assert len(messages) == 1
        assert messages[0]["body"]["message_id"] == "msg-001"
        assert messages[0]["correlation_id"] == "vqms-test-001"

    @mock_aws
    def test_send_message_returns_message_id(self) -> None:
        """send_message should return a non-empty SQS message ID."""
        sqs = boto3.client("sqs", region_name="us-east-1")
        sqs.create_queue(QueueName="vqms-email-intake")

        client = SQSClient(region="us-east-1")
        sqs_msg_id = client.send_message(
            "vqms-email-intake",
            {"test": True},
        )
        assert sqs_msg_id  # Non-empty string

    @mock_aws
    def test_delete_message_removes_from_queue(self) -> None:
        """After deleting a message, it should not be receivable."""
        sqs = boto3.client("sqs", region_name="us-east-1")
        sqs.create_queue(QueueName="vqms-audit")

        client = SQSClient(region="us-east-1")
        client.send_message("vqms-audit", {"action": "test"})

        messages = client.receive_messages(
            "vqms-audit", max_messages=1, wait_time_seconds=0
        )
        assert len(messages) == 1

        client.delete_message(
            "vqms-audit",
            messages[0]["receipt_handle"],
        )

        # After deletion, no messages should be available
        messages_after = client.receive_messages(
            "vqms-audit", max_messages=1, wait_time_seconds=0
        )
        assert len(messages_after) == 0

    @mock_aws
    def test_receive_empty_queue_returns_empty_list(self) -> None:
        """Receiving from an empty queue should return empty list."""
        sqs = boto3.client("sqs", region_name="us-east-1")
        sqs.create_queue(QueueName="vqms-routing")

        client = SQSClient(region="us-east-1")
        messages = client.receive_messages(
            "vqms-routing", max_messages=1, wait_time_seconds=0
        )
        assert messages == []
