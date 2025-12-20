"""Policy data models for declarative routing rules."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PolicyType(str, Enum):
    """Enumeration of policy types."""

    Routing = "routing"
    """Policies that affect routing decisions."""

    CostControl = "cost_control"
    """Policies that control cost and budgets."""

    KeySelection = "key_selection"
    """Policies that filter or prioritize keys."""

    FailureHandling = "failure_handling"
    """Policies that handle failures and retries."""


class PolicyScope(str, Enum):
    """Enumeration of policy scopes."""

    Global = "global"
    """Policy applies globally to all requests."""

    PerProvider = "per_provider"
    """Policy applies to a specific provider."""

    PerKey = "per_key"
    """Policy applies to a specific key."""

    PerRoute = "per_route"
    """Policy applies to a specific route/endpoint."""


class Policy(BaseModel):
    """Declarative policy that drives routing, cost control, and key selection.

    Policies express intent, not procedure. They are evaluated against
    routing context to filter keys and apply constraints.
    """

    id: str = Field(..., description="Unique identifier for this policy", min_length=1)
    name: str = Field(..., description="Human-readable policy name", min_length=1)
    type: PolicyType = Field(..., description="Type of policy")
    scope: PolicyScope = Field(..., description="Scope where policy applies")
    scope_id: str | None = Field(
        default=None,
        description="Specific entity ID if scoped (provider_id, key_id, etc.)",
    )
    rules: dict[str, Any] = Field(
        default_factory=dict,
        description="Declarative policy rules (constraints, filters, etc.)",
    )
    priority: int = Field(
        default=0,
        description="Priority/precedence (higher = more important, used for conflict resolution)",
    )
    enabled: bool = Field(
        default=True, description="Whether this policy is active"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="When policy was created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    @field_validator("id", "name")
    @classmethod
    def validate_string_fields(cls, v: str) -> str:
        """Validate string fields are non-empty."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


class PolicyResult(BaseModel):
    """Result of policy evaluation against routing context.

    Contains information about which keys are allowed, which are filtered,
    and what constraints should be applied.
    """

    allowed: bool = Field(
        default=True,
        description="Whether routing is allowed (false = reject request)",
    )
    filtered_keys: list[str] = Field(
        default_factory=list,
        description="List of key IDs to exclude from routing",
    )
    constraints: dict[str, Any] = Field(
        default_factory=dict,
        description="Constraints to apply (max_cost, min_reliability, etc.)",
    )
    reason: str = Field(
        default="",
        description="Human-readable reason for policy application",
    )
    applied_policies: list[str] = Field(
        default_factory=list,
        description="List of policy IDs that were applied",
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
    )



