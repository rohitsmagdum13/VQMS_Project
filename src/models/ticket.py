"""Module: models/ticket.py

Pydantic models for ticket data in VQMS.

These models define the shape of ServiceNow ticket information
used across the pipeline — from ticket creation through updates
to closure and reopening.

Corresponds to the workflow schema (ticket_link, routing_decision)
and the Ticket Operations Service in the architecture document.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TicketRecord(BaseModel):
    """A ServiceNow ticket created or updated by VQMS.

    Represents the current state of a ticket in ServiceNow.
    The Ticket Operations Service creates and updates these
    records through the ServiceNow REST API.
    """

    ticket_id: str = Field(
        description="ServiceNow ticket number (e.g., 'INC0123456')"
    )
    ticket_url: str = Field(
        description="Full URL to the ticket in ServiceNow"
    )
    vendor_id: str = Field(description="Salesforce Account ID of the vendor")
    title: str = Field(description="Ticket short description / title")
    description: str = Field(description="Ticket detailed description")
    assigned_to: str | None = Field(
        default=None,
        description="Individual assignee (may be unassigned initially)",
    )
    assignment_group: str | None = Field(
        default=None,
        description="ServiceNow assignment group for this ticket",
    )
    status: str = Field(
        description="Ticket status: Open, In Progress, Resolved, Closed, Reopened"
    )
    priority: str = Field(
        description="Ticket priority: Critical, High, Medium, Low"
    )
    created_at: datetime = Field(description="When the ticket was created")
    updated_at: datetime = Field(description="When the ticket was last updated")
    resolved_at: datetime | None = Field(
        default=None,
        description="When the ticket was resolved (None if still open)",
    )


class TicketLink(BaseModel):
    """Association between a VQMS case and a ServiceNow ticket.

    A case can have multiple tickets linked (e.g., when a vendor
    query touches multiple issues), but only one is marked primary.
    Stored in the workflow.ticket_link table.
    """

    case_id: int = Field(description="case_execution.id in PostgreSQL")
    ticket_id: str = Field(description="ServiceNow ticket number")
    ticket_url: str = Field(description="Full URL to the ticket")
    linked_at: datetime = Field(description="When this link was created")
    is_primary: bool = Field(
        default=True,
        description="Only one ticket per case should be primary. "
        "The primary ticket is used in vendor communications.",
    )


class RoutingDecision(BaseModel):
    """The routing decision made by the Orchestration Agent.

    Determines how a case should be handled: fully automated,
    sent for human review, escalated, ticket reopened, or new
    ticket created. Stored in workflow.routing_decision table.
    """

    decision_type: str = Field(
        description="Routing action: auto | human_review | escalate | reopen | new_ticket"
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Agent's confidence in this decision (0.0 to 1.0)",
    )
    reason: str = Field(
        description="Human-readable explanation of why this decision was made"
    )
    decided_at: datetime = Field(
        description="When the routing decision was made"
    )
