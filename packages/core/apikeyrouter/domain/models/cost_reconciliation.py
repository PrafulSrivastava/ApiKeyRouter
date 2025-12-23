"""CostReconciliation model for tracking estimated vs actual costs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CostReconciliation(BaseModel):
    """Represents reconciliation between estimated and actual costs.

    CostReconciliation tracks the difference between estimated and actual costs
    for a request, enabling the system to learn and improve cost estimation
    accuracy over time.

    Example:
        ```python
        reconciliation = CostReconciliation(
            request_id="req-123",
            estimated_cost=Decimal("0.015"),
            actual_cost=Decimal("0.014"),
            provider_id="openai",
            model="gpt-4",
            reconciled_at=datetime.utcnow()
        )
        assert reconciliation.error_amount == Decimal("-0.001")
        assert reconciliation.error_percentage == -6.67
        ```
    """

    request_id: str = Field(
        ...,
        description="Unique request identifier",
        min_length=1,
        max_length=255,
    )
    estimated_cost: Decimal = Field(
        ...,
        description="Estimated cost amount in USD",
        ge=0,
    )
    actual_cost: Decimal = Field(
        ...,
        description="Actual cost amount in USD from provider response",
        ge=0,
    )
    error_amount: Decimal = Field(
        default=Decimal("0.00"),
        description="Error amount (actual_cost - estimated_cost), calculated automatically",
    )
    error_percentage: float = Field(
        default=0.0,
        description="Error percentage ((error_amount / estimated_cost) * 100), calculated automatically",
    )
    provider_id: str | None = Field(
        default=None,
        description="Provider identifier used for the request",
        max_length=255,
    )
    model: str | None = Field(
        default=None,
        description="Model identifier used for the request",
        max_length=255,
    )
    key_id: str | None = Field(
        default=None,
        description="API key identifier used for the request",
        max_length=255,
    )
    reconciled_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when reconciliation was performed",
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, v: str) -> str:
        """Validate request ID is non-empty."""
        if not v or not v.strip():
            raise ValueError("Request ID cannot be empty")
        return v.strip()

    @model_validator(mode="after")
    def calculate_errors(self) -> CostReconciliation:
        """Calculate error_amount and error_percentage from estimated and actual costs.

        This validator ensures error calculations are always correct and up-to-date.
        """
        # Calculate error amount (actual - estimated)
        error_amount = self.actual_cost - self.estimated_cost

        # Calculate error percentage
        if self.estimated_cost > 0:
            error_percentage = float((error_amount / self.estimated_cost) * 100)
        else:
            # If estimated cost is 0, error percentage is undefined
            # Set to 0 if actual is also 0, otherwise 100% error
            error_percentage = 0.0 if self.actual_cost == 0 else 100.0

        # Use object.__setattr__ to bypass Pydantic validation and avoid recursion
        object.__setattr__(self, "error_amount", error_amount)
        object.__setattr__(self, "error_percentage", error_percentage)

        return self

    def __repr__(self) -> str:
        """String representation of cost reconciliation."""
        return (
            f"CostReconciliation(request_id={self.request_id!r}, "
            f"estimated={self.estimated_cost}, actual={self.actual_cost}, "
            f"error={self.error_amount} ({self.error_percentage:.2f}%))"
        )
