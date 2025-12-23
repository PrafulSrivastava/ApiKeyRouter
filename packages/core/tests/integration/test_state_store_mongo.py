"""Integration tests for MongoDB state store connection and configuration."""

import os
from unittest.mock import AsyncMock, patch

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import (
    ConfigurationError,
    ConnectionFailure,
    NetworkTimeout,
    OperationFailure,
    ServerSelectionTimeoutError,
)

from apikeyrouter.domain.interfaces.state_store import StateStoreError
from apikeyrouter.infrastructure.state_store.mongo_store import MongoStateStore


@pytest.fixture
def mongodb_url() -> str:
    """Get MongoDB connection URL from environment or use default."""
    url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    return url


@pytest.fixture
async def mongo_store(mongodb_url: str) -> MongoStateStore:
    """Create MongoStateStore instance for testing."""
    # Check if MongoDB is available
    try:
        client = AsyncIOMotorClient(mongodb_url, serverSelectionTimeoutMS=2000)
        await client.admin.command("ping")
        client.close()
    except Exception:
        pytest.skip(
            "MongoDB is not available. Start MongoDB with 'docker-compose up -d' or set MONGODB_URL"
        )

    return MongoStateStore(
        connection_url=mongodb_url,
        database_name="test_apikeyrouter",
        max_pool_size=50,
        min_pool_size=5,
        connect_timeout_ms=10000,
        server_selection_timeout_ms=3000,
    )


@pytest.mark.asyncio
async def test_mongodb_connection_established(mongo_store: MongoStateStore):
    """Test that MongoDB connection can be established."""
    # Act
    await mongo_store.initialize()

    # Assert
    assert mongo_store._initialized is True
    assert mongo_store._client is not None

    # Cleanup
    await mongo_store.close()


@pytest.mark.asyncio
async def test_connection_string_from_environment_variable():
    """Test that connection string is read from MONGODB_URL environment variable."""
    # Arrange
    test_url = "mongodb://test-host:27017"
    os.environ["MONGODB_URL"] = test_url

    try:
        # Act
        store = MongoStateStore()

        # Assert
        assert store._connection_url == test_url
    finally:
        # Cleanup
        if "MONGODB_URL" in os.environ:
            del os.environ["MONGODB_URL"]


@pytest.mark.asyncio
async def test_connection_string_from_parameter():
    """Test that connection string can be passed as parameter."""
    # Arrange
    test_url = "mongodb://custom-host:27017"

    # Act
    store = MongoStateStore(connection_url=test_url)

    # Assert
    assert store._connection_url == test_url

    # Cleanup
    await store.close()


@pytest.mark.asyncio
async def test_missing_connection_url_raises_error():
    """Test that missing connection URL raises StateStoreError."""
    # Arrange
    if "MONGODB_URL" in os.environ:
        del os.environ["MONGODB_URL"]

    # Act & Assert
    with pytest.raises(StateStoreError, match="MongoDB connection URL not provided"):
        MongoStateStore()


@pytest.mark.asyncio
async def test_connection_pooling_configured(mongo_store: MongoStateStore):
    """Test that connection pooling is configured correctly."""
    # Arrange
    max_pool_size = 100
    min_pool_size = 10
    connect_timeout_ms = 20000
    server_selection_timeout_ms = 5000

    store = MongoStateStore(
        connection_url=mongo_store._connection_url,
        max_pool_size=max_pool_size,
        min_pool_size=min_pool_size,
        connect_timeout_ms=connect_timeout_ms,
        server_selection_timeout_ms=server_selection_timeout_ms,
    )

    # Act
    await store.initialize()

    # Assert
    assert store._client is not None
    # Verify client options (motor doesn't expose these directly, but we can verify client exists)
    assert isinstance(store._client, AsyncIOMotorClient)

    # Cleanup
    await store.close()


@pytest.mark.asyncio
async def test_health_check_returns_true_when_connected(mongo_store: MongoStateStore):
    """Test that health check returns True when connection is healthy."""
    # Arrange
    await mongo_store.initialize()

    # Act
    is_healthy = await mongo_store.check_connection()

    # Assert
    assert is_healthy is True

    # Cleanup
    await mongo_store.close()


@pytest.mark.asyncio
async def test_health_check_returns_false_when_not_connected():
    """Test that health check returns False when connection is not established."""
    # Arrange
    store = MongoStateStore(connection_url="mongodb://invalid-host:27017")

    # Act
    is_healthy = await store.check_connection()

    # Assert
    assert is_healthy is False

    # Cleanup
    await store.close()


