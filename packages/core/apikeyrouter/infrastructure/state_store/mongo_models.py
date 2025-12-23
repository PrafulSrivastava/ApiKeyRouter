"""MongoDB document models using Beanie ODM.

This module provides Beanie document models for MongoDB persistence.
These models map the domain Pydantic models to MongoDB documents with
indexes for efficient querying.

Example:
    ```python
    from beanie import init_beanie
    from motor.motor_asyncio import AsyncIOMotorClient
    from apikeyrouter.infrastructure.state_store.mongo_models import (
        APIKeyDocument,
        QuotaStateDocument,
        RoutingDecisionDocument,
        StateTransitionDocument,
        initialize_beanie_models,
    )

    # Initialize Beanie
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    database = client["apikeyrouter"]
    await initialize_beanie_models(database)
    ```
"""

from datetime import datetime
from typing import Any

from beanie import Document, Indexed, init_beanie
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import IndexModel

from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.domain.models.quota_state import (
    CapacityEstimate,
    CapacityState,
    CapacityUnit,
    QuotaState,
    TimeWindow,
)
from apikeyrouter.domain.models.routing_decision import (
    AlternativeRoute,
    RoutingDecision,
    RoutingObjective,
)
from apikeyrouter.domain.models.state_transition import StateTransition


class APIKeyDocument(Document):
    """Beanie document model for APIKey.

    Maps the APIKey domain model to a MongoDB document with indexes
    for efficient querying by provider, state, and usage patterns.

    Indexes:
        - id: Unique index (primary key)
        - provider_id: Index for querying keys by provider
        - state: Index for querying keys by state
        - provider_id + state: Compound index for common queries
        - created_at: Index for sorting by creation time
    """

    id: str  # Maps to MongoDB _id (automatically unique and indexed)
    key_material: str
    provider_id: Indexed(str)  # type: ignore[valid-type]
    state: Indexed(str)  # type: ignore[valid-type]  # Store as string, convert to KeyState enum
    state_updated_at: datetime
    created_at: Indexed(datetime)  # type: ignore[valid-type]
    last_used_at: datetime | None = None
    usage_count: int = 0
    failure_count: int = 0
    cooldown_until: datetime | None = None
    metadata: dict[str, Any] = {}

    class Settings:
        """Beanie document settings."""

        name = "api_keys"  # Collection name
        indexes = [
            IndexModel([("provider_id", 1), ("state", 1)]),  # Compound index for common queries
            IndexModel([("state", 1), ("last_used_at", -1)]),  # Query by state, sort by usage
            IndexModel([("created_at", -1)]),  # Sort by creation time
        ]

    @classmethod
    def from_domain_model(cls, key: APIKey) -> "APIKeyDocument":
        """Create APIKeyDocument from domain APIKey model.

        Args:
            key: Domain APIKey model instance.

        Returns:
            APIKeyDocument instance.
        """
        return cls(
            id=key.id,
            key_material=key.key_material,
            provider_id=key.provider_id,
            state=key.state.value,  # Convert enum to string
            state_updated_at=key.state_updated_at,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            usage_count=key.usage_count,
            failure_count=key.failure_count,
            cooldown_until=key.cooldown_until,
            metadata=key.metadata,
        )

    def to_domain_model(self) -> APIKey:
        """Convert APIKeyDocument to domain APIKey model.

        Returns:
            APIKey domain model instance.
        """
        return APIKey(
            id=self.id,
            key_material=self.key_material,
            provider_id=self.provider_id,
            state=KeyState(self.state),  # Convert string to enum
            state_updated_at=self.state_updated_at,
            created_at=self.created_at,
            last_used_at=self.last_used_at,
            usage_count=self.usage_count,
            failure_count=self.failure_count,
            cooldown_until=self.cooldown_until,
            metadata=self.metadata,
        )


