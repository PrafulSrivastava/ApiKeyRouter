"""Redis-based state store implementation.

This module provides a Redis implementation of the StateStore interface
for distributed state management across multiple proxy instances.

Example:
    ```python
    import os
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"

    from apikeyrouter.infrastructure.state_store.redis_store import RedisStateStore
    from apikeyrouter.domain.models.api_key import APIKey

    # Create store instance
    store = RedisStateStore()

    # Save a key
    key = APIKey(id="key1", key_material="encrypted_key", provider_id="openai")
    await store.save_key(key)

    # Retrieve a key
    retrieved_key = await store.get_key("key1")
    ```
"""

import asyncio
import contextlib
import json
import os
from typing import Any

import structlog
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import ConnectionError, RedisError, TimeoutError

from apikeyrouter.domain.interfaces.state_store import (
    StateQuery,
    StateStore,
    StateStoreError,
)
from apikeyrouter.domain.models.api_key import APIKey
from apikeyrouter.domain.models.quota_state import QuotaState
from apikeyrouter.domain.models.routing_decision import RoutingDecision
from apikeyrouter.domain.models.state_transition import StateTransition
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore

logger = structlog.get_logger(__name__)

# Redis key patterns
KEY_PATTERN_APIKEY = "apikey:{key_id}"
KEY_PATTERN_QUOTA = "quota:{key_id}"
KEY_PATTERN_DECISION = "decision:{correlation_id}"
KEY_PATTERN_TRANSITIONS = "transitions:{key_id}"

# Default TTL values (in seconds)
DEFAULT_KEY_TTL = 7 * 24 * 60 * 60  # 7 days
DEFAULT_DECISION_TTL = 24 * 60 * 60  # 24 hours
DEFAULT_MAX_TRANSITIONS = 1000  # Maximum transitions per key


