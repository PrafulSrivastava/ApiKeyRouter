"""In-memory state store implementation.

This module provides an in-memory implementation of the StateStore interface
using Python dictionaries. It is thread-safe for concurrent access and provides
high-performance storage without external dependencies.

Example:
    ```python
    from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore
    from apikeyrouter.domain.models.api_key import APIKey

    # Create store instance
    store = InMemoryStateStore()

    # Save a key
    key = APIKey(id="key1", key_material="encrypted_key", provider_id="openai")
    await store.save_key(key)

    # Retrieve a key
    retrieved_key = await store.get_key("key1")
    ```
"""

import asyncio
from typing import Any

from apikeyrouter.domain.interfaces.state_store import (
    StateQuery,
    StateStore,
    StateStoreError,
)
from apikeyrouter.domain.models.api_key import APIKey
from apikeyrouter.domain.models.quota_state import QuotaState
from apikeyrouter.domain.models.routing_decision import RoutingDecision
from apikeyrouter.domain.models.state_transition import StateTransition


class InMemoryStateStore(StateStore):
    """In-memory implementation of StateStore interface.

    Provides thread-safe, high-performance state storage using Python dictionaries.
    This implementation is the default state store and requires no external dependencies.

    Thread Safety:
        - Write operations (save_*) use asyncio.Lock for thread-safety
        - Read operations (get_*) are safe without locks (dict reads are atomic in Python)
        - Concurrent reads are fully supported

    Performance:
        - All operations are O(1) for typical use cases
        - Target: <1ms per operation
        - Lock contention is minimized by using separate locks per operation type

    Attributes:
        _keys: Dictionary storing APIKey objects keyed by key.id
        _quota_states: Dictionary storing QuotaState objects keyed by key_id
        _routing_decisions: List storing RoutingDecision objects
        _state_transitions: List storing StateTransition objects
        _write_lock: asyncio.Lock for thread-safe write operations
    """

    def __init__(self, max_decisions: int = 1000, max_transitions: int = 1000) -> None:
        """Initialize InMemoryStateStore with empty storage dictionaries.

        Args:
            max_decisions: Maximum number of routing decisions to store.
                          When limit is reached, oldest decisions are removed (FIFO).
                          Default is 1000. Set to 0 or negative for unlimited storage.
            max_transitions: Maximum number of state transitions to store.
                            When limit is reached, oldest transitions are removed (FIFO).
                            Default is 1000. Set to 0 or negative for unlimited storage.
        """
        # Storage dictionaries
        self._keys: dict[str, APIKey] = {}
        self._quota_states: dict[str, QuotaState] = {}
        self._routing_decisions: list[RoutingDecision] = []
        self._state_transitions: list[StateTransition] = []

        # Configuration
        self._max_decisions = max_decisions if max_decisions > 0 else 0  # 0 means unlimited
        self._max_transitions = max_transitions if max_transitions > 0 else 0  # 0 means unlimited

        # Lock for write operations (thread-safety)
        self._write_lock = asyncio.Lock()

    async def save_key(self, key: APIKey) -> None:
        """Save an API key to the store.

        Persists an APIKey instance to the in-memory store. If a key with the
        same ID already exists, it will be updated (upsert behavior).

        This method is thread-safe using asyncio.Lock to prevent race conditions
        during concurrent writes.

        Args:
            key: The APIKey to save.

        Raises:
            StateStoreError: If save operation fails (should not occur in
                           in-memory implementation, but included for interface
                           compatibility).

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
        try:
            async with self._write_lock:
                self._keys[key.id] = key
        except Exception as e:
            raise StateStoreError(f"Failed to save key {key.id}: {e}") from e

    async def get_key(self, key_id: str) -> APIKey | None:
        """Retrieve an API key by ID.

        Fetches an APIKey from the in-memory store by its unique identifier.
        This operation is thread-safe without locks because dictionary reads
        are atomic in Python.

        Args:
            key_id: The unique identifier of the key to retrieve.

        Returns:
            The APIKey if found, None if the key does not exist.

        Raises:
            StateStoreError: If retrieval operation fails (should not occur in
                           in-memory implementation, but included for interface
                           compatibility).

        Example:
            ```python
            key = await store.get_key("key1")
            if key:
                print(f"Found key for provider: {key.provider_id}")
            ```
        """
        try:
            # Dictionary reads are atomic in Python, no lock needed
            return self._keys.get(key_id)
        except Exception as e:
            raise StateStoreError(f"Failed to get key {key_id}: {e}") from e

    async def list_keys(self, provider_id: str | None = None) -> list[APIKey]:
        """List all API keys, optionally filtered by provider.

        Retrieves all API keys from the in-memory store. If provider_id is provided,
        only returns keys for that provider. This operation is thread-safe without
        locks because dictionary reads are atomic in Python.

        Args:
            provider_id: Optional provider ID to filter by. If None, returns all keys.

        Returns:
            List of APIKey objects matching the criteria.

        Raises:
            StateStoreError: If retrieval operation fails (should not occur in
                           in-memory implementation, but included for interface
                           compatibility).

        Example:
            ```python
            # Get all keys
            all_keys = await store.list_keys()

            # Get only OpenAI keys
            openai_keys = await store.list_keys(provider_id="openai")
            ```
        """
        try:
            all_keys = list(self._keys.values())
            if provider_id is None:
                return all_keys
            return [key for key in all_keys if key.provider_id == provider_id]
        except Exception as e:
            raise StateStoreError(f"Failed to list keys: {e}") from e

    async def save_quota_state(self, state: QuotaState) -> None:
        """Save a QuotaState to the store.

        Persists a QuotaState instance to the in-memory store. If a quota state
        for the same key_id already exists, it will be updated (upsert behavior).

        This method is thread-safe using asyncio.Lock to prevent race conditions
        during concurrent writes.

        Args:
            state: The QuotaState to save.

        Raises:
            StateStoreError: If save operation fails.

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
        try:
            async with self._write_lock:
                self._quota_states[state.key_id] = state
        except Exception as e:
            raise StateStoreError(f"Failed to save quota state for key {state.key_id}: {e}") from e

    async def get_quota_state(self, key_id: str) -> QuotaState | None:
        """Retrieve a QuotaState by key_id.

        Fetches the QuotaState associated with a specific API key.
        This operation is thread-safe without locks because dictionary reads
        are atomic in Python.

        Args:
            key_id: The unique identifier of the key this quota state belongs to.

        Returns:
            The QuotaState if found, None if no quota state exists for this key.

        Raises:
            StateStoreError: If retrieval operation fails.

        Example:
            ```python
            quota = await store.get_quota_state("key1")
            if quota:
                print(f"Remaining capacity: {quota.remaining_capacity.value}")
            ```
        """
        try:
            # Dictionary reads are atomic in Python, no lock needed
            return self._quota_states.get(key_id)
        except Exception as e:
            raise StateStoreError(f"Failed to get quota state for key {key_id}: {e}") from e

    async def save_routing_decision(self, decision: RoutingDecision) -> None:
        """Save a routing decision to the audit trail.

        Persists a RoutingDecision instance to the in-memory store for audit and
        observability purposes. Routing decisions are append-only and retained
        for analysis.

        If max_decisions limit is configured and reached, the oldest decision
        will be removed (FIFO) to maintain the limit.

        This method is thread-safe using asyncio.Lock to prevent race conditions
        during concurrent writes.

        Args:
            decision: The RoutingDecision to save.

        Raises:
            StateStoreError: If save operation fails.

        Example:
            ```python
            decision = RoutingDecision(
                id="decision1",
                request_id="req1",
                selected_key_id="key1",
                selected_provider_id="openai",
                objective=RoutingObjective(primary="cost"),
                explanation="Lowest cost key available",
                confidence=0.9
            )
            await store.save_routing_decision(decision)
            ```
        """
        try:
            async with self._write_lock:
                self._routing_decisions.append(decision)
                # Enforce max_decisions limit (FIFO removal)
                if self._max_decisions > 0 and len(self._routing_decisions) > self._max_decisions:
                    # Remove oldest decision (first in list)
                    self._routing_decisions.pop(0)
        except Exception as e:
            raise StateStoreError(f"Failed to save routing decision {decision.id}: {e}") from e

    async def save_state_transition(self, transition: StateTransition) -> None:
        """Save a state transition to the audit trail.

        Persists a StateTransition instance to the in-memory store for audit and
        debugging purposes. State transitions are append-only and provide a
        complete history of state changes.

        If max_transitions limit is configured and reached, the oldest transition
        will be removed (FIFO) to maintain the limit.

        This method is thread-safe using asyncio.Lock to prevent race conditions
        during concurrent writes.

        Args:
            transition: The StateTransition to save.

        Raises:
            StateStoreError: If save operation fails.

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
        try:
            async with self._write_lock:
                self._state_transitions.append(transition)
                # Enforce max_transitions limit (FIFO removal)
                if (
                    self._max_transitions > 0
                    and len(self._state_transitions) > self._max_transitions
                ):
                    # Remove oldest transition (first in list)
                    self._state_transitions.pop(0)
        except Exception as e:
            raise StateStoreError(
                f"Failed to save state transition for {transition.entity_type}:{transition.entity_id}: {e}"
            ) from e

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
            on the entity_type in the query. If entity_type is None, returns
            a mixed list of different entity types.

        Raises:
            StateStoreError: If query operation fails.

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
        try:
            results: list[Any] = []

            # Determine which storage to query based on entity_type
            if query.entity_type == "APIKey" or query.entity_type is None:
                # Query keys
                for key in self._keys.values():
                    if self._matches_key_filters(key, query):
                        results.append(key)

            if query.entity_type == "QuotaState" or query.entity_type is None:
                # Query quota states
                for quota_state in self._quota_states.values():
                    if self._matches_quota_filters(quota_state, query):
                        results.append(quota_state)

            if query.entity_type == "RoutingDecision" or query.entity_type is None:
                # Query routing decisions
                for decision in self._routing_decisions:
                    if self._matches_decision_filters(decision, query):
                        results.append(decision)

            if query.entity_type == "StateTransition" or query.entity_type is None:
                # Query state transitions
                for transition in self._state_transitions:
                    if self._matches_transition_filters(transition, query):
                        results.append(transition)

            # Apply pagination
            if query.offset is not None:
                results = results[query.offset :]
            if query.limit is not None:
                results = results[: query.limit]

            return results
        except Exception as e:
            raise StateStoreError(f"Failed to query state: {e}") from e

    def _matches_key_filters(self, key: APIKey, query: StateQuery) -> bool:
        """Check if APIKey matches query filters."""
        if query.key_id is not None and key.id != query.key_id:
            return False
        if query.provider_id is not None and key.provider_id != query.provider_id:
            return False
        if query.state is not None and key.state.value != query.state:
            return False
        if query.timestamp_from is not None and key.created_at < query.timestamp_from:
            return False
        return not (query.timestamp_to is not None and key.created_at > query.timestamp_to)

    def _matches_quota_filters(self, quota_state: QuotaState, query: StateQuery) -> bool:
        """Check if QuotaState matches query filters."""
        if query.key_id is not None and quota_state.key_id != query.key_id:
            return False
        if query.timestamp_from is not None and quota_state.updated_at < query.timestamp_from:
            return False
        return not (query.timestamp_to is not None and quota_state.updated_at > query.timestamp_to)

    def _matches_decision_filters(self, decision: RoutingDecision, query: StateQuery) -> bool:
        """Check if RoutingDecision matches query filters."""
        if query.key_id is not None and decision.selected_key_id != query.key_id:
            return False
        if query.provider_id is not None and decision.selected_provider_id != query.provider_id:
            return False
        if query.timestamp_from is not None and decision.decision_timestamp < query.timestamp_from:
            return False
        return not (
            query.timestamp_to is not None and decision.decision_timestamp > query.timestamp_to
        )

    def _matches_transition_filters(self, transition: StateTransition, query: StateQuery) -> bool:
        """Check if StateTransition matches query filters."""
        if query.key_id is not None and transition.entity_id != query.key_id:
            return False
        if query.state is not None and transition.to_state != query.state:
            return False
        if (
            query.timestamp_from is not None
            and transition.transition_timestamp < query.timestamp_from
        ):
            return False
        return not (
            query.timestamp_to is not None and transition.transition_timestamp > query.timestamp_to
        )
