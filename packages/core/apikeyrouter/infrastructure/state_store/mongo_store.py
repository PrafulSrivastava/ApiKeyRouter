"""MongoDB state store implementation.

This module provides a MongoDB-backed implementation of the StateStore interface
using motor (async MongoDB driver) and beanie (Pydantic-based ODM). It supports
production deployments with persistent state storage and audit trails.

Example:
    ```python
    import os
    os.environ["MONGODB_URL"] = "mongodb://localhost:27017"

    from apikeyrouter.infrastructure.state_store.mongo_store import MongoStateStore
    from apikeyrouter.domain.models.api_key import APIKey

    # Create store instance
    store = MongoStateStore()

    # Ensure connection is established
    await store.initialize()

    # Save a key
    key = APIKey(id="key1", key_material="encrypted_key", provider_id="openai")
    await store.save_key(key)

    # Retrieve a key
    retrieved_key = await store.get_key("key1")
    ```
"""

import os
from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import (
    ConfigurationError,
    ConnectionFailure,
    NetworkTimeout,
    OperationFailure,
    ServerSelectionTimeoutError,
)

from apikeyrouter.domain.interfaces.state_store import (
    StateQuery,
    StateStore,
    StateStoreError,
)
from apikeyrouter.domain.models.api_key import APIKey
from apikeyrouter.domain.models.quota_state import QuotaState
from apikeyrouter.domain.models.routing_decision import RoutingDecision
from apikeyrouter.domain.models.state_transition import StateTransition
from apikeyrouter.infrastructure.state_store.mongo_models import (
    APIKeyDocument,
    QuotaStateDocument,
    RoutingDecisionDocument,
    StateTransitionDocument,
    initialize_beanie_models,
)

logger = structlog.get_logger(__name__)


