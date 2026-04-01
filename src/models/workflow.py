"""Module: models/workflow.py

Pydantic models for workflow execution state in VQMS.

These models track the lifecycle of a single vendor email
as it moves through the pipeline — from intake through
analysis, routing, drafting, validation, and sending.

Corresponds to the workflow schema (case_execution) and
the LangGraph state machine in the architecture document.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from src.models.ticket import RoutingDecision
from src.models.vendor import VendorMatch


class WorkflowState(StrEnum):
    """State of a case in the VQMS workflow pipeline.

    These states map 1:1 to the LangGraph state machine nodes.
    A case progresses through these states sequentially, though
    it can skip states (e.g., escalation skips drafting).
    """

    PENDING = "pending"          # Email received, awaiting processing
    ANALYZING = "analyzing"      # Email Analysis Agent is running
    ROUTING = "routing"          # Orchestration Agent deciding next step
    DRAFTING = "drafting"        # Communication Drafting Agent writing response
    VALIDATING = "validating"    # Quality Gate checking the draft
    SENDING = "sending"          # Response email being sent to vendor
    CLOSED = "closed"            # Case resolved and ticket closed
    REOPENED = "reopened"        # Vendor replied after closure — reprocessing


class AnalysisResult(BaseModel):
    """Output from the Email Analysis Agent.

    Contains the extracted intent, entities, urgency, and sentiment
    from the vendor's email. This drives all downstream routing
    and response decisions.
    """

    intent: str = Field(
        description="What the vendor is asking for "
        "(e.g., 'invoice_inquiry', 'payment_status', 'complaint')"
    )
    entities: dict = Field(
        description="Extracted entities from the email body. "
        "Keys: invoice_ids (list), dates (list), amounts (list), "
        "vendor_ids (list), other (dict)",
    )
    urgency: str = Field(
        description="Urgency level: low | medium | high | critical"
    )
    sentiment: str = Field(
        description="Sender sentiment: positive | neutral | negative"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Agent's confidence in this analysis (0.0 to 1.0)",
    )
    summary: str = Field(
        description="2-3 sentence summary of the email for human reviewers"
    )


class CaseExecution(BaseModel):
    """Complete execution record for one vendor email case.

    This is the central tracking object for the entire VQMS pipeline.
    Each incoming email creates one CaseExecution, which accumulates
    results from each stage. Stored in workflow.case_execution table.
    """

    # Database identity
    id: int | None = Field(
        default=None,
        description="Database primary key (None until persisted)",
    )

    # Tracing
    correlation_id: str = Field(
        description="Unique trace ID that follows this case through "
        "every service, queue, and log entry"
    )
    message_id: str = Field(
        description="Exchange Online message ID that started this case"
    )

    # Current state in the pipeline
    workflow_state: WorkflowState = Field(
        default=WorkflowState.PENDING,
        description="Current position in the workflow state machine",
    )

    # Results from each pipeline stage — populated as the case progresses
    analysis_result: AnalysisResult | None = Field(
        default=None,
        description="Output from Email Analysis Agent (Phase 5)",
    )
    vendor_match: VendorMatch | None = Field(
        default=None,
        description="Output from Vendor Resolution Service (Phase 6)",
    )
    routing_decision: RoutingDecision | None = Field(
        default=None,
        description="Output from Orchestration Agent (Phase 4)",
    )
    draft_package: dict | None = Field(
        default=None,
        description="Output from Communication Drafting Agent (Phase 7). "
        "Stored as dict to avoid circular import with communication.py.",
    )
    validation_report: dict | None = Field(
        default=None,
        description="Output from Quality Gate (Phase 7). "
        "Stored as dict to avoid circular import with communication.py.",
    )

    # Ticket tracking
    ticket_id: str | None = Field(
        default=None,
        description="ServiceNow ticket ID linked to this case",
    )
    assigned_group: str | None = Field(
        default=None,
        description="ServiceNow assignment group",
    )

    # Escalation and review tracking
    escalation_count: int = Field(
        default=0,
        description="Number of times this case has been escalated",
    )
    is_human_review: bool = Field(
        default=False,
        description="True if this case was routed to human review",
    )

    # Timestamps
    closed_at: datetime | None = Field(
        default=None,
        description="When the case was resolved (None if still open)",
    )
    created_at: datetime | None = Field(
        default=None,
        description="When the case record was created in the database",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="When the case record was last updated",
    )
