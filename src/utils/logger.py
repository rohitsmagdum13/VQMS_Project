"""Module: utils/logger.py

Structured JSON logging setup for VQMS using structlog.

All VQMS services and agents use this logger configuration.
Every log entry includes a correlation_id field for tracing
an email through the entire pipeline.

Logs are written to two destinations:
  1. stdout — for real-time visibility during development
  2. data/logs/vqms.log — persistent log file for debugging

Usage:
    from src.utils.logger import setup_logging, get_logger

    setup_logging()  # Call once at application startup
    logger = get_logger(__name__)
    logger.info("Processing email", correlation_id="abc-123", message_id="msg-456")
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog


def setup_logging(log_level: str = "DEBUG") -> None:
    """Configure structured JSON logging for the entire application.

    Sets up structlog to output JSON-formatted log entries with
    timestamps, log levels, and any bound context variables
    (like correlation_id). Should be called once at startup.

    Logs go to both stdout and data/logs/vqms.log. The log file
    rotates at 10 MB and keeps 5 backup files.

    Args:
        log_level: Minimum log level to output. Defaults to DEBUG
            for development mode. Production should use INFO.
    """
    # Configure structlog processors — each one transforms the log event
    structlog.configure(
        processors=[
            # Add log level name (e.g., "info", "error")
            structlog.stdlib.add_log_level,
            # Add ISO-format timestamp
            structlog.processors.TimeStamper(fmt="iso"),
            # Format stack traces for exceptions
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Render as JSON for structured log aggregation
            structlog.processors.JSONRenderer(),
        ],
        # Use standard library logger as the backend
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Determine the numeric log level
    numeric_level = getattr(logging, log_level.upper(), logging.DEBUG)

    # Ensure the log directory exists
    # Project root is 3 levels up from this file: src/utils/logger.py → project root
    project_root = Path(__file__).resolve().parent.parent.parent
    log_dir = project_root / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "vqms.log"

    # File handler — rotates at 10 MB, keeps 5 backups
    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(logging.Formatter("%(message)s"))

    # Stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(numeric_level)
    stdout_handler.setFormatter(logging.Formatter("%(message)s"))

    # Configure the root logger with both handlers so that
    # third-party libraries (boto3, httpx, etc.) also write
    # to the same destinations
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Clear any existing handlers to avoid duplicate output
    # when setup_logging is called more than once
    root_logger.handlers.clear()
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(file_handler)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger bound to a module name.

    Args:
        name: Module name (typically __name__). Appears in log
            output so you can tell which module produced the log.

    Returns:
        A bound logger that supports .info(), .error(), etc.
        with keyword arguments for structured context.
    """
    return structlog.get_logger(name)
