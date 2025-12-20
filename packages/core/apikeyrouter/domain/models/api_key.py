"""APIKey data model and KeyState enum."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class KeyState(str, Enum):
    """Enumeration of possible states for an API key.

    States represent the current operational status of a key and determine
    whether it can be used for routing requests.
    """

    Available = "available"
    """Key is available and ready to use for requests."""

    Throttled = "throttled"
    """Key has been rate-limited and is in cooldown period."""

    Exhausted = "exhausted"
    """Key has exhausted its quota/capacity and cannot be used."""

    Recovering = "recovering"
    """Key is recovering from exhaustion and quota reset is approaching."""

    Disabled = "disabled"
    """Key has been manually disabled and cannot be used."""

    Invalid = "invalid"
    """Key is invalid (e.g., authentication failure) and cannot be used."""


class APIKey(BaseModel):
    """Represents an API key with explicit state, identity, and usage tracking.

    APIKey is a first-class entity with stable identity. The key material
    is stored encrypted and should never be logged or exposed.
    """

    id: str = Field(
        ...,
        description="Stable, unique identifier for the key (not the key material itself)",
        min_length=1,
    )
    key_material: str = Field(
        ...,
        description="Encrypted/secure storage of actual API key",
        min_length=1,
    )
    provider_id: str = Field(
        ...,
        description="Reference to Provider this key belongs to",
        min_length=1,
    )
    state: KeyState = Field(
        default=KeyState.Available,
        description="Current operational state of the key",
    )
    state_updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when state last changed",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when key was registered",
    )
    last_used_at: datetime | None = Field(
        default=None,
        description="Timestamp of last successful usage",
    )
    usage_count: int = Field(
        default=0,
        description="Total number of requests made with this key",
        ge=0,
    )
    failure_count: int = Field(
        default=0,
        description="Total number of failures encountered with this key",
        ge=0,
    )
    cooldown_until: datetime | None = Field(
        default=None,
        description="Timestamp when key can be used again (if throttled)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific metadata (account info, tier, etc.)",
    )

    model_config = ConfigDict(
        frozen=False,  # Allow state updates
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validate key ID format."""
        if not v or not v.strip():
            raise ValueError("Key ID cannot be empty")
        # Allow UUID format or deterministic string IDs
        if len(v) > 255:
            raise ValueError("Key ID must be 255 characters or less")
        return v.strip()

    @field_validator("provider_id")
    @classmethod
    def validate_provider_id(cls, v: str) -> str:
        """Validate provider ID format."""
        if not v or not v.strip():
            raise ValueError("Provider ID cannot be empty")
        if len(v) > 100:
            raise ValueError("Provider ID must be 100 characters or less")
        return v.strip().lower()

    @model_validator(mode="after")
    def validate_state_transitions(self) -> "APIKey":
        """Validate state-related fields are consistent."""
        # If key is throttled, cooldown_until should be set
        if self.state == KeyState.Throttled and self.cooldown_until is None:
            # Allow creation without cooldown, but warn
            pass
        # If key is not throttled, cooldown_until should be None
        if self.state != KeyState.Throttled and self.cooldown_until is not None:
            # Clear cooldown if state is not throttled
            self.cooldown_until = None
        return self

    def __repr__(self) -> str:
        """String representation that never exposes key material."""
        return (
            f"APIKey(id={self.id!r}, provider_id={self.provider_id!r}, "
            f"state={self.state.value}, usage_count={self.usage_count}, "
            f"failure_count={self.failure_count})"
        )

