"""Module: cache/redis_client.py

Redis client wrapper for VQMS with key builders for all 6 key families.

All Redis keys in VQMS follow the pattern: vqms:{family}:{identifier}
Each family has a specific TTL based on its use case:

  1. idempotency — 7 days  (Exchange can redeliver emails up to 5 days)
  2. thread      — 30 days (email threads stay active for weeks)
  3. ticket      — 30 days (ticket lookups during active cases)
  4. workflow    — 24 hours (transient state while case is in progress)
  5. vendor      — 1 hour  (hot cache to avoid repeated Salesforce calls)
  6. sla         — 7 days  (tracking SLA milestones for active tickets)

Corresponds to Section 4 (Redis Key Families) of the architecture document.
"""

from __future__ import annotations

import logging
from typing import Any

import orjson
import redis.asyncio as redis

logger = logging.getLogger(__name__)


# ============================================================
# Key prefix and TTL constants
# ============================================================

KEY_PREFIX = "vqms:"

# TTLs in seconds — each value has a comment explaining WHY
IDEMPOTENCY_TTL_SECONDS = 604800     # 7 days — Exchange can redeliver emails up to 5 days after original send
THREAD_TTL_SECONDS = 2592000         # 30 days — email threads can stay active for weeks
TICKET_TTL_SECONDS = 2592000         # 30 days — tickets can be referenced for weeks after creation
WORKFLOW_TTL_SECONDS = 86400         # 24 hours — workflow state is transient, cases should complete in hours
VENDOR_CACHE_TTL_SECONDS = 3600      # 1 hour — vendor data changes rarely, but we don't want stale data too long
SLA_TTL_SECONDS = 604800             # 7 days — SLA tracking must persist for the entire SLA window


# ============================================================
# Key builder functions
# Pure functions that construct Redis keys — no side effects.
# ============================================================

def build_idempotency_key(message_id: str) -> str:
    """Build key for email deduplication: vqms:idempotency:{message_id}."""
    return f"{KEY_PREFIX}idempotency:{message_id}"


def build_thread_key(thread_id: str) -> str:
    """Build key for thread correlation: vqms:thread:{thread_id}."""
    return f"{KEY_PREFIX}thread:{thread_id}"


def build_ticket_key(ticket_id: str) -> str:
    """Build key for ticket mapping: vqms:ticket:{ticket_id}."""
    return f"{KEY_PREFIX}ticket:{ticket_id}"


def build_workflow_key(correlation_id: str) -> str:
    """Build key for workflow state: vqms:workflow:{correlation_id}."""
    return f"{KEY_PREFIX}workflow:{correlation_id}"


def build_vendor_key(vendor_id: str) -> str:
    """Build key for vendor cache: vqms:vendor:{vendor_id}."""
    return f"{KEY_PREFIX}vendor:{vendor_id}"


def build_sla_key(case_id: str) -> str:
    """Build key for SLA tracking: vqms:sla:{case_id}."""
    return f"{KEY_PREFIX}sla:{case_id}"


# ============================================================
# Redis Client
# ============================================================

