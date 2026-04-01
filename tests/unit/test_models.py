"""Tests for VQMS Pydantic models.

Verifies that all data models validate correctly, enforce
constraints, and provide sensible defaults. Each model gets
its own test class for organization.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.models.budget import Budget
from src.models.communication import DraftEmailPackage, ValidationReport
from src.models.email import EmailAttachment, EmailMessage, ParsedEmailPayload
from src.models.memory import EmbeddingRecord, EpisodicMemory, VendorProfileCache
from src.models.messages import AgentMessage, ToolCall
from src.models.ticket import RoutingDecision, TicketLink, TicketRecord
from src.models.vendor import VendorMatch, VendorProfile, VendorTier
from src.models.workflow import AnalysisResult, CaseExecution, WorkflowState

# ============================================================
# Email Models
# ============================================================


class TestEmailAttachment:
    """Test the EmailAttachment model."""

    def test_valid_attachment(self) -> None:
        """An attachment with all required fields should create successfully."""
        attachment = EmailAttachment(
            filename="report.pdf",
            mime_type="application/pdf",
            file_size_bytes=1024,
        )
        assert attachment.filename == "report.pdf"
        assert attachment.s3_path is None  # Default before S3 upload

    def test_attachment_with_s3_path(self) -> None:
        """After S3 upload, the s3_path should be populated."""
        attachment = EmailAttachment(
            filename="report.pdf",
            mime_type="application/pdf",
            file_size_bytes=1024,
            s3_path="msg-123/report.pdf",
        )
        assert attachment.s3_path == "msg-123/report.pdf"


class TestEmailMessage:
    """Test the EmailMessage model."""

    def test_valid_email_message(self, sample_email_message: EmailMessage) -> None:
        """A valid email message should have all expected fields."""
        assert sample_email_message.message_id == "AAMkAGI2TG93AAA="
        assert sample_email_message.sender_email == "john.doe@acme-corp.com"
        assert sample_email_message.attachments == []

    def test_email_defaults(self) -> None:
        """Optional fields should default correctly."""
        email = EmailMessage(
            message_id="msg-001",
            correlation_id="corr-001",
            sender_email="test@example.com",
            subject="Test",
            body_plain="Hello",
            received_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        assert email.sender_name is None
        assert email.body_html is None
        assert email.attachments == []
        assert email.s3_raw_path is None


class TestParsedEmailPayload:
    """Test the ParsedEmailPayload model."""

    def test_valid_parsed_payload(self, sample_parsed_email: ParsedEmailPayload) -> None:
        """A parsed payload should have s3_raw_path populated."""
        assert sample_parsed_email.s3_raw_path.endswith("raw.eml")
        assert sample_parsed_email.is_duplicate is False

    def test_duplicate_flag(self) -> None:
        """Duplicate emails should be flagged."""
        payload = ParsedEmailPayload(
            message_id="msg-dup",
            correlation_id="corr-dup",
            sender_email="test@example.com",
            subject="Test",
            body_plain="Hello",
            received_at=datetime(2024, 1, 1, tzinfo=UTC),
            s3_raw_path="2024/01/01/msg-dup/raw.eml",
            is_duplicate=True,
        )
        assert payload.is_duplicate is True


# ============================================================
# Vendor Models
# ============================================================


class TestVendorTier:
    """Test the VendorTier enum."""

    def test_all_tiers_exist(self) -> None:
        """All four vendor tiers should be defined."""
        assert VendorTier.PLATINUM == "platinum"
        assert VendorTier.GOLD == "gold"
        assert VendorTier.SILVER == "silver"
        assert VendorTier.STANDARD == "standard"

    def test_tier_count(self) -> None:
        """There should be exactly 4 tiers."""
        assert len(VendorTier) == 4


class TestVendorMatch:
    """Test the VendorMatch model."""

    def test_valid_vendor_match(self, sample_vendor_match: VendorMatch) -> None:
        """A valid vendor match should have all expected fields."""
        assert sample_vendor_match.vendor_id == "SF-ACC-001"
        assert sample_vendor_match.vendor_tier == VendorTier.GOLD
        assert sample_vendor_match.match_confidence == 0.95

    def test_default_tier_is_standard(self) -> None:
        """When no tier is specified, default should be STANDARD."""
        match = VendorMatch(
            vendor_id="SF-ACC-002",
            vendor_name="Unknown Corp",
            match_method="NAME_SIMILARITY",
            match_confidence=0.60,
        )
        assert match.vendor_tier == VendorTier.STANDARD

    def test_confidence_must_be_between_zero_and_one(self) -> None:
        """Confidence scores outside 0.0-1.0 should raise validation error."""
        with pytest.raises(ValueError):
            VendorMatch(
                vendor_id="SF-ACC-003",
                vendor_name="Bad Corp",
                match_method="EMAIL_EXACT",
                match_confidence=1.5,
            )

    def test_confidence_cannot_be_negative(self) -> None:
        """Negative confidence scores should raise validation error."""
        with pytest.raises(ValueError):
            VendorMatch(
                vendor_id="SF-ACC-004",
                vendor_name="Bad Corp",
                match_method="EMAIL_EXACT",
                match_confidence=-0.1,
            )

    def test_risk_flags_default_to_empty_list(self) -> None:
        """Risk flags should default to an empty list, not None."""
        match = VendorMatch(
            vendor_id="SF-ACC-005",
            vendor_name="Safe Corp",
            match_method="EMAIL_EXACT",
            match_confidence=0.90,
        )
        assert match.risk_flags == []
        assert isinstance(match.risk_flags, list)


class TestVendorProfile:
    """Test the VendorProfile model."""

    def test_valid_profile(self, sample_vendor_profile: VendorProfile) -> None:
        """A valid profile should have all expected fields."""
        assert sample_vendor_profile.sla_hours == 12
        assert sample_vendor_profile.interaction_count == 15

    def test_profile_defaults(self) -> None:
        """Optional fields should default correctly."""
        profile = VendorProfile(
            vendor_id="SF-ACC-010",
            vendor_name="New Corp",
            sla_hours=24,
        )
        assert profile.tier == VendorTier.STANDARD
        assert profile.risk_flags == []
        assert profile.last_seen is None
        assert profile.interaction_count == 0


# ============================================================
# Ticket Models
# ============================================================


class TestTicketRecord:
    """Test the TicketRecord model."""

    def test_valid_ticket(self) -> None:
        """A valid ticket should have all required fields."""
        now = datetime.now(tz=UTC)
        ticket = TicketRecord(
            ticket_id="INC0012345",
            ticket_url="https://company.service-now.com/nav_to.do?uri=incident.do?sys_id=abc",
            vendor_id="SF-ACC-001",
            title="Invoice inquiry from Acme Corp",
            description="Vendor is asking about invoice INV-2024-001",
            status="Open",
            priority="Medium",
            created_at=now,
            updated_at=now,
        )
        assert ticket.ticket_id == "INC0012345"
        assert ticket.resolved_at is None


class TestTicketLink:
    """Test the TicketLink model."""

    def test_default_is_primary(self) -> None:
        """New ticket links should default to primary."""
        now = datetime.now(tz=UTC)
        link = TicketLink(
            case_id=1,
            ticket_id="INC0012345",
            ticket_url="https://example.com",
            linked_at=now,
        )
        assert link.is_primary is True


class TestRoutingDecision:
    """Test the RoutingDecision model."""

    def test_valid_routing_decision(self) -> None:
        """A routing decision should have type, confidence, and reason."""
        now = datetime.now(tz=UTC)
        decision = RoutingDecision(
            decision_type="auto",
            confidence_score=0.92,
            reason="High confidence analysis with known vendor",
            decided_at=now,
        )
        assert decision.decision_type == "auto"
        assert decision.confidence_score == 0.92

    def test_confidence_validation(self) -> None:
        """Confidence must be between 0.0 and 1.0."""
        with pytest.raises(ValueError):
            RoutingDecision(
                decision_type="auto",
                confidence_score=2.0,
                reason="Invalid",
                decided_at=datetime.now(tz=UTC),
            )


# ============================================================
# Workflow Models
# ============================================================


class TestWorkflowState:
    """Test the WorkflowState enum."""

    def test_all_states_exist(self) -> None:
        """All 8 workflow states should be defined."""
        expected = {"pending", "analyzing", "routing", "drafting",
                    "validating", "sending", "closed", "reopened"}
        actual = {state.value for state in WorkflowState}
        assert actual == expected

    def test_state_count(self) -> None:
        """There should be exactly 8 states."""
        assert len(WorkflowState) == 8


class TestAnalysisResult:
    """Test the AnalysisResult model."""

    def test_valid_analysis(self) -> None:
        """A valid analysis result should have all required fields."""
        result = AnalysisResult(
            intent="invoice_inquiry",
            entities={"invoice_ids": ["INV-2024-001"], "amounts": [15000]},
            urgency="medium",
            sentiment="neutral",
            confidence=0.88,
            summary="Vendor is asking about the payment status of invoice INV-2024-001.",
        )
        assert result.intent == "invoice_inquiry"
        assert result.confidence == 0.88


class TestCaseExecution:
    """Test the CaseExecution model."""

    def test_new_case_defaults(self) -> None:
        """A new case should start with sensible defaults."""
        case = CaseExecution(
            correlation_id="vqms-test-001",
            message_id="msg-001",
        )
        assert case.id is None
        assert case.workflow_state == WorkflowState.PENDING
        assert case.analysis_result is None
        assert case.vendor_match is None
        assert case.escalation_count == 0
        assert case.is_human_review is False


# ============================================================
# Communication Models
# ============================================================


class TestDraftEmailPackage:
    """Test the DraftEmailPackage model."""

    def test_valid_draft(self) -> None:
        """A valid draft should have all required fields."""
        now = datetime.now(tz=UTC)
        draft = DraftEmailPackage(
            ticket_id="INC0012345",
            recipient_email="john.doe@acme-corp.com",
            subject="Re: Invoice #INV-2024-001 Payment Status",
            body_html="<p>Dear John, we have received your inquiry...</p>",
            body_plain="Dear John, we have received your inquiry...",
            sla_promise="within 24 hours",
            includes_ticket_number=True,
            is_template_compliant=True,
            generated_at=now,
        )
        assert draft.includes_ticket_number is True


class TestValidationReport:
    """Test the ValidationReport model."""

    def test_all_checks_pass(self) -> None:
        """When all checks pass, overall_valid should be True."""
        now = datetime.now(tz=UTC)
        report = ValidationReport(
            ticket_number_valid=True,
            ticket_number_present=True,
            sla_wording_valid=True,
            pii_detected=False,
            template_compliant=True,
            overall_valid=True,
            validated_at=now,
        )
        assert report.overall_valid is True
        assert report.pii_details == []

    def test_pii_detected_fails_validation(self) -> None:
        """When PII is detected, the report should reflect it."""
        now = datetime.now(tz=UTC)
        report = ValidationReport(
            ticket_number_valid=True,
            ticket_number_present=True,
            sla_wording_valid=True,
            pii_detected=True,
            pii_details=["SSN", "credit_card"],
            template_compliant=True,
            overall_valid=False,
            validated_at=now,
        )
        assert report.pii_detected is True
        assert len(report.pii_details) == 2
        assert report.overall_valid is False


# ============================================================
# Memory Models
# ============================================================


class TestEpisodicMemory:
    """Test the EpisodicMemory model."""

    def test_valid_episodic_memory(self) -> None:
        """An episodic memory should capture a single event."""
        now = datetime.now(tz=UTC)
        memory = EpisodicMemory(
            correlation_id="vqms-test-001",
            vendor_id="SF-ACC-001",
            event_type="email_received",
            event_data={"subject": "Invoice inquiry", "sender": "john@acme.com"},
            timestamp=now,
        )
        assert memory.event_type == "email_received"


class TestVendorProfileCache:
    """Test the VendorProfileCache model."""

    def test_valid_cache_entry(self) -> None:
        """A cache entry should have all required fields."""
        now = datetime.now(tz=UTC)
        cache = VendorProfileCache(
            vendor_id="SF-ACC-001",
            vendor_name="Acme Corp",
            tier=VendorTier.GOLD,
            sla_hours=12,
            last_seen=now,
            cached_at=now,
        )
        assert cache.tier == VendorTier.GOLD
        assert cache.interaction_count == 0


class TestEmbeddingRecord:
    """Test the EmbeddingRecord model."""

    def test_valid_embedding(self) -> None:
        """An embedding should store a text chunk and its vector."""
        embedding = EmbeddingRecord(
            correlation_id="vqms-test-001",
            text_chunk="Vendor is asking about invoice payment.",
            embedding=[0.1] * 1536,  # Simplified 1536-dim vector
        )
        assert len(embedding.embedding) == 1536
        assert embedding.vendor_id is None  # Optional


# ============================================================
# Budget Model
# ============================================================


class TestBudget:
    """Test the Budget dataclass."""

    def test_default_budget(self) -> None:
        """A default budget should have standard limits."""
        budget = Budget()
        assert budget.max_tokens_in == 8000
        assert budget.max_tokens_out == 4096
        assert budget.currency_limit_usd == 0.50
        assert budget.is_exhausted() is False

    def test_budget_exhausted_by_tokens_in(self) -> None:
        """Budget should be exhausted when input tokens hit the limit."""
        budget = Budget(current_tokens_in=8000)
        assert budget.is_exhausted() is True

    def test_budget_exhausted_by_tokens_out(self) -> None:
        """Budget should be exhausted when output tokens hit the limit."""
        budget = Budget(current_tokens_out=4096)
        assert budget.is_exhausted() is True

    def test_budget_exhausted_by_cost(self) -> None:
        """Budget should be exhausted when cost hits the limit."""
        budget = Budget(current_cost_usd=0.50)
        assert budget.is_exhausted() is True

    def test_budget_not_exhausted_below_limits(self) -> None:
        """Budget should NOT be exhausted when all values are below limits."""
        budget = Budget(
            current_tokens_in=4000,
            current_tokens_out=2000,
            current_cost_usd=0.25,
        )
        assert budget.is_exhausted() is False

    def test_remaining_calculations(self) -> None:
        """Remaining budget should be calculated correctly."""
        budget = Budget(
            current_tokens_in=3000,
            current_tokens_out=1000,
            current_cost_usd=0.20,
        )
        assert budget.remaining_tokens_in() == 5000
        assert budget.remaining_tokens_out() == 3096
        assert abs(budget.remaining_cost_usd() - 0.30) < 0.001

    def test_remaining_never_negative(self) -> None:
        """Remaining should be 0, never negative, when over budget."""
        budget = Budget(current_tokens_in=10000)  # Over the 8000 limit
        assert budget.remaining_tokens_in() == 0


# ============================================================
# Message Models
# ============================================================


class TestToolCall:
    """Test the ToolCall model."""

    def test_valid_tool_call(self) -> None:
        """A tool call should capture name, input, and output."""
        tool = ToolCall(
            tool_name="salesforce_lookup",
            tool_input={"email": "john@acme.com"},
            tool_output={"vendor_id": "SF-ACC-001"},
            duration_ms=250,
        )
        assert tool.tool_name == "salesforce_lookup"


class TestAgentMessage:
    """Test the AgentMessage model."""

    def test_valid_agent_message(self) -> None:
        """An agent message should have correlation_id and payload."""
        msg = AgentMessage(
            correlation_id="vqms-test-001",
            sender_agent="email_analysis",
            message_type="analysis",
            payload={"intent": "invoice_inquiry"},
        )
        assert msg.sender_agent == "email_analysis"
        assert msg.receiver_agent is None
        assert msg.tool_calls == []
        assert msg.tokens_used is None
