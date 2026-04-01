"""Tests for VQMS Email Intake Service.

Tests the core email ingestion pipeline using mocked dependencies.
Each test verifies a specific behavior of the process_single_email
function without making real API calls or database writes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.email import ParsedEmailPayload
from src.services.email_intake import (
    process_single_email,
)

# ============================================================
# Fixtures: Mock dependencies for the intake pipeline
# ============================================================


@pytest.fixture()
def mock_graph_api() -> AsyncMock:
    """Mock Graph API adapter with a sample email response."""
    mock = AsyncMock()
    mock.fetch_message.return_value = {
        "id": "msg-test-001",
        "subject": "Invoice #INV-2024-001 Payment Status",
        "sender": {
            "emailAddress": {
                "address": "john.doe@acme-corp.com",
                "name": "John Doe",
            }
        },
        "body": {
            "contentType": "text",
            "content": "Hello, I would like to check the status of invoice INV-2024-001.",
        },
        "receivedDateTime": "2024-03-20T10:30:00Z",
        "hasAttachments": False,
        "conversationId": "conv-abc-123",
        "internetMessageId": "<msg-test-001@exchange.online>",
    }
    mock.fetch_attachments.return_value = []
    mock.mark_as_read.return_value = None
    return mock


@pytest.fixture()
def mock_redis_client() -> AsyncMock:
    """Mock Redis client — returns None for idempotency (not a duplicate)."""
    mock = AsyncMock()
    mock.get_idempotency.return_value = None  # Not seen before
    mock.set_idempotency.return_value = None
    return mock


@pytest.fixture()
def mock_db_pool() -> AsyncMock:
    """Mock database pool — returns a fake row ID on insert."""
    mock = AsyncMock()
    mock.fetchrow.return_value = {"id": 42}
    mock.execute.return_value = "INSERT 0 1"
    return mock


@pytest.fixture()
def mock_s3_client() -> MagicMock:
    """Mock S3 client — returns fake S3 keys."""
    mock = MagicMock()
    mock.upload_raw_email.return_value = "raw-emails/2024/03/20/msg-test-001.eml"
    mock.upload_attachment.return_value = "attachments/2024/03/20/msg-test-001/file.pdf"
    return mock


@pytest.fixture()
def mock_event_publisher() -> MagicMock:
    """Mock EventBridge publisher."""
    return MagicMock()


@pytest.fixture()
def mock_sqs_client() -> MagicMock:
    """Mock SQS client."""
    mock = MagicMock()
    mock.send_message.return_value = "sqs-msg-id-001"
    return mock


# ============================================================
# Tests: process_single_email
# ============================================================


class TestProcessSingleEmail:
    """Test the main email ingestion pipeline."""

    @pytest.mark.asyncio()
    async def test_successful_ingestion_returns_parsed_payload(
        self,
        mock_graph_api: AsyncMock,
        mock_redis_client: AsyncMock,
        mock_db_pool: AsyncMock,
        mock_s3_client: MagicMock,
        mock_event_publisher: MagicMock,
        mock_sqs_client: MagicMock,
    ) -> None:
        """A new email should be processed and return a ParsedEmailPayload."""
        result = await process_single_email(
            "msg-test-001",
            graph_api=mock_graph_api,
            redis_client=mock_redis_client,
            db_pool=mock_db_pool,
            s3_client=mock_s3_client,
            event_publisher=mock_event_publisher,
            sqs_client=mock_sqs_client,
            correlation_id="vqms-test-corr",
        )

        assert result is not None
        assert isinstance(result, ParsedEmailPayload)
        assert result.message_id == "msg-test-001"
        assert result.sender_email == "john.doe@acme-corp.com"
        assert result.is_duplicate is False

    @pytest.mark.asyncio()
    async def test_duplicate_email_returns_none(
        self,
        mock_graph_api: AsyncMock,
        mock_redis_client: AsyncMock,
        mock_db_pool: AsyncMock,
        mock_s3_client: MagicMock,
        mock_event_publisher: MagicMock,
        mock_sqs_client: MagicMock,
    ) -> None:
        """A duplicate email (already in Redis) should return None."""
        # Simulate the email already being processed
        mock_redis_client.get_idempotency.return_value = {
            "correlation_id": "old-corr",
            "processed_at": "2024-03-20T10:00:00",
        }

        result = await process_single_email(
            "msg-test-001",
            graph_api=mock_graph_api,
            redis_client=mock_redis_client,
            db_pool=mock_db_pool,
            s3_client=mock_s3_client,
            event_publisher=mock_event_publisher,
            sqs_client=mock_sqs_client,
        )

        assert result is None
        # Graph API should NOT have been called for duplicates
        mock_graph_api.fetch_message.assert_not_called()

    @pytest.mark.asyncio()
    async def test_s3_upload_called_before_database_write(
        self,
        mock_graph_api: AsyncMock,
        mock_redis_client: AsyncMock,
        mock_db_pool: AsyncMock,
        mock_s3_client: MagicMock,
        mock_event_publisher: MagicMock,
        mock_sqs_client: MagicMock,
    ) -> None:
        """Raw email should be stored in S3 before writing to database."""
        await process_single_email(
            "msg-test-001",
            graph_api=mock_graph_api,
            redis_client=mock_redis_client,
            db_pool=mock_db_pool,
            s3_client=mock_s3_client,
            event_publisher=mock_event_publisher,
            sqs_client=mock_sqs_client,
        )

        # Both should have been called
        mock_s3_client.upload_raw_email.assert_called_once()
        mock_db_pool.fetchrow.assert_called_once()

    @pytest.mark.asyncio()
    async def test_redis_idempotency_set_after_successful_storage(
        self,
        mock_graph_api: AsyncMock,
        mock_redis_client: AsyncMock,
        mock_db_pool: AsyncMock,
        mock_s3_client: MagicMock,
        mock_event_publisher: MagicMock,
        mock_sqs_client: MagicMock,
    ) -> None:
        """Idempotency key should be set AFTER database and S3 writes succeed."""
        await process_single_email(
            "msg-test-001",
            graph_api=mock_graph_api,
            redis_client=mock_redis_client,
            db_pool=mock_db_pool,
            s3_client=mock_s3_client,
            event_publisher=mock_event_publisher,
            sqs_client=mock_sqs_client,
        )

        mock_redis_client.set_idempotency.assert_called_once()
        # Check the idempotency value contains correlation_id
        call_args = mock_redis_client.set_idempotency.call_args
        assert "correlation_id" in call_args[0][1]

    @pytest.mark.asyncio()
    async def test_events_published_for_new_email(
        self,
        mock_graph_api: AsyncMock,
        mock_redis_client: AsyncMock,
        mock_db_pool: AsyncMock,
        mock_s3_client: MagicMock,
        mock_event_publisher: MagicMock,
        mock_sqs_client: MagicMock,
    ) -> None:
        """Both EmailReceived and EmailParsed events should be published."""
        await process_single_email(
            "msg-test-001",
            graph_api=mock_graph_api,
            redis_client=mock_redis_client,
            db_pool=mock_db_pool,
            s3_client=mock_s3_client,
            event_publisher=mock_event_publisher,
            sqs_client=mock_sqs_client,
        )

        mock_event_publisher.publish_email_received.assert_called_once()
        mock_event_publisher.publish_email_parsed.assert_called_once()

    @pytest.mark.asyncio()
    async def test_message_sent_to_analysis_queue(
        self,
        mock_graph_api: AsyncMock,
        mock_redis_client: AsyncMock,
        mock_db_pool: AsyncMock,
        mock_s3_client: MagicMock,
        mock_event_publisher: MagicMock,
        mock_sqs_client: MagicMock,
    ) -> None:
        """The parsed payload should be sent to the vqms-analysis SQS queue."""
        await process_single_email(
            "msg-test-001",
            graph_api=mock_graph_api,
            redis_client=mock_redis_client,
            db_pool=mock_db_pool,
            s3_client=mock_s3_client,
            event_publisher=mock_event_publisher,
            sqs_client=mock_sqs_client,
        )

        mock_sqs_client.send_message.assert_called_once()
        call_args = mock_sqs_client.send_message.call_args
        assert call_args[0][0] == "vqms-analysis"

    @pytest.mark.asyncio()
    async def test_email_with_attachments(
        self,
        mock_graph_api: AsyncMock,
        mock_redis_client: AsyncMock,
        mock_db_pool: AsyncMock,
        mock_s3_client: MagicMock,
        mock_event_publisher: MagicMock,
        mock_sqs_client: MagicMock,
    ) -> None:
        """Emails with attachments should fetch and store each attachment."""
        # Configure the mock to return an email with attachments
        mock_graph_api.fetch_message.return_value["hasAttachments"] = True
        mock_graph_api.fetch_attachments.return_value = [
            {
                "name": "invoice.pdf",
                "contentType": "application/pdf",
                "size": 245000,
                "contentBytes": "SGVsbG8=",  # base64 for "Hello"
            }
        ]

        result = await process_single_email(
            "msg-test-001",
            graph_api=mock_graph_api,
            redis_client=mock_redis_client,
            db_pool=mock_db_pool,
            s3_client=mock_s3_client,
            event_publisher=mock_event_publisher,
            sqs_client=mock_sqs_client,
        )

        assert result is not None
        assert len(result.attachments) == 1
        assert result.attachments[0].filename == "invoice.pdf"
        mock_s3_client.upload_attachment.assert_called_once()

    @pytest.mark.asyncio()
    async def test_correlation_id_generated_if_not_provided(
        self,
        mock_graph_api: AsyncMock,
        mock_redis_client: AsyncMock,
        mock_db_pool: AsyncMock,
        mock_s3_client: MagicMock,
        mock_event_publisher: MagicMock,
        mock_sqs_client: MagicMock,
    ) -> None:
        """If no correlation_id is passed, one should be auto-generated."""
        result = await process_single_email(
            "msg-test-001",
            graph_api=mock_graph_api,
            redis_client=mock_redis_client,
            db_pool=mock_db_pool,
            s3_client=mock_s3_client,
            event_publisher=mock_event_publisher,
            sqs_client=mock_sqs_client,
            # No correlation_id provided
        )

        assert result is not None
        assert result.correlation_id.startswith("vqms-")
