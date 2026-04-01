"""Tests for VQMS S3 storage client.

Uses moto to mock AWS S3 so tests run without real AWS credentials.
Tests verify that uploads produce correct S3 keys and that content
is stored and retrievable.
"""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from src.storage.s3_client import (
    BUCKET_ATTACHMENTS,
    BUCKET_AUDIT,
    BUCKET_EMAIL_RAW,
    S3Client,
    _build_date_prefix,
)


@pytest.fixture()
def _create_s3_buckets():
    """Create mock S3 buckets before each test."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET_EMAIL_RAW)
        s3.create_bucket(Bucket=BUCKET_ATTACHMENTS)
        s3.create_bucket(Bucket=BUCKET_AUDIT)
        yield


class TestDatePrefix:
    """Test the date prefix builder."""

    def test_format_is_yyyy_mm_dd(self) -> None:
        """Date prefix should be in YYYY/MM/DD format."""
        prefix = _build_date_prefix()
        parts = prefix.split("/")
        assert len(parts) == 3
        assert len(parts[0]) == 4  # YYYY
        assert len(parts[1]) == 2  # MM
        assert len(parts[2]) == 2  # DD


@pytest.mark.usefixtures("_create_s3_buckets")
class TestRawEmailStorage:
    """Test raw email upload and download."""

    @mock_aws
    def test_upload_raw_email_returns_s3_key(self) -> None:
        """Upload should return a valid S3 key with date prefix."""
        # Re-create bucket inside mock context
        boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket=BUCKET_EMAIL_RAW
        )
        client = S3Client(region="us-east-1")
        key = client.upload_raw_email(
            "msg-123",
            b"raw email content",
            correlation_id="test-corr",
        )
        assert key.startswith("raw-emails/")
        assert key.endswith("msg-123.eml")

    @mock_aws
    def test_upload_and_download_roundtrip(self) -> None:
        """Content should survive an upload-download roundtrip."""
        boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket=BUCKET_EMAIL_RAW
        )
        client = S3Client(region="us-east-1")
        content = b"From: vendor@example.com\nSubject: Test\n\nHello"
        key = client.upload_raw_email("msg-456", content)
        downloaded = client.download_raw_email(key)
        assert downloaded == content

    @mock_aws
    def test_message_id_with_slashes_is_sanitized(self) -> None:
        """Message IDs with path separators should be sanitized."""
        boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket=BUCKET_EMAIL_RAW
        )
        client = S3Client(region="us-east-1")
        key = client.upload_raw_email("msg/with/slashes", b"content")
        assert "//" not in key  # No double slashes from sanitization
        assert "msg_with_slashes" in key


@pytest.mark.usefixtures("_create_s3_buckets")
class TestAttachmentStorage:
    """Test attachment upload."""

    @mock_aws
    def test_upload_attachment_returns_s3_key(self) -> None:
        """Attachment upload should return key with message_id and filename."""
        boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket=BUCKET_ATTACHMENTS
        )
        client = S3Client(region="us-east-1")
        key = client.upload_attachment(
            "msg-789",
            "invoice.pdf",
            b"PDF content",
            "application/pdf",
            correlation_id="test-corr",
        )
        assert key.startswith("attachments/")
        assert "msg-789" in key
        assert key.endswith("invoice.pdf")


@pytest.mark.usefixtures("_create_s3_buckets")
class TestAuditArtifactStorage:
    """Test audit artifact upload."""

    @mock_aws
    def test_upload_audit_artifact_uses_correlation_id_as_folder(self) -> None:
        """Audit artifacts should be stored under the correlation_id folder."""
        boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket=BUCKET_AUDIT
        )
        client = S3Client(region="us-east-1")
        key = client.upload_audit_artifact(
            "vqms-corr-001",
            "analysis.json",
            b'{"intent": "invoice_inquiry"}',
        )
        assert key == "vqms-corr-001/analysis.json"
