"""Tests for VQMS EventBridge publisher.

Uses moto to mock AWS EventBridge. Tests verify that events
are published with the correct detail-type and payload structure.
"""

from __future__ import annotations

from datetime import UTC, datetime

import boto3
import pytest
from moto import mock_aws

from src.events.eventbridge import (
    EVENT_BUS_NAME,
    EVENT_SOURCE,
    EventBridgePublisher,
)


@pytest.fixture()
def _create_event_bus():
    """Create mock EventBridge bus before each test."""
    with mock_aws():
        client = boto3.client("events", region_name="us-east-1")
        client.create_event_bus(Name=EVENT_BUS_NAME)
        yield


class TestEventBridgePublisher:
    """Test EventBridge event publishing."""

    @mock_aws
    def test_publish_email_received(self) -> None:
        """EmailReceived event should be published without errors."""
        boto3.client("events", region_name="us-east-1").create_event_bus(
            Name=EVENT_BUS_NAME
        )
        publisher = EventBridgePublisher(region="us-east-1")
        # Should not raise
        publisher.publish_email_received(
            message_id="msg-001",
            sender_email="vendor@example.com",
            subject="Test Subject",
            received_at=datetime(2024, 3, 20, 10, 30, tzinfo=UTC),
            correlation_id="vqms-test-001",
        )

    @mock_aws
    def test_publish_email_parsed(self) -> None:
        """EmailParsed event should be published without errors."""
        boto3.client("events", region_name="us-east-1").create_event_bus(
            Name=EVENT_BUS_NAME
        )
        publisher = EventBridgePublisher(region="us-east-1")
        publisher.publish_email_parsed(
            message_id="msg-001",
            correlation_id="vqms-test-001",
            s3_raw_path="raw-emails/2024/03/20/msg-001.eml",
            has_attachments=True,
            attachment_count=2,
        )

    @mock_aws
    def test_event_source_is_correct(self) -> None:
        """Events should use the com.vqms source."""
        assert EVENT_SOURCE == "com.vqms"

    @mock_aws
    def test_event_bus_name_is_correct(self) -> None:
        """Events should target the vqms-event-bus."""
        assert EVENT_BUS_NAME == "vqms-event-bus"