class QuotaStateDocument(Document):
    """Beanie document model for QuotaState.

    Maps the QuotaState domain model to a MongoDB document with indexes
    for efficient querying by key_id and reset schedule.

    Indexes:
        - id: Unique index (primary key)
        - key_id: Unique index for querying quota by key
        - reset_at: Index for querying by reset time
    """

    id: str  # Maps to MongoDB _id (automatically unique and indexed)
    key_id: Indexed(str, unique=True)  # type: ignore[valid-type]
    capacity_state: CapacityState
    capacity_unit: CapacityUnit
    remaining_capacity: CapacityEstimate
    total_capacity: int | None = None
    used_capacity: int = 0
    remaining_tokens: CapacityEstimate | None = None
    total_tokens: int | None = None
    used_tokens: int = 0
    used_requests: int = 0
    time_window: TimeWindow
    reset_at: Indexed(datetime)  # type: ignore[valid-type]
    updated_at: datetime

    class Settings:
        """Beanie document settings."""

        name = "quota_states"  # Collection name
        indexes = [
            IndexModel([("reset_at", 1)]),  # Query by reset time
        ]

    @classmethod
    def from_domain_model(cls, quota_state: QuotaState) -> "QuotaStateDocument":
        """Create QuotaStateDocument from domain QuotaState model.

        Args:
            quota_state: Domain QuotaState model instance.

        Returns:
            QuotaStateDocument instance.
        """
        return cls(
            id=quota_state.id,
            key_id=quota_state.key_id,
            capacity_state=quota_state.capacity_state,
            capacity_unit=quota_state.capacity_unit,
            remaining_capacity=quota_state.remaining_capacity,
            total_capacity=quota_state.total_capacity,
            used_capacity=quota_state.used_capacity,
            remaining_tokens=quota_state.remaining_tokens,
            total_tokens=quota_state.total_tokens,
            used_tokens=quota_state.used_tokens,
            used_requests=quota_state.used_requests,
            time_window=quota_state.time_window,
            reset_at=quota_state.reset_at,
            updated_at=quota_state.updated_at,
        )

    def to_domain_model(self) -> QuotaState:
        """Convert QuotaStateDocument to domain QuotaState model.

        Returns:
            QuotaState domain model instance.
        """
        return QuotaState(
            id=self.id,
            key_id=self.key_id,
            capacity_state=self.capacity_state,
            capacity_unit=self.capacity_unit,
            remaining_capacity=self.remaining_capacity,
            total_capacity=self.total_capacity,
            used_capacity=self.used_capacity,
            remaining_tokens=self.remaining_tokens,
            total_tokens=self.total_tokens,
            used_tokens=self.used_tokens,
            used_requests=self.used_requests,
            time_window=self.time_window,
            reset_at=self.reset_at,
            updated_at=self.updated_at,
        )


class RoutingDecisionDocument(Document):
    """Beanie document model for RoutingDecision.

    Maps the RoutingDecision domain model to a MongoDB document with indexes
    for efficient querying by key, provider, and timestamp. Includes optional
    TTL index for automatic cleanup of old decisions.

    Indexes:
        - id: Unique index (primary key)
        - selected_key_id: Index for querying decisions by key
        - selected_provider_id: Index for querying decisions by provider
        - decision_timestamp: Index for querying by time (with optional TTL)
    """

    id: str  # Maps to MongoDB _id (automatically unique and indexed)
    request_id: str
    selected_key_id: Indexed(str)  # type: ignore[valid-type]
    selected_provider_id: Indexed(str)  # type: ignore[valid-type]
    decision_timestamp: Indexed(datetime)  # type: ignore[valid-type]
    objective: RoutingObjective
    eligible_keys: list[str] = []
    evaluation_results: dict[str, Any] = {}
    explanation: str
    confidence: float
    alternatives_considered: list[AlternativeRoute] = []

    class Settings:
        """Beanie document settings."""

        name = "routing_decisions"  # Collection name
        indexes = [
            IndexModel(
                [("selected_key_id", 1), ("decision_timestamp", -1)]
            ),  # Query by key, sort by time
            IndexModel(
                [("selected_provider_id", 1), ("decision_timestamp", -1)]
            ),  # Query by provider, sort by time
            # Optional TTL index: uncomment to enable automatic cleanup after 90 days
            # IndexModel([("decision_timestamp", 1)], expireAfterSeconds=7776000),  # 90 days in seconds
        ]

    @classmethod
    def from_domain_model(cls, decision: RoutingDecision) -> "RoutingDecisionDocument":
        """Create RoutingDecisionDocument from domain RoutingDecision model.

        Args:
            decision: Domain RoutingDecision model instance.

        Returns:
            RoutingDecisionDocument instance.
        """
        return cls(
            id=decision.id,
            request_id=decision.request_id,
            selected_key_id=decision.selected_key_id,
            selected_provider_id=decision.selected_provider_id,
            decision_timestamp=decision.decision_timestamp,
            objective=decision.objective,
            eligible_keys=decision.eligible_keys,
            evaluation_results=decision.evaluation_results,
            explanation=decision.explanation,
            confidence=decision.confidence,
            alternatives_considered=decision.alternatives_considered,
        )

    def to_domain_model(self) -> RoutingDecision:
        """Convert RoutingDecisionDocument to domain RoutingDecision model.

        Returns:
            RoutingDecision domain model instance.
        """
        return RoutingDecision(
            id=self.id,
            request_id=self.request_id,
            selected_key_id=self.selected_key_id,
            selected_provider_id=self.selected_provider_id,
            decision_timestamp=self.decision_timestamp,
            objective=self.objective,
            eligible_keys=self.eligible_keys,
            evaluation_results=self.evaluation_results,
            explanation=self.explanation,
            confidence=self.confidence,
            alternatives_considered=self.alternatives_considered,
        )


