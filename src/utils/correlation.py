"""Module: utils/correlation.py

Correlation ID generation for VQMS.

Every email that enters the VQMS pipeline gets a unique correlation ID
that follows it through every service, queue, agent, and log entry.
This makes it possible to trace an email's entire journey from
intake to response in a single log query.

The format is: vqms-{uuid4} (e.g., vqms-a1b2c3d4-e5f6-7890-abcd-ef1234567890)
The prefix makes VQMS correlation IDs easy to identify in mixed log streams.
"""

from __future__ import annotations

import uuid

# Prefix for all VQMS correlation IDs — makes them easy to
# identify in mixed log streams (e.g., alongside AWS request IDs)
CORRELATION_ID_PREFIX = "vqms"


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for a new VQMS pipeline run.

    Returns:
        A string in the format: vqms-{uuid4}
        Example: vqms-a1b2c3d4-e5f6-7890-abcd-ef1234567890
    """
    return f"{CORRELATION_ID_PREFIX}-{uuid.uuid4()}"
