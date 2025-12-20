"""Budget model for cost control and budget tracking."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apikeyrouter.domain.models.quota_state import TimeWindow


class BudgetScope(str, Enum):
    """Enumeration of budget scopes.

    Defines the scope at which a budget applies (global, per-provider, per-key, per-route).
    """

    Global = "global"
    """Budget applies globally across all providers and keys."""

    PerProvider = "per_provider"
    """Budget applies to a specific provider."""

    PerKey = "per_key"
    """Budget applies to a specific API key."""

    PerRoute = "per_route"
    """Budget applies to a specific route/endpoint."""


class EnforcementMode(str, Enum):
    """Enumeration of budget enforcement modes.

    Defines how budget limits are enforced when exceeded.
    """

    Hard = "hard"
    """Hard enforcement: Reject requests that would exceed budget."""

    Soft = "soft"
    """Soft enforcement: Allow requests but log warnings when budget exceeded."""


class Budget(BaseModel):
    """Represents a budget limit for cost control.

    Budget tracks spending limits at various scopes (global, per-provider, per-key)
    with time-window resets (daily, monthly). Supports both hard and soft enforcement.

    Example:
        ```python
        budget = Budget(
            id="budget_global_daily",
            scope=BudgetScope.Global,
            scope_id=None,
            limit_amount=Decimal("100.00"),
            current_spend=Decimal("45.50"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Hard,
            reset_at=datetime(2024, 1, 2, 0, 0, 0),
            created_at=datetime(2024, 1, 1, 0, 0, 0)
        )
        ```
    """

    id: str = Field(
        ...,
        description="Unique budget identifier",
        min_length=1,
        max_length=255,
    )
    scope: BudgetScope = Field(
        ...,
        description="Budget scope (global, per_provider, per_key, per_route)",
    )
    scope_id: str | None = Field(
        default=None,
        description="Specific entity ID if scoped (provider_id, key_id, route_id)",
        max_length=255,
    )
    limit_amount: Decimal = Field(
        ...,
        description="Budget limit amount in USD",
        ge=0,
    )
    current_spend: Decimal = Field(
        default=Decimal("0.00"),
        description="Current spending amount in USD",
        ge=0,
    )
    period: TimeWindow = Field(
        ...,
        description="Budget reset period (daily, monthly, etc.)",
    )
    enforcement_mode: EnforcementMode = Field(
        default=EnforcementMode.Hard,
        description="Enforcement mode (hard reject or soft warn)",
    )
    reset_at: datetime = Field(
        ...,
        description="Timestamp when budget will reset",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when budget was created",
    )
    warning_count: int = Field(
        default=0,
        description="Number of budget warnings issued (for soft enforcement tracking)",
        ge=0,
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validate budget ID is non-empty."""
        if not v or not v.strip():
            raise ValueError("Budget ID cannot be empty")
        return v.strip()

    @field_validator("scope_id")
    @classmethod
    def validate_scope_id(cls, v: str | None) -> str | None:
        """Validate scope_id format."""
        if v is not None and (not v or not v.strip()):
            raise ValueError("scope_id cannot be empty if provided")
        return v.strip() if v else None

    @model_validator(mode="after")
    def validate_scope_requirements(self) -> Budget:
        """Validate scope_id is provided when scope is not Global."""
        if self.scope != BudgetScope.Global and not self.scope_id:
            raise ValueError(f"scope_id is required for scope {self.scope.value}")
        return self

    @property
    def remaining_budget(self) -> Decimal:
        """Calculate remaining budget amount.

        Returns:
            Remaining budget (limit_amount - current_spend).
        """
        return max(Decimal("0.00"), self.limit_amount - self.current_spend)

    @property
    def is_exceeded(self) -> bool:
        """Check if budget has been exceeded.

        Returns:
            True if current_spend >= limit_amount, False otherwise.
        """
        return self.current_spend >= self.limit_amount

    @property
    def utilization_percentage(self) -> float:
        """Calculate budget utilization percentage.

        Returns:
            Percentage of budget used (0.0 to 100.0+).
        """
        if self.limit_amount == 0:
            return 0.0
        return float((self.current_spend / self.limit_amount) * 100)

    def __repr__(self) -> str:
        """String representation of budget."""
        return (
            f"Budget(id={self.id!r}, scope={self.scope.value}, "
            f"limit_amount={self.limit_amount}, current_spend={self.current_spend}, "
            f"period={self.period.value}, warning_count={self.warning_count})"
        )