class RedisStateStore(StateStore):  # type: ignore[misc]
    """Redis-based implementation of StateStore interface.

    Provides distributed state storage using Redis for multi-instance deployments.
    Supports connection pooling, automatic fallback to in-memory store on failure,
    and state reconciliation for data consistency.

    Thread Safety:
        - All operations are async and thread-safe via Redis connection pool
        - Connection pool handles concurrent access

    Performance:
        - All operations use async Redis client
        - Connection pooling for efficient resource usage
        - TTL-based automatic cleanup

    Attributes:
        _redis: Redis async client instance
        _connection_pool: Redis connection pool
        _fallback_store: InMemoryStateStore used when Redis is unavailable
        _use_fallback: Flag indicating if fallback mode is active
        _key_ttl: TTL for API key records (default: 7 days)
        _decision_ttl: TTL for routing decision records (default: 24 hours)
        _max_transitions: Maximum number of transitions per key (default: 1000)
        _reconciliation_task: Background task for state reconciliation
        _reconciliation_interval: Interval between reconciliation runs (default: 60s)
    """

    def __init__(
        self,
        redis_url: str | None = None,
        key_ttl: int = DEFAULT_KEY_TTL,
        decision_ttl: int = DEFAULT_DECISION_TTL,
        max_transitions: int = DEFAULT_MAX_TRANSITIONS,
        connection_timeout: int = 5,
        reconciliation_interval: int = 60,
        enable_reconciliation: bool = True,
    ) -> None:
        """Initialize RedisStateStore with connection configuration.

        Args:
            redis_url: Redis connection URL. If None, reads from REDIS_URL environment variable.
                     If not provided and REDIS_URL not set, will use fallback mode.
            key_ttl: TTL for API key records in seconds (default: 7 days).
            decision_ttl: TTL for routing decision records in seconds (default: 24 hours).
            max_transitions: Maximum number of state transitions to store per key (default: 1000).
            connection_timeout: Connection timeout in seconds (default: 5).
            reconciliation_interval: Interval between state reconciliation runs in seconds (default: 60).
            enable_reconciliation: Whether to enable background state reconciliation (default: True).

        Example:
            ```python
            # From environment variable
            store = RedisStateStore()

            # With explicit URL
            store = RedisStateStore(redis_url="redis://localhost:6379/0")

            # With custom TTL
            store = RedisStateStore(key_ttl=86400, decision_ttl=3600)
            ```
        """
        # Get Redis URL from parameter or environment
        self._redis_url = redis_url or os.getenv("REDIS_URL")
        self._key_ttl = key_ttl
        self._decision_ttl = decision_ttl
        self._max_transitions = max_transitions
        self._connection_timeout = connection_timeout
        self._reconciliation_interval = reconciliation_interval
        self._enable_reconciliation = enable_reconciliation

        # Initialize Redis connection
        self._redis: Redis | None = None
        self._connection_pool: ConnectionPool | None = None
        self._use_fallback = False
        self._fallback_store = InMemoryStateStore()

        # Background task for state reconciliation
        self._reconciliation_task: asyncio.Task[None] | None = None

        # Initialize connection if URL is provided
        if self._redis_url:
            try:
                self._connection_pool = ConnectionPool.from_url(
                    self._redis_url,
                    max_connections=10,
                    socket_connect_timeout=connection_timeout,
                    socket_timeout=connection_timeout,
                    retry_on_timeout=True,
                )
                self._redis = Redis(connection_pool=self._connection_pool)
            except Exception as e:
                logger.warning(
                    "Failed to initialize Redis connection, using fallback mode",
                    error=str(e),
                    redis_url=self._redis_url,
                )
                self._use_fallback = True
        else:
            logger.warning(
                "REDIS_URL not provided, using fallback in-memory store",
            )
            self._use_fallback = True

        # Start reconciliation task if enabled
        if self._enable_reconciliation and not self._use_fallback:
            self._reconciliation_task = asyncio.create_task(self._reconciliation_loop())

    async def _ensure_connection(self) -> None:
        """Ensure Redis connection is available, fallback if not.

        Checks Redis connection health and switches to fallback mode if unavailable.
        """
        if self._use_fallback:
            return

        if self._redis is None:
            self._use_fallback = True
            logger.warning("Redis connection not available, using fallback mode")
            return

        try:
            await self._redis.ping()
        except (ConnectionError, TimeoutError, RedisError) as e:
            if not self._use_fallback:
                logger.warning(
                    "Redis connection failed, switching to fallback mode",
                    error=str(e),
                )
            self._use_fallback = True

    async def save_key(self, key: APIKey) -> None:
        """Save an API key to the store.

        Persists an APIKey instance to Redis. If a key with the same ID
        already exists, it will be updated (upsert behavior).

        Args:
            key: The APIKey to save.

        Raises:
            StateStoreError: If save operation fails.

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
        await self._ensure_connection()

        if self._use_fallback:
            await self._fallback_store.save_key(key)
            return

        try:
            if self._redis is None:
                raise StateStoreError("Redis connection not available")
            redis_key = KEY_PATTERN_APIKEY.format(key_id=key.id)
            # Serialize APIKey to JSON
            key_json = key.model_dump_json()
            # Store with TTL
            await self._redis.setex(redis_key, self._key_ttl, key_json)
        except (ConnectionError, TimeoutError, RedisError) as e:
            logger.warning(
                "Failed to save key to Redis, using fallback",
                key_id=key.id,
                error=str(e),
            )
            await self._fallback_store.save_key(key)
            self._use_fallback = True
        except Exception as e:
            raise StateStoreError(f"Failed to save key {key.id}: {e}") from e

    async def get_key(self, key_id: str) -> APIKey | None:
        """Retrieve an API key by ID.

        Fetches an APIKey from Redis by its unique identifier.

        Args:
            key_id: The unique identifier of the key to retrieve.

        Returns:
            The APIKey if found, None if the key does not exist.

        Raises:
            StateStoreError: If retrieval operation fails.

        Example:
            ```python
            key = await store.get_key("key1")
            if key:
                print(f"Found key for provider: {key.provider_id}")
            ```
        """
        await self._ensure_connection()

        if self._use_fallback:
            return await self._fallback_store.get_key(key_id)

        try:
            if self._redis is None:
                raise StateStoreError("Redis connection not available")
            redis_key = KEY_PATTERN_APIKEY.format(key_id=key_id)
            key_json = await self._redis.get(redis_key)
            if key_json is None:
                return None
            # Deserialize from JSON
            key_dict = json.loads(key_json)
            return APIKey(**key_dict)
        except (ConnectionError, TimeoutError, RedisError) as e:
            logger.warning(
                "Failed to get key from Redis, using fallback",
                key_id=key_id,
                error=str(e),
            )
            self._use_fallback = True
            return await self._fallback_store.get_key(key_id)
        except Exception as e:
            raise StateStoreError(f"Failed to get key {key_id}: {e}") from e

    async def list_keys(self, provider_id: str | None = None) -> list[APIKey]:
        """List all API keys, optionally filtered by provider.

        Retrieves all API keys from Redis. If provider_id is provided,
        only returns keys for that provider.

        Args:
            provider_id: Optional provider ID to filter by. If None, returns all keys.

        Returns:
            List of APIKey objects matching the criteria.

        Raises:
            StateStoreError: If retrieval operation fails.

        Example:
            ```python
            # Get all keys
            all_keys = await store.list_keys()

            # Get only OpenAI keys
            openai_keys = await store.list_keys(provider_id="openai")
            ```
        """
        await self._ensure_connection()

        if self._use_fallback:
            return await self._fallback_store.list_keys(provider_id)  # type: ignore[no-any-return]

        try:
            if self._redis is None:
                raise StateStoreError("Redis connection not available")
            # Get all keys matching pattern
            pattern = KEY_PATTERN_APIKEY.format(key_id="*")
            keys: list[APIKey] = []
            async for redis_key in self._redis.scan_iter(match=pattern):
                key_json = await self._redis.get(redis_key)
                if key_json:
                    try:
                        key_dict = json.loads(key_json)
                        key = APIKey(**key_dict)
                        if provider_id is None or key.provider_id == provider_id:
                            keys.append(key)
                    except Exception:
                        # Skip invalid keys
                        continue
            return keys
        except (ConnectionError, TimeoutError, RedisError) as e:
            logger.warning(
                "Failed to list keys from Redis, using fallback",
                error=str(e),
            )
            self._use_fallback = True
            return await self._fallback_store.list_keys(provider_id)  # type: ignore[no-any-return]
        except Exception as e:
            raise StateStoreError(f"Failed to list keys: {e}") from e

    async def save_quota_state(self, state: QuotaState) -> None:
        """Save a QuotaState to the store.

        Persists a QuotaState instance to Redis. If a quota state for the
        same key_id already exists, it will be updated (upsert behavior).

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
        await self._ensure_connection()

        if self._use_fallback:
            await self._fallback_store.save_quota_state(state)
            return

        try:
            if self._redis is None:
                raise StateStoreError("Redis connection not available")
            redis_key = KEY_PATTERN_QUOTA.format(key_id=state.key_id)
            # Serialize QuotaState to JSON
            state_json = state.model_dump_json()
            # Store with TTL (use key TTL as quota state should match key lifetime)
            await self._redis.setex(redis_key, self._key_ttl, state_json)
        except (ConnectionError, TimeoutError, RedisError) as e:
            logger.warning(
                "Failed to save quota state to Redis, using fallback",
                key_id=state.key_id,
                error=str(e),
            )
            await self._fallback_store.save_quota_state(state)
            self._use_fallback = True
        except Exception as e:
            raise StateStoreError(
                f"Failed to save quota state for key {state.key_id}: {e}"
            ) from e

    async def get_quota_state(self, key_id: str) -> QuotaState | None:
        """Retrieve a QuotaState by key_id.

        Fetches the QuotaState associated with a specific API key.

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
        await self._ensure_connection()

        if self._use_fallback:
            return await self._fallback_store.get_quota_state(key_id)

        try:
            if self._redis is None:
                raise StateStoreError("Redis connection not available")
            redis_key = KEY_PATTERN_QUOTA.format(key_id=key_id)
            state_json = await self._redis.get(redis_key)
            if state_json is None:
                return None
            # Deserialize from JSON
            state_dict = json.loads(state_json)
            return QuotaState(**state_dict)
        except (ConnectionError, TimeoutError, RedisError) as e:
            logger.warning(
                "Failed to get quota state from Redis, using fallback",
                key_id=key_id,
                error=str(e),
            )
            self._use_fallback = True
            return await self._fallback_store.get_quota_state(key_id)
        except Exception as e:
            raise StateStoreError(f"Failed to get quota state for key {key_id}: {e}") from e

    async def save_routing_decision(self, decision: RoutingDecision) -> None:
        """Save a routing decision to the audit trail.

        Persists a RoutingDecision instance to Redis for audit and
        observability purposes. Routing decisions are append-only
        and retained for analysis.

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
        await self._ensure_connection()

        if self._use_fallback:
            await self._fallback_store.save_routing_decision(decision)
            return

        try:
            if self._redis is None:
                raise StateStoreError("Redis connection not available")
            # Use decision.id as correlation_id (or request_id if id not available)
            correlation_id = decision.id or decision.request_id
            redis_key = KEY_PATTERN_DECISION.format(correlation_id=correlation_id)
            # Serialize RoutingDecision to JSON
            decision_json = decision.model_dump_json()
            # Store with TTL
            await self._redis.setex(redis_key, self._decision_ttl, decision_json)
        except (ConnectionError, TimeoutError, RedisError) as e:
            logger.warning(
                "Failed to save routing decision to Redis, using fallback",
                decision_id=decision.id,
                error=str(e),
            )
            await self._fallback_store.save_routing_decision(decision)
            self._use_fallback = True
        except Exception as e:
            raise StateStoreError(
                f"Failed to save routing decision {decision.id}: {e}"
            ) from e

    async def save_state_transition(self, transition: StateTransition) -> None:
        """Save a state transition to the audit trail.

        Persists a StateTransition instance to Redis for audit and
        debugging purposes. State transitions are append-only and provide
        a complete history of state changes.

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
        await self._ensure_connection()

        if self._use_fallback:
            await self._fallback_store.save_state_transition(transition)
            return

        try:
            if self._redis is None:
                raise StateStoreError("Redis connection not available")
            redis_key = KEY_PATTERN_TRANSITIONS.format(key_id=transition.entity_id)
            # Serialize StateTransition to JSON
            transition_json = transition.model_dump_json()
            # Store in Redis list (append-only)
            await self._redis.lpush(redis_key, transition_json)  # type: ignore[misc]
            # Trim list to max_transitions (keep most recent)
            await self._redis.ltrim(redis_key, 0, self._max_transitions - 1)  # type: ignore[misc]
        except (ConnectionError, TimeoutError, RedisError) as e:
            logger.warning(
                "Failed to save state transition to Redis, using fallback",
                entity_id=transition.entity_id,
                error=str(e),
            )
            await self._fallback_store.save_state_transition(transition)
            self._use_fallback = True
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
        await self._ensure_connection()

        if self._use_fallback:
            fallback_results = await self._fallback_store.query_state(query)
            return list(fallback_results)

        try:
            if self._redis is None:
                raise StateStoreError("Redis connection not available")
            results: list[Any] = []

            # Query APIKeys
            if query.entity_type == "APIKey" or query.entity_type is None:
                pattern = KEY_PATTERN_APIKEY.format(key_id="*")
                async for redis_key in self._redis.scan_iter(match=pattern):
                    key_json = await self._redis.get(redis_key)
                    if key_json:
                        try:
                            key_dict = json.loads(key_json)
                            key = APIKey(**key_dict)
                            if self._matches_key_filters(key, query):
                                results.append(key)
                        except Exception:
                            continue

            # Query QuotaStates
            if query.entity_type == "QuotaState" or query.entity_type is None:
                pattern = KEY_PATTERN_QUOTA.format(key_id="*")
                async for redis_key in self._redis.scan_iter(match=pattern):
                    state_json = await self._redis.get(redis_key)
                    if state_json:
                        try:
                            state_dict = json.loads(state_json)
                            quota_state = QuotaState(**state_dict)
                            if self._matches_quota_filters(quota_state, query):
                                results.append(quota_state)
                        except Exception:
                            continue

            # Query RoutingDecisions
            if query.entity_type == "RoutingDecision" or query.entity_type is None:
                pattern = KEY_PATTERN_DECISION.format(correlation_id="*")
                async for redis_key in self._redis.scan_iter(match=pattern):
                    decision_json = await self._redis.get(redis_key)
                    if decision_json:
                        try:
                            decision_dict = json.loads(decision_json)
                            decision = RoutingDecision(**decision_dict)
                            if self._matches_decision_filters(decision, query):
                                results.append(decision)
                        except Exception:
                            continue

            # Query StateTransitions
            if query.entity_type == "StateTransition" or query.entity_type is None:
                pattern = KEY_PATTERN_TRANSITIONS.format(key_id="*")
                async for redis_key in self._redis.scan_iter(match=pattern):
                    transitions_json: list[bytes] = await self._redis.lrange(redis_key, 0, -1)  # type: ignore[misc]
                    for transition_json in transitions_json:
                        try:
                            transition_dict = json.loads(transition_json)
                            transition = StateTransition(**transition_dict)
                            if self._matches_transition_filters(transition, query):
                                results.append(transition)
                        except Exception:
                            continue

            # Apply pagination
            if query.offset is not None:
                results = results[query.offset :]
            if query.limit is not None:
                results = results[: query.limit]

            return results
        except (ConnectionError, TimeoutError, RedisError) as e:
            logger.warning(
                "Failed to query state from Redis, using fallback",
                error=str(e),
            )
            self._use_fallback = True
            fallback_results = await self._fallback_store.query_state(query)
            return list(fallback_results)
        except Exception as e:
            raise StateStoreError(f"Failed to query state: {e}") from e

    async def check_connection(self) -> bool:
        """Check if Redis connection is healthy.

        Pings Redis server to verify connection health.

        Returns:
            True if connection is healthy, False otherwise.

        Example:
            ```python
            is_healthy = await store.check_connection()
            if not is_healthy:
                logger.warning("Redis connection unhealthy")
            ```
        """
        if self._use_fallback or self._redis is None:
            return False

        try:
            await self._redis.ping()
            return True
        except (ConnectionError, TimeoutError, RedisError):
            return False
        except Exception:
            return False

    async def _reconciliation_loop(self) -> None:
        """Background task for state reconciliation.

        Periodically checks Redis state consistency, reconciles key states
        across instances, and handles stale state cleanup.
        """
        while True:
            try:
                await asyncio.sleep(self._reconciliation_interval)
                if self._use_fallback or self._redis is None:
                    continue

                await self._reconcile_state()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Error in state reconciliation loop",
                    error=str(e),
                )

    async def _reconcile_state(self) -> None:
        """Reconcile state consistency across instances.

        Checks for stale state, cleans up expired records, and ensures
        consistency between key states and quota states.
        """
        if self._use_fallback or self._redis is None:
            return

        try:
            # Get all keys
            pattern = KEY_PATTERN_APIKEY.format(key_id="*")
            key_ids: set[str] = set()
            async for redis_key in self._redis.scan_iter(match=pattern):
                # Extract key_id from redis_key (format: "apikey:{key_id}")
                key_id = redis_key.decode().split(":", 1)[1] if ":" in redis_key.decode() else None
                if key_id:
                    key_ids.add(key_id)

            # Check quota states match keys
            quota_pattern = KEY_PATTERN_QUOTA.format(key_id="*")
            async for redis_key in self._redis.scan_iter(match=quota_pattern):
                key_id = redis_key.decode().split(":", 1)[1] if ":" in redis_key.decode() else None
                if key_id and key_id not in key_ids:
                    # Orphaned quota state - clean up
                    await self._redis.delete(redis_key)
                    logger.debug("Cleaned up orphaned quota state", key_id=key_id)

            # Clean up expired transitions (older than key TTL)
            transition_pattern = KEY_PATTERN_TRANSITIONS.format(key_id="*")
            async for redis_key in self._redis.scan_iter(match=transition_pattern):
                # Check if corresponding key exists
                key_id = redis_key.decode().split(":", 1)[1] if ":" in redis_key.decode() else None
                if key_id and key_id not in key_ids:
                    # No corresponding key - clean up transitions
                    await self._redis.delete(redis_key)
                    logger.debug("Cleaned up orphaned transitions", key_id=key_id)

        except Exception as e:
            logger.warning(
                "Error during state reconciliation",
                error=str(e),
            )

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
        if (
            query.timestamp_from is not None
            and decision.decision_timestamp < query.timestamp_from
        ):
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
            query.timestamp_to is not None
            and transition.transition_timestamp > query.timestamp_to
        )

    async def close(self) -> None:
        """Close Redis connection and cleanup resources.

        Should be called when the store is no longer needed to properly
        clean up connections and background tasks.
        """
        # Cancel reconciliation task
        if self._reconciliation_task and not self._reconciliation_task.done():
            self._reconciliation_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconciliation_task

        # Close Redis connection
        if self._redis:
            await self._redis.close()
        if self._connection_pool:
            await self._connection_pool.disconnect()

