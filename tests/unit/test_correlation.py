"""Tests for VQMS correlation ID generation.

Verifies that correlation IDs have the correct format and
are unique across multiple generations.
"""

from __future__ import annotations

from src.utils.correlation import CORRELATION_ID_PREFIX, generate_correlation_id


class TestCorrelationIdGeneration:
    """Test the generate_correlation_id function."""

    def test_starts_with_vqms_prefix(self) -> None:
        """Correlation ID must start with 'vqms-' for identification."""
        corr_id = generate_correlation_id()
        assert corr_id.startswith(f"{CORRELATION_ID_PREFIX}-")

    def test_has_uuid_format(self) -> None:
        """After the prefix, the ID should contain a valid UUID."""
        corr_id = generate_correlation_id()
        # Format: vqms-{uuid4}
        # UUID4 has the pattern: 8-4-4-4-12 hex chars
        parts = corr_id.split("-", 1)
        assert parts[0] == "vqms"
        uuid_part = parts[1]
        # UUID should have 4 hyphens and 32 hex chars
        assert len(uuid_part.replace("-", "")) == 32

    def test_unique_across_calls(self) -> None:
        """Each call should produce a different ID."""
        ids = {generate_correlation_id() for _ in range(100)}
        assert len(ids) == 100  # All 100 should be unique

    def test_prefix_constant_is_vqms(self) -> None:
        """The prefix constant should be 'vqms'."""
        assert CORRELATION_ID_PREFIX == "vqms"
