"""StateTransition data model for audit trail."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StateTransition(BaseModel):
    """Represents a state transition for audit trail purposes.

    StateTransition records all state changes with full context for
    observability and debugging.
    """

    entity_type: str = Field(
        ...,
        description="Type of entity (e.g., 'APIKey')",
        min_length=1,
    )
    entity_id: str = Field(
        ...,
        description="Entity identifier (e.g., key_id)",
        min_length=1,
    )
    from_state: str = Field(
        ...,
        description="Previous state value",
    )
    to_state: str = Field(
        ...,
        description="New state value",
    )
    transition_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when transition occurred",
    )
    trigger: str = Field(
        ...,
        description="What caused transition (request, error, policy, manual, automatic)",
        min_length=1,
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context about transition",
    )

    model_config = ConfigDict(
        frozen=True,  # Immutable audit trail
        validate_assignment=True,
    )