class RedisClient:
    """Async Redis client wrapper with typed methods for each key family.

    Wraps redis.asyncio.Redis with JSON serialization and key
    builders for all 6 VQMS key families. Each family has set,
    get, and delete methods with the correct TTL pre-configured.

    Usage:
        client = RedisClient(host="localhost", port=6379)
        await client.connect()
        await client.set_idempotency("msg-123", {"processed_at": "..."})
        data = await client.get_idempotency("msg-123")
        await client.close()
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: str | None = None,
        db: int = 0,
        ssl: bool = False,
    ) -> None:
        """Initialize Redis connection parameters.

        Does not connect immediately — call connect() to establish
        the connection. This allows the client to be created at
        module load time without blocking.
        """
        self._host = host
        self._port = port
        self._password = password
        self._db = db
        self._ssl = ssl
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        """Establish the Redis connection."""
        self._client = redis.Redis(
            host=self._host,
            port=self._port,
            password=self._password,
            db=self._db,
            ssl=self._ssl,
            decode_responses=True,
        )
        logger.info(
            "Redis client connected",
            extra={"host": self._host, "port": self._port},
        )

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            await self._client.aclose()
            logger.info("Redis client connection closed")

    @property
    def client(self) -> redis.Redis:
        """Get the underlying Redis client, raising if not connected."""
        if self._client is None:
            raise RuntimeError(
                "Redis client is not connected. Call connect() first."
            )
        return self._client

    # --------------------------------------------------------
    # Generic helpers for JSON serialization
    # --------------------------------------------------------

    async def _set_json(
        self, key: str, value: dict[str, Any], ttl_seconds: int
    ) -> None:
        """Serialize a dict to JSON and store it with a TTL."""
        serialized = orjson.dumps(value).decode("utf-8")
        await self.client.setex(key, ttl_seconds, serialized)

    async def _get_json(self, key: str) -> dict[str, Any] | None:
        """Retrieve a key and deserialize from JSON. Returns None if missing."""
        raw = await self.client.get(key)
        if raw is None:
            return None
        return orjson.loads(raw)

    async def _delete_key(self, key: str) -> bool:
        """Delete a key. Returns True if the key existed."""
        result = await self.client.delete(key)
        return result > 0

    # --------------------------------------------------------
    # Family 1: Idempotency (prevents duplicate email processing)
    # TTL: 7 days — Exchange can redeliver emails up to 5 days
    # --------------------------------------------------------

    async def set_idempotency(
        self, message_id: str, value: dict[str, Any]
    ) -> None:
        """Mark an email as processed to prevent duplicate handling."""
        key = build_idempotency_key(message_id)
        await self._set_json(key, value, IDEMPOTENCY_TTL_SECONDS)

    async def get_idempotency(self, message_id: str) -> dict[str, Any] | None:
        """Check if an email has already been processed."""
        key = build_idempotency_key(message_id)
        return await self._get_json(key)

    async def delete_idempotency(self, message_id: str) -> bool:
        """Remove an idempotency key (used in testing or error recovery)."""
        key = build_idempotency_key(message_id)
        return await self._delete_key(key)

    # --------------------------------------------------------
    # Family 2: Thread Correlation (groups related emails)
    # TTL: 30 days — email threads can span weeks
    # --------------------------------------------------------

    async def set_thread(
        self, thread_id: str, value: dict[str, Any]
    ) -> None:
        """Store or update thread correlation data."""
        key = build_thread_key(thread_id)
        await self._set_json(key, value, THREAD_TTL_SECONDS)

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        """Look up thread correlation data."""
        key = build_thread_key(thread_id)
        return await self._get_json(key)

    async def delete_thread(self, thread_id: str) -> bool:
        """Remove thread correlation data."""
        key = build_thread_key(thread_id)
        return await self._delete_key(key)

    # --------------------------------------------------------
    # Family 3: Ticket Mapping (links emails to tickets)
    # TTL: 30 days — tickets are referenced during active cases
    # --------------------------------------------------------

    async def set_ticket(
        self, ticket_id: str, value: dict[str, Any]
    ) -> None:
        """Store ticket-to-case mapping."""
        key = build_ticket_key(ticket_id)
        await self._set_json(key, value, TICKET_TTL_SECONDS)

    async def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        """Look up which case and emails are linked to a ticket."""
        key = build_ticket_key(ticket_id)
        return await self._get_json(key)

    async def delete_ticket(self, ticket_id: str) -> bool:
        """Remove ticket mapping."""
        key = build_ticket_key(ticket_id)
        return await self._delete_key(key)

    # --------------------------------------------------------
    # Family 4: Workflow State (transient case execution state)
    # TTL: 24 hours — cases should complete within hours
    # --------------------------------------------------------

    async def set_workflow(
        self, correlation_id: str, value: dict[str, Any]
    ) -> None:
        """Cache workflow state while a case is in progress."""
        key = build_workflow_key(correlation_id)
        await self._set_json(key, value, WORKFLOW_TTL_SECONDS)

    async def get_workflow(
        self, correlation_id: str
    ) -> dict[str, Any] | None:
        """Get cached workflow state for a case."""
        key = build_workflow_key(correlation_id)
        return await self._get_json(key)

    async def delete_workflow(self, correlation_id: str) -> bool:
        """Remove workflow state cache (e.g., after case closes)."""
        key = build_workflow_key(correlation_id)
        return await self._delete_key(key)

    # --------------------------------------------------------
    # Family 5: Vendor Cache (hot vendor data from Salesforce)
    # TTL: 1 hour — vendor data changes rarely
    # --------------------------------------------------------

    async def set_vendor(
        self, vendor_id: str, value: dict[str, Any]
    ) -> None:
        """Cache vendor profile data from Salesforce."""
        key = build_vendor_key(vendor_id)
        await self._set_json(key, value, VENDOR_CACHE_TTL_SECONDS)

    async def get_vendor(self, vendor_id: str) -> dict[str, Any] | None:
        """Look up cached vendor profile."""
        key = build_vendor_key(vendor_id)
        return await self._get_json(key)

    async def delete_vendor(self, vendor_id: str) -> bool:
        """Invalidate vendor cache (e.g., after Salesforce update)."""
        key = build_vendor_key(vendor_id)
        return await self._delete_key(key)

    # --------------------------------------------------------
    # Family 6: SLA Tracking (current SLA status per case)
    # TTL: 7 days — SLA windows can last several days
    # --------------------------------------------------------

    async def set_sla(
        self, case_id: str, value: dict[str, Any]
    ) -> None:
        """Store SLA tracking data for a case."""
        key = build_sla_key(case_id)
        await self._set_json(key, value, SLA_TTL_SECONDS)

    async def get_sla(self, case_id: str) -> dict[str, Any] | None:
        """Get SLA tracking data for a case."""
        key = build_sla_key(case_id)
        return await self._get_json(key)

    async def delete_sla(self, case_id: str) -> bool:
        """Remove SLA tracking data (e.g., after case closes)."""
        key = build_sla_key(case_id)
        return await self._delete_key(key)
