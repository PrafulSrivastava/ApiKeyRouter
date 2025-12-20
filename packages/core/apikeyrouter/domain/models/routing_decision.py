"""RoutingDecision data model and RoutingObjective models."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ObjectiveType(str, Enum):
    """Enumeration of routing objective types.

    Objectives represent what the routing engine optimizes for when
    selecting an API key for a request.
    """

    Cost = "cost"
    """Minimize cost per request."""

    Reliability = "reliability"
    """Maximize reliability and success rate."""

    Fairness = "fairness"
    """Distribute load fairly across keys."""

    Quality = "quality"
    """Maximize response quality (e.g., model capability)."""


class AlternativeRoute(BaseModel):
    """Represents an alternative routing option that was considered but not selected.

    Used to track other viable options during routing decision-making
    for audit and explainability purposes.
    """

    key_id: str = Field(..., description="Alternative key ID that was considered")
    provider_id: str = Field(..., description="Alternative provider ID")
    score: float | None = Field(
        default=None,
        description="Evaluation score for this alternative",
    )
    reason_not_selected: str | None = Field(
        default=None,
        description="Reason why this alternative was not chosen",
    )

    model_config = ConfigDict(frozen=True)


class RoutingObjective(BaseModel):
    """Explicit objective configuration for routing optimization.

    Defines what the routing engine should optimize for, including
    primary objective, secondary objectives, constraints, and weights
    for multi-objective optimization.
    """

    primary: str = Field(
        ...,
        description="Primary objective (cost, reliability, fairness, quality, latency)",
        min_length=1,
    )
    secondary: list[str] = Field(
        default_factory=list,
        description="Secondary objectives to consider",
    )
    constraints: dict[str, Any] = Field(
        default_factory=dict,
        description="Hard constraints (min reliability, max cost, etc.)",
    )
    weights: dict[str, float] = Field(
        default_factory=dict,
        description="Objective weights for multi-objective optimization",
    )

    model_config = ConfigDict(frozen=True)

    @field_validator("primary")
    @classmethod
    def validate_primary(cls, v: str) -> str:
        """Validate primary objective is a valid objective type."""
        valid_objectives = {obj.value for obj in ObjectiveType}
        # Also allow "latency" as mentioned in architecture docs
        valid_objectives.add("latency")
        if v.lower() not in valid_objectives:
            raise ValueError(
                f"Primary objective must be one of {valid_objectives}, got {v}"
            )
        return v.lower()

    @field_validator("secondary")
    @classmethod
    def validate_secondary(cls, v: list[str]) -> list[str]:
        """Validate secondary objectives are valid objective types."""
        valid_objectives = {obj.value for obj in ObjectiveType}
        valid_objectives.add("latency")
        for obj in v:
            if obj.lower() not in valid_objectives:
                raise ValueError(
                    f"Secondary objective must be one of {valid_objectives}, got {obj}"
                )
        return [obj.lower() for obj in v]

    @field_validator("weights")
    @classmethod
    def validate_weights(cls, v: dict[str, float]) -> dict[str, float]:
        """Validate weights are between 0.0 and 1.0."""
        for key, weight in v.items():
            if not 0.0 <= weight <= 1.0:
                raise ValueError(f"Weight for {key} must be between 0.0 and 1.0, got {weight}")
        return v


class RoutingDecision(BaseModel):
    """Represents an explainable routing choice with full context.

    Every routing decision is intentional and traceable. This model
    captures the decision, the reasoning, and alternatives considered.
    """

    id: str = Field(
        ...,
        description="Unique identifier for this routing decision",
        min_length=1,
    )
    request_id: str = Field(
        ...,
        description="Reference to the request that triggered this decision",
        min_length=1,
    )
    selected_key_id: str = Field(
        ...,
        description="Which key was chosen for routing",
        min_length=1,
    )
    selected_provider_id: str = Field(
        ...,
        description="Which provider was chosen for routing",
        min_length=1,
    )
    decision_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the routing decision was made",
    )
    objective: RoutingObjective = Field(
        ...,
        description="What was optimized (cost, reliability, fairness, quality)",
    )
    eligible_keys: list[str] = Field(
        default_factory=list,
        description="Key IDs that were eligible for routing",
    )
    evaluation_results: dict[str, Any] = Field(
        default_factory=dict,
        description="How each key scored during evaluation (scores per key)",
    )
    explanation: str = Field(
        ...,
        description="Human-readable explanation of why this key was chosen",
        min_length=1,
    )
    confidence: float = Field(
        ...,
        description="Confidence in decision (0.0 to 1.0)",
        ge=0.0,
        le=1.0,
    )
    alternatives_considered: list[AlternativeRoute] = Field(
        default_factory=list,
        description="Other routing options that were evaluated but not selected",
    )

    model_config = ConfigDict(
        frozen=False,  # Allow updates for audit trail
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validate decision ID format."""
        if not v or not v.strip():
            raise ValueError("Decision ID cannot be empty")
        if len(v) > 255:
            raise ValueError("Decision ID must be 255 characters or less")
        return v.strip()

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, v: str) -> str:
        """Validate request ID format."""
        if not v or not v.strip():
            raise ValueError("Request ID cannot be empty")
        return v.strip()

    @field_validator("explanation")
    @classmethod
    def validate_explanation(cls, v: str) -> str:
        """Validate explanation is not empty (critical rule)."""
        if not v or not v.strip():
            raise ValueError("Explanation is required and cannot be empty")
        return v.strip()