class StateTransitionDocument(Document):
    """Beanie document model for StateTransition.

    Maps the StateTransition domain model to a MongoDB document with indexes
    for efficient querying by entity, type, and timestamp. Includes optional
    TTL index for automatic cleanup of old transitions.

    Indexes:
        - id: Auto-generated ObjectId (primary key)
        - entity_id: Index for querying transitions by entity
        - entity_type: Index for querying transitions by type
        - transition_timestamp: Index for querying by time (with optional TTL)
    """

    entity_type: Indexed(str)  # type: ignore[valid-type]
    entity_id: Indexed(str)  # type: ignore[valid-type]
    from_state: str
    to_state: str
    transition_timestamp: Indexed(datetime)  # type: ignore[valid-type]
    trigger: str
    context: dict[str, Any] = {}

    class Settings:
        """Beanie document settings."""

        name = "state_transitions"  # Collection name
        indexes = [
            IndexModel(
                [("entity_id", 1), ("transition_timestamp", -1)]
            ),  # Query by entity, sort by time
            IndexModel(
                [("entity_type", 1), ("transition_timestamp", -1)]
            ),  # Query by type, sort by time
            # Optional TTL index: uncomment to enable automatic cleanup after 90 days
            # IndexModel([("transition_timestamp", 1)], expireAfterSeconds=7776000),  # 90 days in seconds
        ]

    @classmethod
    def from_domain_model(cls, transition: StateTransition) -> "StateTransitionDocument":
        """Create StateTransitionDocument from domain StateTransition model.

        Args:
            transition: Domain StateTransition model instance.

        Returns:
            StateTransitionDocument instance.
        """
        return cls(
            entity_type=transition.entity_type,
            entity_id=transition.entity_id,
            from_state=transition.from_state,
            to_state=transition.to_state,
            transition_timestamp=transition.transition_timestamp,
            trigger=transition.trigger,
            context=transition.context,
        )

    def to_domain_model(self) -> StateTransition:
        """Convert StateTransitionDocument to domain StateTransition model.

        Returns:
            StateTransition domain model instance.
        """
        return StateTransition(
            entity_type=self.entity_type,
            entity_id=self.entity_id,
            from_state=self.from_state,
            to_state=self.to_state,
            transition_timestamp=self.transition_timestamp,
            trigger=self.trigger,
            context=self.context,
        )


async def initialize_beanie_models(database: AsyncIOMotorDatabase) -> None:
    """Initialize Beanie with all document models.

    Registers all Beanie document models and creates indexes on startup.
    This function should be called once when the application starts.

    Args:
        database: MongoDB database instance from motor client.

    Example:
        ```python
        from motor.motor_asyncio import AsyncIOMotorClient
        from apikeyrouter.infrastructure.state_store.mongo_models import initialize_beanie_models

        client = AsyncIOMotorClient("mongodb://localhost:27017")
        database = client["apikeyrouter"]
        await initialize_beanie_models(database)
        ```

    Raises:
        Exception: If Beanie initialization fails.
    """
    await init_beanie(
        database=database,
        document_models=[
            APIKeyDocument,
            QuotaStateDocument,
            RoutingDecisionDocument,
            StateTransitionDocument,
        ],
    )
