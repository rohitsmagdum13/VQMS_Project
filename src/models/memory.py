"""Module: models/memory.py

Pydantic models for memory and context management in VQMS.

These models define the shape of historical data stored for
vendor interactions, episodic events, and semantic embeddings.
Used by the Memory & Context Service to provide agents with
relevant history when processing new emails.

Corresponds to the memory schema in the architecture document.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.vendor import VendorTier


class EpisodicMemory(BaseModel):
    """A single event in the history of a vendor interaction.

    Episodic memories are immutable records of things that happened
    during case processing. They help agents understand the history
    of a vendor relationship and make better decisions.

    Stored in memory.episodic_memory table.
    """

    correlation_id: str = Field(
        description="Links back to the case_execution that produced this event"
    )
    vendor_id: str = Field(
        description="Salesforce Account ID of the vendor involved"
    )
    event_type: str = Field(
        description="Type of event: email_received | ticket_created | "
        "sla_warning | escalation | resolution | reopened"
    )
    event_data: dict = Field(
        description="Full event payload — varies by event_type"
    )
    timestamp: datetime = Field(
        description="When this event occurred (UTC)"
    )


class VendorProfileCache(BaseModel):
    """Hot cache entry for vendor data from Salesforce.

    Cached in both Redis (1-hour TTL for fast lookups) and
    PostgreSQL (memory.vendor_profile_cache for persistence).
    Avoids repeated Salesforce API calls for the same vendor
    within a short time window.
    """

    vendor_id: str = Field(description="Salesforce Account ID")
    vendor_name: str = Field(description="Company name from Salesforce")
    tier: VendorTier = Field(description="SLA tier from Salesforce")
    sla_hours: int = Field(
        description="SLA target in hours based on vendor tier"
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="Risk flags from Salesforce (e.g., 'payment_overdue')",
    )
    last_seen: datetime = Field(
        description="When we last received an email from this vendor"
    )
    last_ticket_id: str | None = Field(
        default=None,
        description="Most recent ServiceNow ticket for this vendor",
    )
    interaction_count: int = Field(
        default=0,
        description="Total number of emails received from this vendor",
    )
    avg_resolution_time_hours: float | None = Field(
        default=None,
        description="Average time to resolve this vendor's tickets (hours)",
    )
    cached_at: datetime = Field(
        description="When this cache entry was created or last refreshed"
    )


class EmbeddingRecord(BaseModel):
    """A semantic embedding for RAG (Retrieval-Augmented Generation).

    Text chunks from emails, tickets, and knowledge base documents
    are embedded using Amazon Bedrock and stored in PostgreSQL with
    pgvector for semantic similarity search.

    Stored in memory.embedding_index table.
    """

    id: int | None = Field(
        default=None,
        description="Database primary key (None until persisted)",
    )
    correlation_id: str = Field(
        description="Links to the case that produced this embedding"
    )
    vendor_id: str | None = Field(
        default=None,
        description="Vendor associated with this text (None for knowledge base docs)",
    )
    text_chunk: str = Field(
        description="The text that was embedded — chunked by semantic boundaries"
    )
    embedding: list[float] = Field(
        description="1536-dimensional vector from Bedrock embedding model"
    )
    created_at: datetime | None = Field(
        default=None,
        description="When this embedding was created",
    )
