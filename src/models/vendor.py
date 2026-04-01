"""Module: models/vendor.py

Pydantic models for vendor data in VQMS.

These models define the shape of vendor information as it flows
through the pipeline — from Salesforce lookup to agent decisions.

Corresponds to the memory schema (vendor_profile_cache) and
the Vendor Resolution Service in the architecture document.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class VendorTier(StrEnum):
    """Vendor importance level — determines SLA targets and escalation speed.

    Tier is pulled from Salesforce during vendor resolution.
    Higher tiers get faster SLA targets and earlier escalations.
    """

    PLATINUM = "platinum"  # Most important — fastest SLA, immediate escalation
    GOLD = "gold"          # High priority — shorter SLA than standard
    SILVER = "silver"      # Medium priority
    STANDARD = "standard"  # Default tier for unclassified vendors


class VendorMatch(BaseModel):
    """Result of looking up a vendor in Salesforce.

    The Vendor Resolution Service produces this after trying
    to match an email sender against Salesforce CRM records.
    Uses a three-step fallback: exact email, vendor ID in body,
    then fuzzy name similarity.
    """

    # Vendor identity
    vendor_id: str = Field(description="Salesforce Account ID")
    vendor_name: str = Field(description="Company name from Salesforce")
    vendor_tier: VendorTier = Field(
        default=VendorTier.STANDARD,
        description="SLA tier — drives response time targets",
    )

    # How we found this vendor
    match_method: str = Field(
        description="How the vendor was matched: "
        "EMAIL_EXACT, VENDOR_ID_BODY, NAME_SIMILARITY, or UNRESOLVED",
    )
    match_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="How confident we are in this match (0.0 to 1.0)",
    )

    # Flags for routing decisions
    risk_flags: list[str] = Field(
        default_factory=list,
        description="Any risk flags from Salesforce (e.g., 'payment_overdue')",
    )


class VendorProfile(BaseModel):
    """Cached vendor profile for quick lookups.

    Stored in both Redis (hot cache, 1-hour TTL) and PostgreSQL
    (vendor_profile_cache table) to avoid repeated Salesforce calls
    for the same vendor within a short window.
    """

    vendor_id: str = Field(description="Salesforce Account ID")
    vendor_name: str = Field(description="Company name from Salesforce")
    tier: VendorTier = Field(
        default=VendorTier.STANDARD,
        description="SLA tier from Salesforce",
    )
    sla_hours: int = Field(
        description="SLA target in hours for this vendor's tier"
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="Risk flags from Salesforce",
    )
    last_seen: datetime | None = Field(
        default=None,
        description="When we last received an email from this vendor",
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
