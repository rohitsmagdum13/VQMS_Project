"""VQMS Pydantic data models.

Re-exports all public models for convenient imports.
Usage: from src.models import EmailMessage, VendorMatch, etc.
"""

from src.models.budget import Budget
from src.models.communication import DraftEmailPackage, ValidationReport
from src.models.email import EmailAttachment, EmailMessage, ParsedEmailPayload
from src.models.memory import EmbeddingRecord, EpisodicMemory, VendorProfileCache
from src.models.messages import AgentMessage, ToolCall
from src.models.ticket import RoutingDecision, TicketLink, TicketRecord
from src.models.vendor import VendorMatch, VendorProfile, VendorTier
from src.models.workflow import AnalysisResult, CaseExecution, WorkflowState

__all__ = [
    # messages.py
    "AgentMessage",
    "AnalysisResult",
    # budget.py
    "Budget",
    "CaseExecution",
    # communication.py
    "DraftEmailPackage",
    # email.py
    "EmailAttachment",
    "EmailMessage",
    "EmbeddingRecord",
    # memory.py
    "EpisodicMemory",
    "ParsedEmailPayload",
    "RoutingDecision",
    "TicketLink",
    # ticket.py
    "TicketRecord",
    "ToolCall",
    "ValidationReport",
    "VendorMatch",
    "VendorProfile",
    "VendorProfileCache",
    # vendor.py
    "VendorTier",
    # workflow.py
    "WorkflowState",
]
