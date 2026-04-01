"""Module: models/messages.py

Pydantic models for inter-agent communication in VQMS.

These models define the message envelope that agents use to
communicate through the LangGraph state machine. Every message
includes a correlation_id for tracing and optional cost/token
metadata for budget tracking.

Corresponds to Section 2 (Multi-layer Architecture) of the
coding standards — message envelope contract.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Record of a tool invocation during agent execution.

    When an agent calls a tool (e.g., Salesforce lookup, S3 upload),
    the invocation details are captured here for audit and debugging.
    """

    tool_name: str = Field(
        description="Name of the tool that was called "
        "(e.g., 'salesforce_lookup', 's3_upload')"
    )
    tool_input: dict = Field(
        description="Input parameters passed to the tool"
    )
    tool_output: dict | None = Field(
        default=None,
        description="Output returned by the tool (None if tool hasn't completed)",
    )
    executed_at: datetime | None = Field(
        default=None,
        description="When the tool was executed",
    )
    duration_ms: int | None = Field(
        default=None,
        description="How long the tool took to execute (milliseconds)",
    )


class AgentMessage(BaseModel):
    """Message passed between agents in the LangGraph pipeline.

    This is the standard envelope for all inter-agent communication.
    Every message carries a correlation_id so we can trace a vendor
    email through every agent and service it touches.
    """

    # Tracing — required on every message
    correlation_id: str = Field(
        description="Trace ID that follows this email through the pipeline"
    )

    # Routing — who sent this and who should receive it
    sender_agent: str = Field(
        description="Agent that produced this message: "
        "email_analysis | communication_drafting | orchestration"
    )
    receiver_agent: str | None = Field(
        default=None,
        description="Target agent (None if the message is for an external handler "
        "like SQS or EventBridge)",
    )

    # Content
    message_type: str = Field(
        description="Type of message: analysis | routing_decision | draft | request"
    )
    payload: dict = Field(
        description="Message content — structure varies by message_type"
    )

    # Tool invocations during this agent step
    tool_calls: list[ToolCall] = Field(
        default_factory=list,
        description="Tools the agent called while producing this message",
    )

    # Cost tracking — populated by Bedrock Integration Service
    tokens_used: int | None = Field(
        default=None,
        description="Total tokens consumed (input + output) for this message",
    )
    cost_usd: float | None = Field(
        default=None,
        description="Cost in USD for the LLM call that produced this message",
    )

    # Timestamp
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this message was created",
    )
