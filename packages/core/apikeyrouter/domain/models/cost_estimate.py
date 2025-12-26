"""CostEstimate model for cost estimation."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CostEstimate(BaseModel):
    """Cost estimate for a request.

    CostEstimate represents the estimated cost of a request before execution.
    It includes the estimated amount, confidence level, and method used for
    estimation.

    Example:
        ```python
        estimate = CostEstimate(
            amount=Decimal("0.0025"),
            currency="USD",
            confidence=0.8,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50
        )
        ```
    """

    amount: Decimal = Field(
        ...,
        description="Estimated cost amount in USD",
        ge=0,
    )
    currency: str = Field(
        default="USD",
        description="Currency code (default: USD)",
        min_length=3,
        max_length=3,
    )
    confidence: float = Field(
        ...,
        description="Confidence level in estimate (0.0 to 1.0)",
        ge=0.0,
        le=1.0,
    )
    estimation_method: str = Field(
        ...,
        description="Method used for estimation (e.g., 'token_count_approximation', 'exact_token_count')",
        min_length=1,
    )
    input_tokens_estimate: int = Field(
        ...,
        description="Estimated number of input tokens",
        ge=0,
    )
    output_tokens_estimate: int = Field(
        ...,
        description="Estimated number of output tokens",
        ge=0,
    )
    breakdown: dict[str, Decimal] | None = Field(
        default=None,
        description="Cost breakdown by component (input_cost, output_cost, etc.)",
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
    )

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Validate currency code."""
        return v.upper()

    @property
    def total_tokens_estimate(self) -> int:
        """Compute total estimated tokens (input + output)."""
        return self.input_tokens_estimate + self.output_tokens_estimate

