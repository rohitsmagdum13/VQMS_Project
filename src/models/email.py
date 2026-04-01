"""Module: models/email.py

Pydantic models for email data in VQMS.

These models define the shape of email information as it flows
through the pipeline — from Exchange Online ingestion through
parsing to downstream analysis.

Corresponds to the intake schema in the architecture document.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class EmailAttachment(BaseModel):
    """A single file attached to an incoming vendor email.

    Attachments are stored in S3 (vqms-email-attachments-prod)
    and referenced by their s3_path for downstream processing.
    """

    filename: str = Field(description="Original filename from the email")
    mime_type: str = Field(description="MIME type (e.g., 'application/pdf')")
    file_size_bytes: int = Field(description="Size of the attachment in bytes")
    s3_path: str | None = Field(
        default=None,
        description="Path in vqms-email-attachments-prod bucket. "
        "None until the attachment is uploaded to S3.",
    )


class EmailMessage(BaseModel):
    """An incoming vendor email fetched from Exchange Online.

    This is the core data object for the email ingestion pipeline.
    It holds the raw email content and metadata needed for
    downstream analysis, vendor resolution, and ticket creation.
    """

    # Identity — uniquely identifies this email in Exchange Online
    message_id: str = Field(
        description="Exchange Online message ID (unique across mailbox)"
    )
    correlation_id: str = Field(
        description="Trace ID that follows this email through "
        "the entire VQMS pipeline"
    )

    # Sender information
    sender_email: str = Field(description="Email address of the sender")
    sender_name: str | None = Field(
        default=None,
        description="Display name of the sender (may be absent)",
    )

    # Recipients
    to_address: str = Field(
        description="Primary recipient email address"
    )
    cc_addresses: str | None = Field(
        default=None,
        description="CC recipients as semicolon-separated emails (e.g., 'a@x.com;b@y.com')",
    )

    # Email content
    subject: str = Field(description="Email subject line")
    body_plain: str = Field(description="Plain text body of the email")
    body_html: str | None = Field(
        default=None,
        description="HTML body if available (some emails are plain text only)",
    )

    # Timestamps
    received_at: datetime = Field(
        description="When the email was received by Exchange Online (UTC)"
    )

    # Thread and reply tracking
    thread_id: str | None = Field(
        default=None,
        description="Graph API conversationId — groups related emails into a thread",
    )
    is_reply: bool = Field(
        default=False,
        description="True if this email is a reply to an earlier message",
    )
    is_auto_reply: bool = Field(
        default=False,
        description="True if this is an auto-reply (out-of-office, delivery receipt, etc.)",
    )

    # Metadata
    language: str = Field(
        default="en",
        description="Detected language code (ISO 639-1). Default 'en' until Comprehend is integrated",
    )
    status: str = Field(
        default="INGESTED",
        description="Pipeline status: INGESTED → ANALYZED → ROUTED → RESOLVED",
    )

    # Attachments and storage
    has_attachments: bool = Field(
        default=False,
        description="True if the email has file attachments",
    )
    attachment_count: int = Field(
        default=0,
        description="Number of attachments on this email",
    )
    attachments: list[EmailAttachment] = Field(
        default_factory=list,
        description="List of file attachments on this email",
    )
    s3_raw_path: str | None = Field(
        default=None,
        description="Path to the raw JSON in vqms-email-raw-dev bucket. "
        "None until the raw email is stored in S3.",
    )


class ParsedEmailPayload(BaseModel):
    """The fully parsed result of email ingestion.

    Produced by the Email Ingestion Service after fetching,
    parsing, deduplicating, and storing the email. This payload
    is published to the vqms-analysis SQS queue for the
    Email Analysis Agent to consume.
    """

    # Identity
    message_id: str = Field(
        description="Exchange Online message ID"
    )
    correlation_id: str = Field(
        description="Trace ID for the pipeline"
    )

    # Sender
    sender_email: str = Field(description="Sender email address")
    sender_name: str | None = Field(default=None)

    # Recipients
    to_address: str = Field(description="Primary recipient email address")
    cc_addresses: str | None = Field(default=None)

    # Content
    subject: str = Field(description="Email subject line")
    body_plain: str = Field(description="Plain text body")
    body_html: str | None = Field(default=None)

    # Timestamps
    received_at: datetime = Field(description="When email was received (UTC)")
    parsed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When parsing completed (UTC)",
    )

    # Thread and reply tracking
    thread_id: str | None = Field(default=None)
    is_reply: bool = Field(default=False)
    is_auto_reply: bool = Field(default=False)

    # Metadata
    language: str = Field(default="en")
    status: str = Field(default="INGESTED")

    # Attachments and storage
    has_attachments: bool = Field(default=False)
    attachment_count: int = Field(default=0)
    attachments: list[EmailAttachment] = Field(default_factory=list)
    s3_raw_path: str = Field(
        description="Path to raw JSON in S3 — always populated after parsing"
    )

    # Deduplication flag — checked against Redis idempotency key
    is_duplicate: bool = Field(
        default=False,
        description="True if this message_id was already processed. "
        "Duplicates are logged but not sent downstream.",
    )
