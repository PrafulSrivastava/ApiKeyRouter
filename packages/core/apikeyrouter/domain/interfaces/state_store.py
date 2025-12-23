"""StateStore interface for state persistence and retrieval.

This module defines the abstract StateStore interface that provides a consistent
API for persisting and querying state across different storage backends (in-memory,
Redis, MongoDB, etc.).

Example:
    ```python
    from apikeyrouter.domain.interfaces.state_store import StateStore
    from apikeyrouter.infrastructure.state_store.memory_store import MemoryStore

    # Use in-memory store (default)
    store: StateStore = MemoryStore()

    # Save a key
    key = APIKey(id="key1", key_material="encrypted_key", provider_id="openai")
    await store.save_key(key)

    # Retrieve a key
    retrieved_key = await store.get_key("key1")

    # Query state
    query = StateQuery(entity_type="APIKey", provider_id="openai")
    results = await store.query_state(query)
    ```
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apikeyrouter.domain.models.api_key import APIKey
from apikeyrouter.domain.models.quota_state import QuotaState
from apikeyrouter.domain.models.routing_decision import RoutingDecision
from apikeyrouter.domain.models.state_transition import StateTransition


class StateQuery(BaseModel):
    """Query parameters for state store queries.

    Used to filter and retrieve state objects from the store for observability
    and analysis purposes. Supports filtering by entity type, key ID, provider ID,
    state, and timestamp ranges.

    Attributes:
        entity_type: Type of entity to query (APIKey, QuotaState, RoutingDecision, StateTransition).
                     If None, queries all entity types.
        key_id: Filter by specific key ID. If None, matches all keys.
        provider_id: Filter by provider ID. If None, matches all providers.
        state: Filter by state value (e.g., "available", "throttled"). If None, matches all states.
        timestamp_from: Start of timestamp range filter. If None, no lower bound.
        timestamp_to: End of timestamp range filter. If None, no upper bound.
        limit: Maximum number of results to return. If None, returns all matches.
        offset: Number of results to skip (for pagination). If None, starts from beginning.

    Example:
        ```python
        # Query all available keys for a provider
        query = StateQuery(
            entity_type="APIKey",
            provider_id="openai",
            state="available"
        )
        results = await store.query_state(query)

        # Query routing decisions in a time range
        query = StateQuery(
            entity_type="RoutingDecision",
            timestamp_from=datetime(2024, 1, 1),
            timestamp_to=datetime(2024, 1, 31),
            limit=100
        )
        decisions = await store.query_state(query)
        ```
    """

    entity_type: str | None = Field(
        default=None,
        description="Type of entity to query (APIKey, QuotaState, RoutingDecision, StateTransition)",
    )
    key_id: str | None = Field(
        default=None,
        description="Filter by specific key ID",
    )
    provider_id: str | None = Field(
        default=None,
        description="Filter by provider ID",
    )
    state: str | None = Field(
        default=None,
        description="Filter by state value (e.g., 'available', 'throttled')",
    )
    timestamp_from: datetime | None = Field(
        default=None,
        description="Start of timestamp range filter",
    )
    timestamp_to: datetime | None = Field(
        default=None,
        description="End of timestamp range filter",
    )
    limit: int | None = Field(
        default=None,
        description="Maximum number of results to return (for pagination)",
        ge=1,
    )
    offset: int | None = Field(
        default=None,
        description="Number of results to skip (for pagination)",
        ge=0,
    )

    model_config = ConfigDict(
        frozen=True,
        validate_assignment=True,
        str_strip_whitespace=True,
    )


class StateStore(ABC):
    """Abstract interface for state persistence and retrieval.

    StateStore provides a consistent API for persisting and querying state across
    different storage backends. The default implementation is in-memory, with
    optional persistent backends (Redis, MongoDB) for production deployments.

    All methods are async to support non-blocking I/O operations. Implementations
    must handle errors gracefully and raise StateStoreError for operation failures.

    Key Features:
        - In-memory by default (stateless deployment support)
        - Optional persistent backends (Redis, MongoDB)
        - Query interface for observability
        - Full type hints for all methods
        - Async/await support throughout

    Example:
        ```python
        from apikeyrouter.domain.interfaces.state_store import StateStore
        from apikeyrouter.infrastructure.state_store.memory_store import MemoryStore

        # Create store instance
        store: StateStore = MemoryStore()

        # Save and retrieve API keys
        key = APIKey(id="key1", key_material="encrypted", provider_id="openai")
        await store.save_key(key)
        retrieved = await store.get_key("key1")

        # Save and retrieve quota state
        quota = QuotaState(
            id="quota1",
            key_id="key1",
            remaining_capacity=CapacityEstimate(value=1000),
            reset_at=datetime.utcnow()
        )
        await store.save_quota_state(quota)
        retrieved_quota = await store.get_quota_state("key1")

        # Save routing decisions and state transitions
        decision = RoutingDecision(...)
        await store.save_routing_decision(decision)

        transition = StateTransition(...)
        await store.save_state_transition(transition)

        # Query state for observability
        query = StateQuery(entity_type="APIKey", provider_id="openai")
        results = await store.query_state(query)
        ```
    """

    @abstractmethod
    async def save_key(self, key: APIKey) -> None:
        """Save an API key to the store.

        Persists an APIKey instance to the store. If a key with the same ID
        already exists, it should be updated (upsert behavior).

        Args:
            key: The APIKey to save.

        Raises:
            StateStoreError: If save operation fails (e.g., connection error,
                           validation error, storage full).

        Example:
            ```python
            key = APIKey(
                id="key1",
                key_material="encrypted_key_material",
                provider_id="openai"
            )
            await store.save_key(key)
            ```
        """
        pass

    @abstractmethod
    async def get_key(self, key_id: str) -> APIKey | None:
        """Retrieve an API key by ID.

        Fetches an APIKey from the store by its unique identifier.

        Args:
            key_id: The unique identifier of the key to retrieve.

        Returns:
            The APIKey if found, None if the key does not exist.

        Raises:
            StateStoreError: If retrieval operation fails (e.g., connection error).

        Example:
            ```python
            key = await store.get_key("key1")
            if key:
                print(f"Found key for provider: {key.provider_id}")
            ```
        """
        pass

    @abstractmethod
    async def list_keys(self, provider_id: str | None = None) -> list[APIKey]:
        """List all API keys, optionally filtered by provider.

        Retrieves all API keys from the store. If provider_id is provided,
        only returns keys for that provider.

        Args:
            provider_id: Optional provider ID to filter by. If None, returns all keys.

        Returns:
            List of APIKey objects matching the criteria.

        Raises:
            StateStoreError: If retrieval operation fails (e.g., connection error).

        Example:
            ```python
            # Get all keys
            all_keys = await store.list_keys()

            # Get only OpenAI keys
            openai_keys = await store.list_keys(provider_id="openai")
            ```
        """
        pass

    @abstractmethod
    async def save_quota_state(self, state: QuotaState) -> None:
        """Save a QuotaState to the store.

        Persists a QuotaState instance to the store. If a quota state for the
        same key_id already exists, it should be updated (upsert behavior).

        Args:
            state: The QuotaState to save.

        Raises:
            StateStoreError: If save operation fails (e.g., connection error,
                           validation error).

        Example:
            ```python
            quota = QuotaState(
                id="quota1",
                key_id="key1",
                remaining_capacity=CapacityEstimate(value=5000),
                reset_at=datetime.utcnow() + timedelta(days=1)
            )
            await store.save_quota_state(quota)
            ```
        """
        pass

    @abstractmethod
    async def get_quota_state(self, key_id: str) -> QuotaState | None:
        """Retrieve a QuotaState by key_id.

        Fetches the QuotaState associated with a specific API key.

        Args:
            key_id: The unique identifier of the key this quota state belongs to.

        Returns:
            The QuotaState if found, None if no quota state exists for this key.

        Raises:
            StateStoreError: If retrieval operation fails (e.g., connection error).

        Example:
            ```python
            quota = await store.get_quota_state("key1")
            if quota:
                print(f"Remaining capacity: {quota.remaining_capacity.value}")
            ```
        """
        pass

    @abstractmethod
    async def save_routing_decision(self, decision: RoutingDecision) -> None:
        """Save a routing decision to the audit trail.

        Persists a RoutingDecision instance to the store for audit and
        observability purposes. Routing decisions are typically append-only
        and should be retained for analysis.

        Args:
            decision: The RoutingDecision to save.

        Raises:
            StateStoreError: If save operation fails (e.g., connection error,
                           validation error).

        Example:
            ```python
            decision = RoutingDecision(
                id="decision1",
                request_id="req1",
                selected_key_id="key1",
                selected_provider_id="openai",
                objective=RoutingObjective(primary="cost"),
                explanation="Lowest cost key available"
            )
            await store.save_routing_decision(decision)
            ```
        """
        pass

    @abstractmethod
    async def save_state_transition(self, transition: StateTransition) -> None:
        """Save a state transition to the audit trail.

        Persists a StateTransition instance to the store for audit and
        debugging purposes. State transitions are typically append-only
        and provide a complete history of state changes.

        Args:
            transition: The StateTransition to save.

        Raises:
            StateStoreError: If save operation fails (e.g., connection error,
                           validation error).

        Example:
            ```python
            transition = StateTransition(
                entity_type="APIKey",
                entity_id="key1",
                from_state="available",
                to_state="throttled",
                trigger="rate_limit_error",
                context={"error_code": 429}
            )
            await store.save_state_transition(transition)
            ```
        """
        pass

    @abstractmethod
    async def query_state(self, query: StateQuery) -> list[Any]:
        """Query state objects based on filter criteria.

        Provides a flexible query interface for retrieving state objects
        (APIKey, QuotaState, RoutingDecision, StateTransition) based on
        various filter criteria. Supports filtering by entity type, key ID,
        provider ID, state, and timestamp ranges. Also supports pagination
        via limit and offset.

        Args:
            query: StateQuery object containing filter criteria and pagination options.

        Returns:
            List of matching state objects. The type of objects returned depends
            on the entity_type in the query. If entity_type is None, may return
            a mixed list of different entity types.

        Raises:
            StateStoreError: If query operation fails (e.g., connection error,
                           invalid query parameters).

        Example:
            ```python
            # Query all available keys for a provider
            query = StateQuery(
                entity_type="APIKey",
                provider_id="openai",
                state="available"
            )
            keys = await store.query_state(query)

            # Query routing decisions in a time range with pagination
            query = StateQuery(
                entity_type="RoutingDecision",
                timestamp_from=datetime(2024, 1, 1),
                timestamp_to=datetime(2024, 1, 31),
                limit=50,
                offset=0
            )
            decisions = await store.query_state(query)
            ```
        """
        pass


class StateStoreError(Exception):
    """Raised when StateStore operations fail.

    This exception is raised by StateStore implementations when operations
    cannot be completed due to errors such as:
    - Connection failures
    - Validation errors
    - Storage capacity issues
    - Invalid query parameters
    - Timeout errors

    Example:
        ```python
        try:
            await store.save_key(key)
        except StateStoreError as e:
            logger.error(f"Failed to save key: {e}")
        ```
    """

    pass