class MongoStateStore(StateStore):
    """MongoDB implementation of StateStore interface.

    Provides persistent state storage using MongoDB with motor (async driver)
    and beanie (Pydantic-based ODM). This implementation supports production
    deployments with full state persistence and audit trails.

    Connection Configuration:
        - Connection string from MONGODB_URL environment variable
        - Connection pooling configured via motor client options
        - Health check via ping operation

    Error Handling:
        - Connection errors raise StateStoreError with appropriate context
        - Authentication errors are handled gracefully
        - Network errors are logged and re-raised

    Attributes:
        _client: AsyncIOMotorClient instance for MongoDB connection
        _database_name: Name of the MongoDB database to use
        _initialized: Whether the connection has been initialized
    """

    def __init__(
        self,
        connection_url: str | None = None,
        database_name: str = "apikeyrouter",
        max_pool_size: int = 100,
        min_pool_size: int = 10,
        connect_timeout_ms: int = 20000,
        server_selection_timeout_ms: int = 5000,
    ) -> None:
        """Initialize MongoStateStore with connection configuration.

        Args:
            connection_url: MongoDB connection string. If None, reads from
                           MONGODB_URL environment variable.
            database_name: Name of the MongoDB database to use. Default is "apikeyrouter".
            max_pool_size: Maximum number of connections in the pool. Default is 100.
            min_pool_size: Minimum number of connections in the pool. Default is 10.
            connect_timeout_ms: Connection timeout in milliseconds. Default is 20000 (20s).
            server_selection_timeout_ms: Server selection timeout in milliseconds.
                                        Default is 5000 (5s).

        Raises:
            StateStoreError: If connection URL is missing or invalid.
        """
        # Get connection URL from parameter or environment variable
        if connection_url is None:
            connection_url = os.getenv("MONGODB_URL")
            if connection_url is None:
                raise StateStoreError(
                    "MongoDB connection URL not provided. Set MONGODB_URL environment variable or pass connection_url parameter."
                )

        self._connection_url = connection_url
        self._database_name = database_name
        self._initialized = False

        # Parse connection string and configure client
        try:
            # Create motor client with connection pooling configuration
            self._client: AsyncIOMotorClient | None = AsyncIOMotorClient(
                connection_url,
                maxPoolSize=max_pool_size,
                minPoolSize=min_pool_size,
                connectTimeoutMS=connect_timeout_ms,
                serverSelectionTimeoutMS=server_selection_timeout_ms,
            )
            logger.info(
                "MongoDB client created",
                database=database_name,
                max_pool_size=max_pool_size,
                min_pool_size=min_pool_size,
            )
        except (ConfigurationError, ValueError) as e:
            error_msg = f"Invalid MongoDB connection URL: {e}"
            logger.error("mongodb_connection_error", error=error_msg)
            raise StateStoreError(error_msg) from e

    async def initialize(self) -> None:
        """Initialize MongoDB connection and verify connectivity.

        Establishes connection to MongoDB, performs a health check, and
        initializes Beanie with all document models. This method should be
        called before using the store.

        Raises:
            StateStoreError: If connection fails or health check fails.
        """
        if self._initialized:
            return

        if self._client is None:
            raise StateStoreError("MongoDB client not initialized")

        try:
            # Perform health check by pinging the server
            await self._client.admin.command("ping")

            # Initialize Beanie with document models
            database = self._client[self._database_name]
            await initialize_beanie_models(database)

            self._initialized = True
            logger.info(
                "MongoDB connection established and Beanie initialized",
                database=self._database_name,
            )
        except (ConnectionFailure, ServerSelectionTimeoutError, NetworkTimeout) as e:
            error_msg = f"Failed to connect to MongoDB: {e}"
            logger.error("mongodb_connection_failure", error=error_msg)
            raise StateStoreError(error_msg) from e
        except OperationFailure as e:
            # Check if it's an authentication error (error code 18)
            if e.code == 18 or "authentication" in str(e).lower():
                error_msg = f"MongoDB authentication failed: {e}"
                logger.error("mongodb_authentication_failure", error=error_msg)
                raise StateStoreError(error_msg) from e
            # Re-raise other operation failures
            raise
        except Exception as e:
            error_msg = f"Unexpected error during MongoDB initialization: {e}"
            logger.error("mongodb_initialization_error", error=error_msg)
            raise StateStoreError(error_msg) from e

    async def check_connection(self) -> bool:
        """Check if MongoDB connection is healthy.

        Performs a ping operation to verify the connection is still active.

        Returns:
            True if connection is healthy, False otherwise.
        """
        if self._client is None:
            return False

        try:
            await self._client.admin.command("ping")
            return True
        except Exception as e:
            logger.warning("mongodb_health_check_failed", error=str(e))
            return False

    async def close(self) -> None:
        """Close MongoDB connection and cleanup resources.

        Closes the motor client connection and releases all resources.
        Should be called when the store is no longer needed.
        """
        if self._client is not None:
            self._client.close()
            self._initialized = False
            logger.info("MongoDB connection closed")

    async def save_key(self, key: APIKey) -> None:
        """Save an API key to MongoDB using Beanie.

        Persists an APIKey instance to MongoDB using Beanie ODM. If a key
        with the same ID already exists, it will be updated (upsert behavior).

        Args:
            key: The APIKey to save.

        Raises:
            StateStoreError: If save operation fails.
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Convert domain model to Beanie document
            doc = APIKeyDocument.from_domain_model(key)
            # Check if document exists
            existing_doc = await APIKeyDocument.get(key.id)
            if existing_doc is not None:
                # Update existing document
                await doc.replace()
            else:
                # Insert new document
                await doc.insert()
        except Exception as e:
            error_msg = f"Failed to save key {key.id}: {e}"
            logger.error("mongodb_save_key_error", key_id=key.id, error=error_msg)
            raise StateStoreError(error_msg) from e

    async def get_key(self, key_id: str) -> APIKey | None:
        """Retrieve an API key by ID from MongoDB using Beanie.

        Fetches an APIKey from MongoDB by its unique identifier using Beanie ODM.
        Uses the key_id index for fast lookups.

        Args:
            key_id: The unique identifier of the key to retrieve.

        Returns:
            The APIKey if found, None if the key does not exist.

        Raises:
            StateStoreError: If retrieval operation fails.
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Use Beanie get() method which uses the id index
            doc = await APIKeyDocument.get(key_id)
            if doc is None:
                return None
            # Convert Beanie document to domain model
            return doc.to_domain_model()
        except Exception as e:
            error_msg = f"Failed to get key {key_id}: {e}"
            logger.error("mongodb_get_key_error", key_id=key_id, error=error_msg)
            raise StateStoreError(error_msg) from e

    async def list_keys(self, provider_id: str | None = None) -> list[APIKey]:
        """List all API keys, optionally filtered by provider.

        Retrieves all API keys from MongoDB. If provider_id is provided,
        only returns keys for that provider.

        Args:
            provider_id: Optional provider ID to filter by. If None, returns all keys.

        Returns:
            List of APIKey objects matching the criteria.

        Raises:
            StateStoreError: If retrieval operation fails.
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Use Beanie to query documents
            if provider_id is None:
                docs = await APIKeyDocument.find_all().to_list()
            else:
                docs = await APIKeyDocument.find(
                    APIKeyDocument.provider_id == provider_id
                ).to_list()

            # Convert documents to domain models
            keys = [doc.to_domain_model() for doc in docs]
            return keys
        except Exception as e:
            error_msg = f"Failed to list keys: {e}"
            logger.error("mongodb_list_keys_error", error=error_msg)
            raise StateStoreError(error_msg) from e

    async def save_quota_state(self, state: QuotaState) -> None:
        """Save a QuotaState to MongoDB using Beanie.

        Persists a QuotaState instance to MongoDB using Beanie ODM. If a quota
        state for the same key_id already exists, it will be updated (upsert
        behavior). Uses MongoDB atomic operations for concurrent updates.

        Args:
            state: The QuotaState to save.

        Raises:
            StateStoreError: If save operation fails.
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Convert domain model to Beanie document
            doc = QuotaStateDocument.from_domain_model(state)
            # Check if document exists by key_id (unique index)
            existing_doc = await QuotaStateDocument.find_one(
                QuotaStateDocument.key_id == state.key_id
            )
            if existing_doc is not None:
                # Update existing document (atomic operation)
                doc.id = existing_doc.id  # Preserve the document ID
                await doc.replace()
            else:
                # Insert new document
                await doc.insert()
        except Exception as e:
            error_msg = f"Failed to save quota state for key {state.key_id}: {e}"
            logger.error("mongodb_save_quota_error", key_id=state.key_id, error=error_msg)
            raise StateStoreError(error_msg) from e

    async def get_quota_state(self, key_id: str) -> QuotaState | None:
        """Retrieve a QuotaState by key_id from MongoDB using Beanie.

        Fetches the QuotaState associated with a specific API key using Beanie ODM.
        Uses the key_id unique index for fast lookups.

        Args:
            key_id: The unique identifier of the key this quota state belongs to.

        Returns:
            The QuotaState if found, None if no quota state exists for this key.

        Raises:
            StateStoreError: If retrieval operation fails.
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Use Beanie find_one() with key_id index
            doc = await QuotaStateDocument.find_one(QuotaStateDocument.key_id == key_id)
            if doc is None:
                return None
            # Convert Beanie document to domain model
            return doc.to_domain_model()
        except Exception as e:
            error_msg = f"Failed to get quota state for key {key_id}: {e}"
            logger.error("mongodb_get_quota_error", key_id=key_id, error=error_msg)
            raise StateStoreError(error_msg) from e

    async def save_routing_decision(self, decision: RoutingDecision) -> None:
        """Save a routing decision to MongoDB using Beanie.

        Persists a RoutingDecision instance to MongoDB using Beanie ODM for audit
        and observability purposes. Routing decisions are append-only (insert only).

        Args:
            decision: The RoutingDecision to save.

        Raises:
            StateStoreError: If save operation fails.
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Convert domain model to Beanie document
            doc = RoutingDecisionDocument.from_domain_model(decision)
            # Use Beanie insert() for append-only audit trail
            await doc.insert()
        except Exception as e:
            error_msg = f"Failed to save routing decision {decision.id}: {e}"
            logger.error("mongodb_save_decision_error", decision_id=decision.id, error=error_msg)
            raise StateStoreError(error_msg) from e

    async def save_state_transition(self, transition: StateTransition) -> None:
        """Save a state transition to MongoDB using Beanie.

        Persists a StateTransition instance to MongoDB using Beanie ODM for audit
        and debugging purposes. State transitions are append-only (insert only).

        Args:
            transition: The StateTransition to save.

        Raises:
            StateStoreError: If save operation fails.
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Convert domain model to Beanie document
            doc = StateTransitionDocument.from_domain_model(transition)
            # Use Beanie insert() for append-only audit trail
            await doc.insert()
        except Exception as e:
            error_msg = (
                f"Failed to save state transition for {transition.entity_type}:"
                f"{transition.entity_id}: {e}"
            )
            logger.error(
                "mongodb_save_transition_error",
                entity_type=transition.entity_type,
                entity_id=transition.entity_id,
                error=error_msg,
            )
            raise StateStoreError(error_msg) from e

    async def query_state(self, query: StateQuery) -> list[Any]:
        """Query state objects from MongoDB based on filter criteria.

        Provides a flexible query interface for retrieving state objects
        (APIKey, QuotaState, RoutingDecision, StateTransition) based on
        various filter criteria.

        Args:
            query: StateQuery object containing filter criteria and pagination options.

        Returns:
            List of matching state objects.

        Raises:
            StateStoreError: If query operation fails.
        """
        if not self._initialized:
            await self.initialize()

        try:
            results: list[Any] = []
            self._client[self._database_name]

            # Build MongoDB query filter
            mongo_filter: dict[str, Any] = {}
            if query.key_id is not None:
                mongo_filter["key_id"] = query.key_id
            if query.provider_id is not None:
                mongo_filter["provider_id"] = query.provider_id
            if query.state is not None:
                mongo_filter["state"] = query.state
            if query.timestamp_from is not None or query.timestamp_to is not None:
                timestamp_filter: dict[str, Any] = {}
                if query.timestamp_from is not None:
                    timestamp_filter["$gte"] = query.timestamp_from
                if query.timestamp_to is not None:
                    timestamp_filter["$lte"] = query.timestamp_to
                if timestamp_filter:
                    # Determine timestamp field based on entity type
                    if query.entity_type == "APIKey":
                        mongo_filter["created_at"] = timestamp_filter
                    elif query.entity_type == "QuotaState":
                        mongo_filter["updated_at"] = timestamp_filter
                    elif query.entity_type == "RoutingDecision":
                        mongo_filter["decision_timestamp"] = timestamp_filter
                    elif query.entity_type == "StateTransition":
                        mongo_filter["transition_timestamp"] = timestamp_filter

            # Query based on entity type
            if query.entity_type == "APIKey" or query.entity_type is None:
                # Use Beanie for APIKey queries (supports indexes)
                key_filter: dict[str, Any] = {}
                if query.key_id is not None:
                    key_filter["id"] = query.key_id
                if query.provider_id is not None:
                    key_filter["provider_id"] = query.provider_id
                if query.state is not None:
                    key_filter["state"] = query.state
                # For timestamp queries, use created_at field
                if query.timestamp_from is not None or query.timestamp_to is not None:
                    timestamp_filter: dict[str, Any] = {}
                    if query.timestamp_from is not None:
                        timestamp_filter["$gte"] = query.timestamp_from
                    if query.timestamp_to is not None:
                        timestamp_filter["$lte"] = query.timestamp_to
                    if timestamp_filter:
                        key_filter["created_at"] = timestamp_filter

                # Build Beanie query
                # Beanie find() accepts a dict, but we need to use the correct field names
                # For id field, use the document's id field directly
                if "id" in key_filter:
                    # Use Beanie's find with id field
                    beanie_query = APIKeyDocument.find(APIKeyDocument.id == key_filter["id"])
                    # Remove id from filter for other conditions
                    other_filters = {k: v for k, v in key_filter.items() if k != "id"}
                    for field, value in other_filters.items():
                        beanie_query = beanie_query.find(getattr(APIKeyDocument, field) == value)
                else:
                    beanie_query = APIKeyDocument.find(key_filter)
                if query.limit is not None:
                    beanie_query = beanie_query.limit(query.limit)
                if query.offset is not None:
                    beanie_query = beanie_query.skip(query.offset)

                # Execute query and convert to domain models
                docs = await beanie_query.to_list()
                for doc in docs:
                    results.append(doc.to_domain_model())

            if query.entity_type == "QuotaState" or query.entity_type is None:
                # Use Beanie for QuotaState queries (supports reset_at index)
                quota_filter = {}
                if query.key_id is not None:
                    quota_filter["key_id"] = query.key_id
                # For time-window queries, use reset_at field
                if query.timestamp_from is not None or query.timestamp_to is not None:
                    reset_at_filter: dict[str, Any] = {}
                    if query.timestamp_from is not None:
                        reset_at_filter["$gte"] = query.timestamp_from
                    if query.timestamp_to is not None:
                        reset_at_filter["$lte"] = query.timestamp_to
                    if reset_at_filter:
                        quota_filter["reset_at"] = reset_at_filter

                # Build Beanie query
                beanie_query = QuotaStateDocument.find(quota_filter)
                if query.limit is not None:
                    beanie_query = beanie_query.limit(query.limit)
                if query.offset is not None:
                    beanie_query = beanie_query.skip(query.offset)

                # Execute query and convert to domain models
                docs = await beanie_query.to_list()
                for doc in docs:
                    results.append(doc.to_domain_model())

            if query.entity_type == "RoutingDecision" or query.entity_type is None:
                # Use Beanie for RoutingDecision queries (supports timestamp indexes)
                decision_filter: dict[str, Any] = {}
                if query.key_id is not None:
                    decision_filter["selected_key_id"] = query.key_id
                if query.provider_id is not None:
                    decision_filter["selected_provider_id"] = query.provider_id
                # For time-range queries, use decision_timestamp field
                if query.timestamp_from is not None or query.timestamp_to is not None:
                    timestamp_filter: dict[str, Any] = {}
                    if query.timestamp_from is not None:
                        timestamp_filter["$gte"] = query.timestamp_from
                    if query.timestamp_to is not None:
                        timestamp_filter["$lte"] = query.timestamp_to
                    if timestamp_filter:
                        decision_filter["decision_timestamp"] = timestamp_filter

                # Build Beanie query
                beanie_query = RoutingDecisionDocument.find(decision_filter)
                if query.limit is not None:
                    beanie_query = beanie_query.limit(query.limit)
                if query.offset is not None:
                    beanie_query = beanie_query.skip(query.offset)

                # Execute query and convert to domain models
                docs = await beanie_query.to_list()
                for doc in docs:
                    results.append(doc.to_domain_model())

            if query.entity_type == "StateTransition" or query.entity_type is None:
                # Use Beanie for StateTransition queries (supports timestamp indexes)
                transition_filter: dict[str, Any] = {}
                if query.key_id is not None:
                    transition_filter["entity_id"] = query.key_id
                if query.state is not None:
                    transition_filter["to_state"] = query.state
                # For time-range queries, use transition_timestamp field
                if query.timestamp_from is not None or query.timestamp_to is not None:
                    timestamp_filter: dict[str, Any] = {}
                    if query.timestamp_from is not None:
                        timestamp_filter["$gte"] = query.timestamp_from
                    if query.timestamp_to is not None:
                        timestamp_filter["$lte"] = query.timestamp_to
                    if timestamp_filter:
                        transition_filter["transition_timestamp"] = timestamp_filter

                # Build Beanie query
                beanie_query = StateTransitionDocument.find(transition_filter)
                if query.limit is not None:
                    beanie_query = beanie_query.limit(query.limit)
                if query.offset is not None:
                    beanie_query = beanie_query.skip(query.offset)

                # Execute query and convert to domain models
                docs = await beanie_query.to_list()
                for doc in docs:
                    results.append(doc.to_domain_model())

            return results
        except Exception as e:
            error_msg = f"Failed to query state: {e}"
            logger.error("mongodb_query_error", error=error_msg)
            raise StateStoreError(error_msg) from e
