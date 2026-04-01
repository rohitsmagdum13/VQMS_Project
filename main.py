"""VQMS — Vendor Query Management System.

Entry point for the VQMS Agentic AI Platform.
This module bootstraps the FastAPI application and starts the server.

Phase 1: Stub only — actual server setup will be added in later phases.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def main() -> None:
    """Start the VQMS application.

    TODO: Phase 2+ will initialize FastAPI, database connections,
    Redis, and the LangGraph orchestration pipeline.
    """
    logger.info("VQMS application starting")
    raise NotImplementedError("Application server setup pending — Phase 2+")


if __name__ == "__main__":
    main()
