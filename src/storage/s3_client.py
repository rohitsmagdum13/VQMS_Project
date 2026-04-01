"""Module: storage/s3_client.py

S3 client for VQMS with upload/download methods for all 4 buckets.

Handles storage of raw emails, attachments, audit artifacts, and
knowledge base documents. Each bucket has a specific path format
defined by the architecture document.

Path formats:
  - Raw emails:   raw-emails/YYYY-MM-DD/{correlation_id}/{correlation_id}.json
  - Attachments:  attachments/YYYY-MM-DD/{correlation_id}/{filename}
  - Audit:        {correlation_id}/analysis.json, draft.html, etc.
  - Knowledge:    vendor_guides/, sla_templates/, etc.

Usage:
    from src.storage.s3_client import S3Client

    s3 = S3Client()
    path = await s3.upload_raw_email(message_id, raw_content)
    content = await s3.download_raw_email(path)
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class S3StorageError(Exception):
    """Raised when an S3 operation fails.

    Covers: upload failures, download failures, bucket not found,
    access denied, and network errors.
    """


# Bucket names from environment — defaults match .env.copy
BUCKET_EMAIL_RAW = os.getenv("S3_BUCKET_EMAIL_RAW", "vqms-email-raw-prod")
BUCKET_ATTACHMENTS = os.getenv("S3_BUCKET_ATTACHMENTS", "vqms-email-attachments-prod")
BUCKET_AUDIT = os.getenv("S3_BUCKET_AUDIT_ARTIFACTS", "vqms-audit-artifacts-prod")
BUCKET_KNOWLEDGE = os.getenv("S3_BUCKET_KNOWLEDGE", "vqms-knowledge-artifacts-prod")


def _build_date_prefix() -> str:
    """Build a YYYY-MM-DD path prefix from today's date (UTC).

    Single date folder (not nested year/month/day) for cleaner
    S3 browsability and simpler path structure.
    """
    now = datetime.now(UTC)
    return f"{now.year:04d}-{now.month:02d}-{now.day:02d}"


class S3Client:
    """S3 storage client for VQMS.

    Wraps boto3 S3 client with typed methods for each storage pattern.
    Uses synchronous boto3 (not aioboto3) for simplicity in development
    mode — production may switch to async.

    All methods accept optional correlation_id for log tracing.
    """

    def __init__(self, region: str | None = None) -> None:
        """Initialize the S3 client.

        Args:
            region: AWS region. Defaults to AWS_REGION env var.
        """
        self._region = region or os.getenv("AWS_REGION", "us-east-1")
        self._client = boto3.client("s3", region_name=self._region)

    # --------------------------------------------------------
    # Raw Email Storage (vqms-email-raw-dev)
    # Path: raw-emails/YYYY/MM/DD/{correlation_id}/{correlation_id}.json
    # --------------------------------------------------------

    def upload_raw_email(
        self,
        message_id: str,
        content: bytes,
        *,
        correlation_id: str | None = None,
    ) -> str:
        """Upload a raw email to S3 as JSON.

        Stores the Graph API JSON response for archival and
        reprocessing. This is the first write in the ingestion
        pipeline — raw storage happens before parsing.

        Path structure:
          raw-emails/YYYY/MM/DD/{correlation_id}/{correlation_id}.json

        The correlation_id is used as folder and filename because
        it is short and human-readable (e.g., vqms-a1b2c3d4-...).
        The full Exchange message_id is inside the JSON content.

        Args:
            message_id: Exchange Online message ID (stored in content).
            content: Graph API JSON response as bytes.
            correlation_id: Tracing ID — used for the filename.

        Returns:
            The S3 key where the email was stored.

        Raises:
            S3StorageError: If the upload fails.
        """
        date_prefix = _build_date_prefix()

        # Use correlation_id as the folder and filename because it is
        # short and readable. Falls back to sanitized message_id if
        # correlation_id is not provided.
        folder_name = correlation_id or message_id.replace("/", "_").replace("\\", "_")

        s3_key = f"raw-emails/{date_prefix}/{folder_name}/{folder_name}.json"

        try:
            self._client.put_object(
                Bucket=BUCKET_EMAIL_RAW,
                Key=s3_key,
                Body=content,
                ContentType="application/json",
            )
            logger.info(
                "Raw email uploaded to S3",
                extra={
                    "s3_key": s3_key,
                    "size_bytes": len(content),
                    "correlation_id": correlation_id,
                },
            )
            return s3_key
        except ClientError as exc:
            raise S3StorageError(
                f"Failed to upload raw email to S3: {exc}"
            ) from exc

    def download_raw_email(
        self,
        s3_key: str,
        *,
        correlation_id: str | None = None,
    ) -> bytes:
        """Download a raw email from S3.

        Args:
            s3_key: The S3 key returned by upload_raw_email.
            correlation_id: Tracing ID for log context.

        Returns:
            Raw email content as bytes.

        Raises:
            S3StorageError: If the download fails.
        """
        try:
            response = self._client.get_object(
                Bucket=BUCKET_EMAIL_RAW,
                Key=s3_key,
            )
            return response["Body"].read()
        except ClientError as exc:
            raise S3StorageError(
                f"Failed to download raw email from S3: {exc}"
            ) from exc

    # --------------------------------------------------------
    # Attachment Storage (vqms-email-attachments-prod)
    # Path: attachments/YYYY/MM/DD/{correlation_id}/{filename}
    # --------------------------------------------------------

    def upload_attachment(
        self,
        message_id: str,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        *,
        correlation_id: str | None = None,
    ) -> str:
        """Upload an email attachment to S3.

        Path structure:
          attachments/YYYY/MM/DD/{correlation_id}/{filename}

        Uses correlation_id as the folder name (same pattern as
        raw email storage) for consistency and readability.

        Args:
            message_id: Exchange Online message ID (parent email).
            filename: Original filename from the email.
            content: Attachment file content as bytes.
            content_type: MIME type of the attachment.
            correlation_id: Tracing ID — used for the folder name.

        Returns:
            The S3 key where the attachment was stored.

        Raises:
            S3StorageError: If the upload fails.
        """
        date_prefix = _build_date_prefix()

        # Use correlation_id as folder name for consistency with
        # raw email storage. Falls back to sanitized message_id.
        folder_name = correlation_id or message_id.replace("/", "_").replace("\\", "_")

        # Preserve original filename but sanitize path separators
        safe_filename = filename.replace("/", "_").replace("\\", "_")
        s3_key = f"attachments/{date_prefix}/{folder_name}/{safe_filename}"

        try:
            self._client.put_object(
                Bucket=BUCKET_ATTACHMENTS,
                Key=s3_key,
                Body=content,
                ContentType=content_type,
            )
            logger.info(
                "Attachment uploaded to S3",
                extra={
                    "s3_key": s3_key,
                    "attachment_filename": filename,
                    "size_bytes": len(content),
                    "correlation_id": correlation_id,
                },
            )
            return s3_key
        except ClientError as exc:
            raise S3StorageError(
                f"Failed to upload attachment to S3: {exc}"
            ) from exc

    # --------------------------------------------------------
    # Audit Artifacts (vqms-audit-artifacts-prod)
    # Path: {correlation_id}/{artifact_name}
    # --------------------------------------------------------

    def upload_audit_artifact(
        self,
        correlation_id: str,
        artifact_name: str,
        content: bytes,
        content_type: str = "application/json",
    ) -> str:
        """Upload an audit artifact to S3.

        Audit artifacts include analysis results, drafts, and
        validation reports stored for compliance purposes.

        Args:
            correlation_id: Case trace ID (used as folder).
            artifact_name: Filename (e.g., 'analysis.json', 'draft.html').
            content: Artifact content as bytes.
            content_type: MIME type of the artifact.

        Returns:
            The S3 key where the artifact was stored.

        Raises:
            S3StorageError: If the upload fails.
        """
        s3_key = f"{correlation_id}/{artifact_name}"

        try:
            self._client.put_object(
                Bucket=BUCKET_AUDIT,
                Key=s3_key,
                Body=content,
                ContentType=content_type,
            )
            logger.info(
                "Audit artifact uploaded to S3",
                extra={
                    "s3_key": s3_key,
                    "correlation_id": correlation_id,
                },
            )
            return s3_key
        except ClientError as exc:
            raise S3StorageError(
                f"Failed to upload audit artifact to S3: {exc}"
            ) from exc
