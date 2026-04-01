"""Module: utils/retry.py

Simple retry decorator with exponential backoff for VQMS.

Uses tenacity for retry logic. In development mode, we keep
retry configuration simple — just exponential backoff with
a max attempt count. Production will add circuit breakers
and more sophisticated error classification.

Usage:
    from src.utils.retry import with_retry

    @with_retry(max_attempts=3)
    async def call_salesforce(query: str) -> dict:
        ...
"""

from __future__ import annotations

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Default retry settings for development mode
# These are intentionally conservative — we retry a few times
# with increasing delays, then give up and let the caller handle it
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_WAIT_MIN_SECONDS = 1
DEFAULT_WAIT_MAX_SECONDS = 10


def with_retry(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    wait_min: int = DEFAULT_WAIT_MIN_SECONDS,
    wait_max: int = DEFAULT_WAIT_MAX_SECONDS,
    retry_on: type[Exception] | tuple[type[Exception], ...] = Exception,
):
    """Create a retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts before giving up.
        wait_min: Minimum wait time in seconds between retries.
        wait_max: Maximum wait time in seconds between retries.
        retry_on: Exception type(s) that should trigger a retry.
            Defaults to all exceptions. In production, this should
            be narrowed to transient errors only (timeouts, 429s).

    Returns:
        A decorator that adds retry logic to async or sync functions.
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(min=wait_min, max=wait_max),
        retry=retry_if_exception_type(retry_on),
        reraise=True,
    )
