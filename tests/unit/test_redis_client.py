"""Tests for VQMS Redis client key builders and TTL constants.

Tests the key generation functions (pure, no Redis connection needed)
and verifies all TTL constants match the architecture specification.
"""

from __future__ import annotations

from src.cache.redis_client import (
    IDEMPOTENCY_TTL_SECONDS,
    KEY_PREFIX,
    SLA_TTL_SECONDS,
    THREAD_TTL_SECONDS,
    TICKET_TTL_SECONDS,
    VENDOR_CACHE_TTL_SECONDS,
    WORKFLOW_TTL_SECONDS,
    build_idempotency_key,
    build_sla_key,
    build_thread_key,
    build_ticket_key,
    build_vendor_key,
    build_workflow_key,
)

# ============================================================
# Key Prefix
# ============================================================


class TestKeyPrefix:
    """Verify the global key prefix."""

    def test_key_prefix_is_vqms(self) -> None:
        """All VQMS Redis keys must start with 'vqms:'."""
        assert KEY_PREFIX == "vqms:"


# ============================================================
# TTL Constants
# ============================================================


class TestTTLConstants:
    """Verify TTL values match the architecture specification."""

    def test_idempotency_ttl_is_7_days(self) -> None:
        """Idempotency TTL must be 7 days (604800 seconds).
        Exchange Online can redeliver emails up to 5 days after send.
        """
        assert IDEMPOTENCY_TTL_SECONDS == 604800
        assert IDEMPOTENCY_TTL_SECONDS == 7 * 24 * 60 * 60

    def test_thread_ttl_is_30_days(self) -> None:
        """Thread TTL must be 30 days (2592000 seconds)."""
        assert THREAD_TTL_SECONDS == 2592000
        assert THREAD_TTL_SECONDS == 30 * 24 * 60 * 60

    def test_ticket_ttl_is_30_days(self) -> None:
        """Ticket TTL must be 30 days (2592000 seconds)."""
        assert TICKET_TTL_SECONDS == 2592000

    def test_workflow_ttl_is_24_hours(self) -> None:
        """Workflow TTL must be 24 hours (86400 seconds)."""
        assert WORKFLOW_TTL_SECONDS == 86400
        assert WORKFLOW_TTL_SECONDS == 24 * 60 * 60

    def test_vendor_cache_ttl_is_1_hour(self) -> None:
        """Vendor cache TTL must be 1 hour (3600 seconds)."""
        assert VENDOR_CACHE_TTL_SECONDS == 3600

    def test_sla_ttl_is_7_days(self) -> None:
        """SLA TTL must be 7 days (604800 seconds)."""
        assert SLA_TTL_SECONDS == 604800


# ============================================================
# Key Builder Functions
# ============================================================


class TestIdempotencyKey:
    """Test idempotency key generation."""

    def test_key_format(self) -> None:
        """Key should be: vqms:idempotency:{message_id}."""
        key = build_idempotency_key("AAMkAGI2TG93AAA=")
        assert key == "vqms:idempotency:AAMkAGI2TG93AAA="

    def test_key_starts_with_prefix(self) -> None:
        """Key must start with the global prefix."""
        key = build_idempotency_key("msg-123")
        assert key.startswith(KEY_PREFIX)


class TestThreadKey:
    """Test thread correlation key generation."""

    def test_key_format(self) -> None:
        """Key should be: vqms:thread:{thread_id}."""
        key = build_thread_key("thread-abc-123")
        assert key == "vqms:thread:thread-abc-123"


class TestTicketKey:
    """Test ticket mapping key generation."""

    def test_key_format(self) -> None:
        """Key should be: vqms:ticket:{ticket_id}."""
        key = build_ticket_key("INC0012345")
        assert key == "vqms:ticket:INC0012345"


class TestWorkflowKey:
    """Test workflow state key generation."""

    def test_key_format(self) -> None:
        """Key should be: vqms:workflow:{correlation_id}."""
        key = build_workflow_key("vqms-a1b2c3d4")
        assert key == "vqms:workflow:vqms-a1b2c3d4"


class TestVendorKey:
    """Test vendor cache key generation."""

    def test_key_format(self) -> None:
        """Key should be: vqms:vendor:{vendor_id}."""
        key = build_vendor_key("SF-ACC-001")
        assert key == "vqms:vendor:SF-ACC-001"


class TestSlaKey:
    """Test SLA tracking key generation."""

    def test_key_format(self) -> None:
        """Key should be: vqms:sla:{case_id}."""
        key = build_sla_key("42")
        assert key == "vqms:sla:42"


# ============================================================
# All Keys Use Correct Prefix
# ============================================================


class TestAllKeysHavePrefix:
    """Ensure all key builders produce keys with the vqms: prefix."""

    def test_all_builders_use_prefix(self) -> None:
        """Every key builder function must produce a key starting with 'vqms:'."""
        builders_and_args = [
            (build_idempotency_key, "test"),
            (build_thread_key, "test"),
            (build_ticket_key, "test"),
            (build_workflow_key, "test"),
            (build_vendor_key, "test"),
            (build_sla_key, "test"),
        ]
        for builder, arg in builders_and_args:
            key = builder(arg)
            assert key.startswith("vqms:"), f"{builder.__name__} missing prefix"