@pytest.mark.asyncio
async def test_health_check_returns_false_when_client_is_none():
    """Test that health check returns False when client is None."""
    # Arrange
    store = MongoStateStore(connection_url="mongodb://localhost:27017")
    store._client = None

    # Act
    is_healthy = await store.check_connection()

    # Assert
    assert is_healthy is False


@pytest.mark.asyncio
async def test_connection_failure_raises_state_store_error():
    """Test that connection failures raise StateStoreError."""
    # Arrange
    store = MongoStateStore(connection_url="mongodb://invalid-host:27017")

    # Act & Assert
    with pytest.raises(StateStoreError, match="Failed to connect to MongoDB"):
        await store.initialize()

    # Cleanup
    await store.close()


@pytest.mark.asyncio
async def test_authentication_failure_raises_state_store_error():
    """Test that authentication failures raise StateStoreError with appropriate message."""
    # Arrange
    # Use a connection URL that will fail authentication
    # Note: This test may not work without a real MongoDB with wrong credentials
    # We'll mock it instead
    store = MongoStateStore(connection_url="mongodb://user:wrongpass@localhost:27017")

    # Mock the client to raise AuthenticationFailed
    with patch.object(store, "_client") as mock_client:
        # Create OperationFailure with authentication error code (18)
        auth_error = OperationFailure("Authentication failed", code=18)
        mock_client.admin.command = AsyncMock(side_effect=auth_error)

        # Act & Assert
        with pytest.raises(StateStoreError, match="MongoDB authentication failed"):
            await store.initialize()


@pytest.mark.asyncio
async def test_network_error_raises_state_store_error():
    """Test that network errors raise StateStoreError."""
    # Arrange
    store = MongoStateStore(connection_url="mongodb://localhost:27017")

    # Mock the client to raise NetworkTimeout
    with patch.object(store, "_client") as mock_client:
        mock_client.admin.command = AsyncMock(side_effect=NetworkTimeout("Network timeout"))

        # Act & Assert
        with pytest.raises(StateStoreError, match="Failed to connect to MongoDB"):
            await store.initialize()


@pytest.mark.asyncio
async def test_server_selection_timeout_raises_state_store_error():
    """Test that server selection timeout raises StateStoreError."""
    # Arrange
    store = MongoStateStore(connection_url="mongodb://localhost:27017")

    # Mock the client to raise ServerSelectionTimeoutError
    with patch.object(store, "_client") as mock_client:
        mock_client.admin.command = AsyncMock(
            side_effect=ServerSelectionTimeoutError("Server selection timeout")
        )

        # Act & Assert
        with pytest.raises(StateStoreError, match="Failed to connect to MongoDB"):
            await store.initialize()


@pytest.mark.asyncio
async def test_invalid_connection_url_raises_state_store_error():
    """Test that invalid connection URL raises StateStoreError on initialization."""
    # Create store with invalid URL
    store = MongoStateStore(connection_url="invalid-url")

    # Act & Assert - Error should occur when trying to initialize
    with pytest.raises((StateStoreError, ConnectionFailure, ConfigurationError)):
        await store.initialize()


@pytest.mark.asyncio
async def test_close_connection_cleans_up_resources(mongo_store: MongoStateStore):
    """Test that closing connection cleans up resources."""
    # Arrange
    await mongo_store.initialize()
    assert mongo_store._initialized is True
    assert mongo_store._client is not None

    # Act
    await mongo_store.close()

    # Assert
    assert mongo_store._initialized is False


@pytest.mark.asyncio
async def test_initialize_idempotent(mongo_store: MongoStateStore):
    """Test that initialize can be called multiple times safely."""
    # Act
    await mongo_store.initialize()
    first_initialized = mongo_store._initialized

    await mongo_store.initialize()
    second_initialized = mongo_store._initialized

    # Assert
    assert first_initialized is True
    assert second_initialized is True

    # Cleanup
    await mongo_store.close()


@pytest.mark.asyncio
async def test_database_name_configurable():
    """Test that database name can be configured."""
    # Arrange
    custom_db_name = "custom_database"
    store = MongoStateStore(
        connection_url="mongodb://localhost:27017", database_name=custom_db_name
    )

    # Assert
    assert store._database_name == custom_db_name

    # Cleanup
    await store.close()
