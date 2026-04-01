"""Module: models/budget.py

Budget dataclass for token and cost limits in VQMS.

Each agent invocation gets a budget that caps how many tokens
it can consume and how much it can cost. The orchestration layer
checks the budget before and after each LLM call to prevent
runaway costs.

Uses a dataclass instead of Pydantic because Budget is a simple
internal tracking object, not a serialized data contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Default limits from environment configuration
# These match AGENT_BUDGET_* values in .env.copy
DEFAULT_MAX_TOKENS_IN = 8000
DEFAULT_MAX_TOKENS_OUT = 4096
DEFAULT_CURRENCY_LIMIT_USD = 0.50


@dataclass
class Budget:
    """Token and cost limits for a single agent invocation.

    The orchestration layer creates a Budget for each LLM call
    and passes it through the pipeline. After each call, the
    Bedrock Integration Service updates the current_* fields.

    When is_exhausted() returns True, the orchestrator must stop
    the current agent and either return a partial result or
    escalate to human review.
    """

    # Limits — set once at creation
    max_tokens_in: int = field(default=DEFAULT_MAX_TOKENS_IN)
    max_tokens_out: int = field(default=DEFAULT_MAX_TOKENS_OUT)
    currency_limit_usd: float = field(default=DEFAULT_CURRENCY_LIMIT_USD)

    # Current usage — updated after each LLM call
    current_tokens_in: int = field(default=0)
    current_tokens_out: int = field(default=0)
    current_cost_usd: float = field(default=0.0)

    def is_exhausted(self) -> bool:
        """Check if any budget limit has been reached.

        Returns True if the agent has consumed its entire budget
        for input tokens, output tokens, OR cost. Any one limit
        being hit is enough to stop the agent.
        """
        return (
            self.current_tokens_in >= self.max_tokens_in
            or self.current_tokens_out >= self.max_tokens_out
            or self.current_cost_usd >= self.currency_limit_usd
        )

    def remaining_tokens_in(self) -> int:
        """How many input tokens are left in the budget."""
        return max(0, self.max_tokens_in - self.current_tokens_in)

    def remaining_tokens_out(self) -> int:
        """How many output tokens are left in the budget."""
        return max(0, self.max_tokens_out - self.current_tokens_out)

    def remaining_cost_usd(self) -> float:
        """How much cost budget is left (USD)."""
        return max(0.0, self.currency_limit_usd - self.current_cost_usd)
