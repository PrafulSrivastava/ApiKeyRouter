"""QuotaState data model with capacity tracking."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CapacityState(str, Enum):
    """Enumeration of capacity states for quota tracking.

    States represent the current capacity level of a key's quota and determine
    routing priority and usage recommendations.
    """

    Abundant = "abundant"
    """More than 80% remaining capacity. Safe to use for any request."""

    Constrained = "constrained"
    """50-80% remaining capacity. Use with caution, monitor usage."""

    Critical = "critical"
    """20-50% remaining capacity. Avoid unless necessary."""

    Exhausted = "exhausted"
    """Less than 20% remaining or hard limit hit. Do not use."""

    Recovering = "recovering"
    """Exhausted but reset approaching. Monitor for availability."""


class UncertaintyLevel(str, Enum):
    """Enumeration of uncertainty levels for capacity estimates and predictions.

    Uncertainty levels indicate the reliability of capacity estimates and
    determine how conservative the system should be in its decisions.
    """

    Low = "low"
    """Low uncertainty: Exact capacity known, sufficient data, stable usage. Use exact calculations."""

    Medium = "medium"
    """Medium uncertainty: Estimated capacity or moderate data quality. Use moderate estimates."""

    High = "high"
    """High uncertainty: Bounded capacity or insufficient data. Use conservative estimates."""

    Unknown = "unknown"
    """Unknown uncertainty: Capacity unknown or very poor data quality. Use most conservative estimates."""


class CapacityUnit(str, Enum):
    """Enumeration of capacity units for quota tracking.

    Defines the unit in which capacity is measured (requests, tokens, or both).
    """

    Requests = "requests"
    """Capacity is measured in number of requests."""

    Tokens = "tokens"
    """Capacity is measured in number of tokens."""

    Mixed = "mixed"
    """Capacity has both request limits and token limits."""


class TimeWindow(str, Enum):
    """Enumeration of quota reset time windows.

    Defines the frequency at which quota capacity resets.
    """

    Daily = "daily"
    """Quota resets every 24 hours."""

    Hourly = "hourly"
    """Quota resets every hour."""

    Monthly = "monthly"
    """Quota resets every month."""

    Custom = "custom"
    """Custom reset schedule defined by reset_at field."""

    def calculate_next_reset(self, current_time: datetime) -> datetime:
        """Calculate the next reset time based on the time window.

        Args:
            current_time: The current datetime to calculate from.

        Returns:
            The datetime when the quota will next reset.

        Raises:
            ValueError: If time window is Custom (use reset_at field directly).
        """
        if self == TimeWindow.Custom:
            raise ValueError(
                "Cannot calculate reset for Custom time window. Use reset_at field directly."
            )

        from datetime import timedelta

        if self == TimeWindow.Hourly:
            return current_time.replace(minute=0, second=0, microsecond=0) + timedelta(
                hours=1
            )
        elif self == TimeWindow.Daily:
            return current_time.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
        elif self == TimeWindow.Monthly:
            # Calculate first day of next month
            if current_time.month == 12:
                return current_time.replace(
                    year=current_time.year + 1,
                    month=1,
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            else:
                return current_time.replace(
                    month=current_time.month + 1,
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
        else:
            raise ValueError(f"Unknown time window: {self}")


class CapacityEstimate(BaseModel):
    """Represents an estimate of remaining capacity.

    Supports exact values, estimated ranges, and bounded estimates with
    confidence levels and verification tracking.
    """

    value: int | None = Field(
        default=None,
        description="Exact value if known, None if estimated or unknown",
        ge=0,
    )
    min_value: int | None = Field(
        default=None,
        description="Lower bound if estimated, None if exact or unknown",
        ge=0,
    )
    max_value: int | None = Field(
        default=None,
        description="Upper bound if estimated, None if exact or unknown",
        ge=0,
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence level from 0.0 to 1.0",
        ge=0.0,
        le=1.0,
    )
    estimation_method: str = Field(
        default="unknown",
        description="Method used to calculate the estimate (e.g., 'api_response', 'historical', 'heuristic')",
    )
    last_verified: datetime | None = Field(
        default=None,
        description="Timestamp when estimate was last verified against provider API",
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        str_strip_whitespace=True,
    )


    def get_estimate_type(self) -> Literal["exact", "estimated", "bounded", "unknown"]:
        """Determine the type of estimate based on available fields.

        Returns:
            'exact' if value is known
            'estimated' if min/max bounds are available
            'bounded' if only one bound is available
            'unknown' if no information is available
        """
        if self.value is not None:
            return "exact"
        elif self.min_value is not None and self.max_value is not None:
            return "estimated"
        elif self.min_value is not None or self.max_value is not None:
            return "bounded"
        else:
            return "unknown"

    def __repr__(self) -> str:
        """String representation of capacity estimate."""
        estimate_type = self.get_estimate_type()
        if estimate_type == "exact":
            return f"CapacityEstimate(value={self.value}, confidence={self.confidence})"
        elif estimate_type == "estimated":
            return (
                f"CapacityEstimate(min={self.min_value}, max={self.max_value}, "
                f"confidence={self.confidence})"
            )
        elif estimate_type == "bounded":
            bound = (
                f"min={self.min_value}"
                if self.min_value is not None
                else f"max={self.max_value}"
            )
            return f"CapacityEstimate({bound}, confidence={self.confidence})"
        else:
            return f"CapacityEstimate(unknown, confidence={self.confidence})"


class QuotaState(BaseModel):
    """Represents the quota state for an API key.

    Tracks remaining capacity, total capacity, usage, and reset schedule
    for quota-aware routing decisions. Supports capacity measured in requests,
    tokens, or both (mixed).
    """

    id: str = Field(
        ...,
        description="Unique identifier for this quota state",
        min_length=1,
    )
    key_id: str = Field(
        ...,
        description="Reference to the APIKey this quota state belongs to",
        min_length=1,
    )
    capacity_state: CapacityState = Field(
        default=CapacityState.Abundant,
        description="Current capacity state based on remaining capacity",
    )
    capacity_unit: CapacityUnit = Field(
        default=CapacityUnit.Requests,
        description="Unit in which capacity is measured (requests, tokens, or mixed)",
    )
    remaining_capacity: CapacityEstimate = Field(
        ...,
        description="Estimate of remaining capacity (exact, estimated, or bounded)",
    )
    total_capacity: int | None = Field(
        default=None,
        description="Total capacity if known, None if unknown (in capacity_unit)",
        ge=0,
    )
    used_capacity: int = Field(
        default=0,
        description="Amount of capacity consumed (in capacity_unit)",
        ge=0,
    )
    # Fields for mixed units (when capacity_unit is Mixed)
    remaining_tokens: CapacityEstimate | None = Field(
        default=None,
        description="Remaining token capacity (only used when capacity_unit is Mixed)",
    )
    total_tokens: int | None = Field(
        default=None,
        description="Total token capacity if known (only used when capacity_unit is Mixed)",
        ge=0,
    )
    used_tokens: int = Field(
        default=0,
        description="Amount of tokens consumed (only used when capacity_unit is Mixed or Tokens)",
        ge=0,
    )
    used_requests: int = Field(
        default=0,
        description="Amount of requests consumed (only used when capacity_unit is Mixed)",
        ge=0,
    )
    time_window: TimeWindow = Field(
        default=TimeWindow.Daily,
        description="Quota reset schedule (daily, hourly, monthly, custom)",
    )
    reset_at: datetime = Field(
        ...,
        description="Timestamp when quota will reset",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when quota state was last updated",
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    @field_validator("id", "key_id")
    @classmethod
    def validate_ids(cls, v: str) -> str:
        """Validate ID fields are non-empty."""
        if not v or not v.strip():
            raise ValueError("ID cannot be empty")
        if len(v) > 255:
            raise ValueError("ID must be 255 characters or less")
        return v.strip()


    def __repr__(self) -> str:
        """String representation of quota state."""
        return (
            f"QuotaState(id={self.id!r}, key_id={self.key_id!r}, "
            f"capacity_state={self.capacity_state.value}, "
            f"used_capacity={self.used_capacity}, "
            f"time_window={self.time_window.value})"
        )


class UsageRate(BaseModel):
    """Represents usage rate calculation for an API key.

    Tracks the rate of requests and token consumption over a time window
    to enable predictive exhaustion calculations.
    """

    requests_per_hour: float = Field(
        ...,
        description="Average number of requests per hour",
        ge=0.0,
    )
    tokens_per_hour: float | None = Field(
        default=None,
        description="Average number of tokens per hour (if available)",
        ge=0.0,
    )
    window_hours: float = Field(
        ...,
        description="Time window used for calculation in hours",
        gt=0.0,
    )
    calculated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when calculation was performed",
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence in the calculation (0.0 to 1.0) based on data quality",
        ge=0.0,
        le=1.0,
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    @field_validator("window_hours")
    @classmethod
    def validate_window_hours(cls, v: float) -> float:
        """Validate window_hours is positive."""
        if v <= 0:
            raise ValueError("window_hours must be greater than 0")
        return v

    def __repr__(self) -> str:
        """String representation of usage rate."""
        tokens_str = (
            f"{self.tokens_per_hour:.2f}" if self.tokens_per_hour is not None else "None"
        )
        return (
            f"UsageRate(requests_per_hour={self.requests_per_hour:.2f}, "
            f"tokens_per_hour={tokens_str}, window_hours={self.window_hours:.2f}, "
            f"confidence={self.confidence:.2f})"
        )


class ExhaustionPrediction(BaseModel):
    """Represents a prediction of when an API key will exhaust its quota.

    Provides forward-looking quota awareness by predicting when a key will
    run out of capacity based on current usage rate and remaining capacity.
    """

    key_id: str = Field(
        ...,
        description="Reference to the APIKey this prediction is for",
        min_length=1,
    )
    predicted_exhaustion_at: datetime = Field(
        ...,
        description="Predicted datetime when the key will exhaust its quota",
    )
    confidence: float = Field(
        ...,
        description="Confidence in the prediction (0.0 to 1.0)",
        ge=0.0,
        le=1.0,
    )
    calculation_method: str = Field(
        ...,
        description="Method used to calculate the prediction (e.g., 'usage_rate_division', 'linear_extrapolation')",
        min_length=1,
    )
    current_usage_rate: float = Field(
        ...,
        description="Current usage rate (requests per hour) used in calculation",
        ge=0.0,
    )
    remaining_capacity: int | None = Field(
        ...,
        description="Remaining capacity at time of calculation (None if unknown)",
        ge=0,
    )
    calculated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when prediction was calculated",
    )
    uncertainty_level: UncertaintyLevel = Field(
        default=UncertaintyLevel.Unknown,
        description="Uncertainty level of the prediction (low, medium, high, unknown)",
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    @field_validator("key_id")
    @classmethod
    def validate_key_id(cls, v: str) -> str:
        """Validate key_id is non-empty."""
        if not v or not v.strip():
            raise ValueError("key_id cannot be empty")
        return v.strip()

    @field_validator("calculation_method")
    @classmethod
    def validate_calculation_method(cls, v: str) -> str:
        """Validate calculation_method is non-empty."""
        if not v or not v.strip():
            raise ValueError("calculation_method cannot be empty")
        return v.strip()

    def __repr__(self) -> str:
        """String representation of exhaustion prediction."""
        remaining_str = (
            str(self.remaining_capacity) if self.remaining_capacity is not None else "None"
        )
        return (
            f"ExhaustionPrediction(key_id={self.key_id!r}, "
            f"predicted_exhaustion_at={self.predicted_exhaustion_at.isoformat()}, "
            f"confidence={self.confidence:.2f}, "
            f"remaining_capacity={remaining_str}, "
            f"usage_rate={self.current_usage_rate:.2f})"
        )
