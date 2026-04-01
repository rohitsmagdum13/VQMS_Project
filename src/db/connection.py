"""Module: db/connection.py

PostgreSQL async connection pool for VQMS.

Provides a shared connection pool using asyncpg that all services
use to read/write the 5 PostgreSQL schemas (intake, workflow,
memory, audit, reporting).

Uses asyncpg directly rather than SQLAlchemy ORM — in development
mode we prefer explicit SQL for clarity and debuggability.

Usage:
    from src.db.connection import DatabasePool

    pool = DatabasePool()
    await pool.connect()
    row = await pool.fetchrow("SELECT * FROM intake.email_messages WHERE id = $1", msg_id)
    await pool.close()
"""

from __future__ import annotations

import logging
import os
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


class DatabaseConnectionError(Exception):
    """Raised when the database connection pool cannot be created or a query fails.

    This covers: connection refused, auth failure, pool exhaustion,
    query syntax errors, and constraint violations.
    """


class DatabasePool:
    """Async PostgreSQL connection pool wrapper.

    Thin wrapper around asyncpg.Pool that loads connection settings
    from environment variables and provides simple query methods.

    All methods accept optional correlation_id for log tracing.
    """

    def __init__(self) -> None:
        """Initialize with connection settings from environment.

        Does not connect immediately — call connect() to create the pool.
        """
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Create the connection pool using settings from environment variables.

        Reads POSTGRES_* variables from .env. Pool size is controlled
        by POSTGRES_POOL_MIN and POSTGRES_POOL_MAX.

        Raises:
            DatabaseConnectionError: If the pool cannot be created
                (e.g., wrong credentials, host unreachable).
        """
        try:
            # Neon and other cloud-hosted PostgreSQL providers require SSL.
            # POSTGRES_SSLMODE controls this: "require" for cloud, empty for local.
            ssl_mode = os.getenv("POSTGRES_SSLMODE", "")
            ssl_param = ssl_mode if ssl_mode else False

            self._pool = await asyncpg.create_pool(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
                database=os.getenv("POSTGRES_DB", "vqms"),
                user=os.getenv("POSTGRES_USER", "postgres"),
                password=os.getenv("POSTGRES_PASSWORD", ""),
                min_size=int(os.getenv("POSTGRES_POOL_MIN", "5")),
                max_size=int(os.getenv("POSTGRES_POOL_MAX", "20")),
                ssl=ssl_param,
            )
            logger.info(
                "Database connection pool created",
                extra={
                    "host": os.getenv("POSTGRES_HOST", "localhost"),
                    "database": os.getenv("POSTGRES_DB", "vqms"),
                },
            )
        except Exception as exc:
            raise DatabaseConnectionError(
                f"Failed to create database connection pool: {exc}"
            ) from exc

    async def close(self) -> None:
        """Close the connection pool and release all connections."""
        if self._pool:
            await self._pool.close()
            logger.info("Database connection pool closed")

    @property
    def pool(self) -> asyncpg.Pool:
        """Get the underlying pool, raising if not connected."""
        if self._pool is None:
            raise DatabaseConnectionError(
                "Database pool is not connected. Call connect() first."
            )
        return self._pool

    # --------------------------------------------------------
    # Query helpers — thin wrappers for common asyncpg patterns
    # --------------------------------------------------------

    async def execute(
        self,
        query: str,
        *args: Any,
        correlation_id: str | None = None,
    ) -> str:
        """Execute a query that does not return rows (INSERT, UPDATE, DELETE).

        Args:
            query: SQL query with $1, $2, ... placeholders.
            *args: Values for the placeholders.
            correlation_id: Tracing ID for log context.

        Returns:
            Status string from PostgreSQL (e.g., 'INSERT 0 1').

        Raises:
            DatabaseConnectionError: On query failure.
        """
        try:
            result = await self.pool.execute(query, *args)
            logger.debug(
                "Query executed",
                extra={"correlation_id": correlation_id, "status": result},
            )
            return result
        except Exception as exc:
            logger.error(
                "Query execution failed",
                extra={"correlation_id": correlation_id, "error": str(exc)},
            )
            raise DatabaseConnectionError(
                f"Query execution failed: {exc}"
            ) from exc

    async def fetchrow(
        self,
        query: str,
        *args: Any,
        correlation_id: str | None = None,
    ) -> asyncpg.Record | None:
        """Fetch a single row. Returns None if no match.

        Args:
            query: SQL query with $1, $2, ... placeholders.
            *args: Values for the placeholders.
            correlation_id: Tracing ID for log context.

        Returns:
            A single asyncpg.Record, or None if no rows matched.

        Raises:
            DatabaseConnectionError: On query failure.
        """
        try:
            return await self.pool.fetchrow(query, *args)
        except Exception as exc:
            logger.error(
                "Fetchrow failed",
                extra={"correlation_id": correlation_id, "error": str(exc)},
            )
            raise DatabaseConnectionError(
                f"Fetchrow failed: {exc}"
            ) from exc

    async def fetch(
        self,
        query: str,
        *args: Any,
        correlation_id: str | None = None,
    ) -> list[asyncpg.Record]:
        """Fetch multiple rows.

        Args:
            query: SQL query with $1, $2, ... placeholders.
            *args: Values for the placeholders.
            correlation_id: Tracing ID for log context.

        Returns:
            List of asyncpg.Record objects (empty list if no matches).

        Raises:
            DatabaseConnectionError: On query failure.
        """
        try:
            return await self.pool.fetch(query, *args)
        except Exception as exc:
            logger.error(
                "Fetch failed",
                extra={"correlation_id": correlation_id, "error": str(exc)},
            )
            raise DatabaseConnectionError(
                f"Fetch failed: {exc}"
            ) from exc
