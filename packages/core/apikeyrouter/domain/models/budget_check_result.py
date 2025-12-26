"""BudgetCheckResult model for budget validation."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class BudgetCheckResult(BaseModel):
    """Result of a budget check before request execution.

    BudgetCheckResult indicates whether a request is allowed based on budget
    constraints and provides information about remaining budget and any violations.

    Example:
        ```python
        result = BudgetCheckResult(
            allowed=True,
            remaining_budget=Decimal("50.00"),
            would_exceed=False,
            violated_budgets=[]
        )
        if not result.allowed:
            # Reject request or handle violation
            ...
        ```
    """

    allowed: bool = Field(
        ...,
        description="Whether the request is allowed based on budget constraints",
    )
    remaining_budget: Decimal = Field(
        ...,
        description="Remaining budget amount (minimum across all applicable budgets)",
        ge=0,
    )
    would_exceed: bool = Field(
        ...,
        description="Whether the request would exceed any budget",
    )
    budget_id: str | None = Field(
        default=None,
        description="Primary budget ID that was checked (if single budget)",
        max_length=255,
    )
    violated_budgets: list[str] = Field(
        default_factory=list,
        description="List of budget IDs that would be exceeded by this request",
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    def __repr__(self) -> str:
        """String representation of budget check result."""
        return (
            f"BudgetCheckResult(allowed={self.allowed}, "
            f"remaining_budget={self.remaining_budget}, "
            f"would_exceed={self.would_exceed}, "
            f"violated_budgets={len(self.violated_budgets)})"
        )

