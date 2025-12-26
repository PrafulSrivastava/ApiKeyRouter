"""HealthState model for provider health status."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthStatus(str, Enum):
    """Health status enumeration for providers."""

    Healthy = "healthy"
    """Provider is operational and responding normally."""

    Degraded = "degraded"
    """Provider has issues but is partially operational (e.g., rate limited)."""

    Down = "down"
    """Provider is unavailable or not responding."""


class HealthState(BaseModel):
    """Health state for a provider.

    HealthState represents the current operational status of a provider,
    including status, last check time, and optional details.

    Example:
        ```python
        health = HealthState(
            status=HealthStatus.Healthy,
            last_check=datetime.utcnow(),
            latency_ms=150
        )
        ```
    """

    status: HealthStatus = Field(
        ...,
        description="Current health status",
    )
    last_check: datetime = Field(
        ...,
        description="Timestamp of last health check",
    )
    latency_ms: int | None = Field(
        default=None,
        description="Response latency in milliseconds",
        ge=0,
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional health check details",
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
    )

