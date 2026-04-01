"""Shared test fixtures for VQMS.

Provides reusable sample data and mock objects used across
multiple test modules. Import fixtures by name in test files —
pytest discovers them automatically from conftest.py.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.models.email import EmailAttachment, EmailMessage, ParsedEmailPayload
from src.models.vendor import VendorMatch, VendorProfile, VendorTier


@pytest.fixture()
def sample_email_attachment() -> EmailAttachment:
    """A sample PDF attachment for testing."""
    return EmailAttachment(
        filename="invoice_2024_001.pdf",
        mime_type="application/pdf",
        file_size_bytes=245_000,
        s3_path="msg-abc123/invoice_2024_001.pdf",
    )


@pytest.fixture()
def sample_email_message() -> EmailMessage:
    """A sample incoming vendor email for testing."""
    return EmailMessage(
        message_id="AAMkAGI2TG93AAA=",
        correlation_id="vqms-test-corr-001",
        sender_email="john.doe@acme-corp.com",
        sender_name="John Doe",
        subject="Invoice #INV-2024-001 Payment Status",
        body_plain="Hello, I would like to check the status of invoice INV-2024-001. "
        "The amount is $15,000 and it was due on 2024-03-15. "
        "Please provide an update. Thanks, John",
        body_html=None,
        received_at=datetime(2024, 3, 20, 10, 30, 0, tzinfo=UTC),
    )


@pytest.fixture()
def sample_parsed_email() -> ParsedEmailPayload:
    """A sample parsed email payload for testing."""
    return ParsedEmailPayload(
        message_id="AAMkAGI2TG93AAA=",
        correlation_id="vqms-test-corr-001",
        sender_email="john.doe@acme-corp.com",
        sender_name="John Doe",
        subject="Invoice #INV-2024-001 Payment Status",
        body_plain="Hello, I would like to check the status of invoice INV-2024-001.",
        received_at=datetime(2024, 3, 20, 10, 30, 0, tzinfo=UTC),
        s3_raw_path="2024/03/20/AAMkAGI2TG93AAA=/raw.eml",
        is_duplicate=False,
    )


@pytest.fixture()
def sample_vendor_match() -> VendorMatch:
    """A sample vendor match result for testing."""
    return VendorMatch(
        vendor_id="SF-ACC-001",
        vendor_name="Acme Corporation",
        vendor_tier=VendorTier.GOLD,
        match_method="EMAIL_EXACT",
        match_confidence=0.95,
        risk_flags=[],
    )


@pytest.fixture()
def sample_vendor_profile() -> VendorProfile:
    """A sample vendor profile for testing."""
    return VendorProfile(
        vendor_id="SF-ACC-001",
        vendor_name="Acme Corporation",
        tier=VendorTier.GOLD,
        sla_hours=12,
        risk_flags=[],
        last_seen=datetime(2024, 3, 20, 10, 30, 0, tzinfo=UTC),
        last_ticket_id="INC0012345",
        interaction_count=15,
        avg_resolution_time_hours=8.5,
    )
