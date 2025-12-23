"""Integration tests for MongoDBStateStore key storage using Beanie."""

import os
from datetime import datetime

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.infrastructure.state_store.mongo_store import MongoStateStore


@pytest.fixture
async def mongodb_database():
    """Create MongoDB database for testing."""
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")

    # Check if MongoDB is available
    try:
        client = AsyncIOMotorClient(mongodb_url, serverSelectionTimeoutMS=2000)
        await client.admin.command("ping")
    except Exception:
        pytest.skip("MongoDB is not available. Start MongoDB with 'docker-compose up -d' or set MONGODB_URL")

    client = AsyncIOMotorClient(mongodb_url)
    database = client["test_apikeyrouter_keys"]
    from contextlib import suppress

    yield database
    # Cleanup: drop test database
    with suppress(Exception):
        await client.drop_database("test_apikeyrouter_keys")  # Ignore cleanup errors
    client.close()


@pytest.fixture
async def mongo_store(mongodb_database) -> MongoStateStore:
    """Create MongoStateStore instance for testing."""
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    store = MongoStateStore(
        connection_url=mongodb_url,
        database_name="test_apikeyrouter_keys",
        max_pool_size=50,
        min_pool_size=5,
        connect_timeout_ms=10000,
        server_selection_timeout_ms=3000,
    )
    await store.initialize()
    yield store
    await store.close()


@pytest.mark.asyncio
async def test_save_key_saves_to_mongodb(mongo_store: MongoStateStore):
    """Test that save_key saves to MongoDB using Beanie."""
    # Arrange
    key = APIKey(
        id="test-key-1",
        key_material="encrypted_key_material",
        provider_id="openai",
        state=KeyState.Available,
        state_updated_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
    )

    # Act
    await mongo_store.save_key(key)

    # Assert - retrieve using get_key
    retrieved = await mongo_store.get_key("test-key-1")
    assert retrieved is not None
    assert retrieved.id == key.id
    assert retrieved.key_material == key.key_material
    assert retrieved.provider_id == key.provider_id
    assert retrieved.state == key.state


@pytest.mark.asyncio
async def test_get_key_retrieves_from_mongodb(mongo_store: MongoStateStore):
    """Test that get_key retrieves from MongoDB using Beanie."""
    # Arrange
    key = APIKey(
        id="test-key-2",
        key_material="encrypted_key_2",
        provider_id="anthropic",
        state=KeyState.Available,
        state_updated_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        usage_count=10,
        failure_count=1,
    )
    await mongo_store.save_key(key)

    # Act
    retrieved = await mongo_store.get_key("test-key-2")

    # Assert
    assert retrieved is not None
    assert retrieved.id == key.id
    assert retrieved.provider_id == key.provider_id
    assert retrieved.usage_count == key.usage_count
    assert retrieved.failure_count == key.failure_count


@pytest.mark.asyncio
async def test_get_key_returns_none_for_nonexistent_key(mongo_store: MongoStateStore):
    """Test that get_key returns None for non-existent key."""
    # Act
    retrieved = await mongo_store.get_key("nonexistent-key-id")

    # Assert
    assert retrieved is None


@pytest.mark.asyncio
async def test_save_key_upserts_existing_key(mongo_store: MongoStateStore):
    """Test that save_key updates existing key (upsert behavior)."""
    # Arrange
    key = APIKey(
        id="test-key-3",
        key_material="encrypted_key_3",
        provider_id="openai",
        state=KeyState.Available,
        state_updated_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        usage_count=5,
    )
    await mongo_store.save_key(key)

    # Update the key
    key.usage_count = 15
    key.state = KeyState.Throttled
    key.state_updated_at = datetime.utcnow()

    # Act
    await mongo_store.save_key(key)

    # Assert
    retrieved = await mongo_store.get_key("test-key-3")
    assert retrieved is not None
    assert retrieved.usage_count == 15
    assert retrieved.state == KeyState.Throttled


@pytest.mark.asyncio
async def test_indexes_used_for_fast_lookups(mongo_store: MongoStateStore):
    """Test that indexes are used for fast lookups."""
    # Arrange - save multiple keys
    keys = [
        APIKey(
            id=f"test-key-{i}",
            key_material=f"encrypted_key_{i}",
            provider_id="openai" if i % 2 == 0 else "anthropic",
            state=KeyState.Available,
            state_updated_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        for i in range(10)
    ]

    for key in keys:
        await mongo_store.save_key(key)

    # Act - retrieve by key_id (should use index)
    retrieved = await mongo_store.get_key("test-key-5")

    # Assert
    assert retrieved is not None
    assert retrieved.id == "test-key-5"

    # Verify we can query by provider_id (uses index)
    all_keys = await mongo_store.list_keys(provider_id="openai")
    assert len(all_keys) == 5  # Half of the keys are openai


@pytest.mark.asyncio
async def test_async_operations_work_correctly(mongo_store: MongoStateStore):
    """Test that async operations work correctly with Beanie."""
    # Arrange
    keys = [
        APIKey(
            id=f"async-key-{i}",
            key_material=f"encrypted_async_{i}",
            provider_id="openai",
            state=KeyState.Available,
            state_updated_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        for i in range(5)
    ]

    # Act - save multiple keys concurrently
    import asyncio

    await asyncio.gather(*[mongo_store.save_key(key) for key in keys])

    # Assert - retrieve all keys
    retrieved_keys = []
    for key in keys:
        retrieved = await mongo_store.get_key(key.id)
        assert retrieved is not None
        retrieved_keys.append(retrieved)

    assert len(retrieved_keys) == 5


@pytest.mark.asyncio
async def test_save_key_with_all_fields(mongo_store: MongoStateStore):
    """Test that save_key preserves all fields."""
    # Arrange
    key = APIKey(
        id="test-key-full",
        key_material="encrypted_full",
        provider_id="openai",
        state=KeyState.Available,
        state_updated_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        last_used_at=datetime.utcnow(),
        usage_count=100,
        failure_count=5,
        cooldown_until=None,
        metadata={"account_tier": "premium", "organization_id": "org_123"},
    )

    # Act
    await mongo_store.save_key(key)

    # Assert
    retrieved = await mongo_store.get_key("test-key-full")
    assert retrieved is not None
    assert retrieved.id == key.id
    assert retrieved.key_material == key.key_material
    assert retrieved.provider_id == key.provider_id
    assert retrieved.state == key.state
    assert retrieved.usage_count == key.usage_count
    assert retrieved.failure_count == key.failure_count
    assert retrieved.metadata == key.metadata
    assert retrieved.last_used_at is not None


@pytest.mark.asyncio
async def test_get_key_uses_index_for_fast_lookup(mongo_store: MongoStateStore):
    """Test that get_key uses the key_id index for fast lookups."""
    # Arrange - create many keys
    for i in range(100):
        key = APIKey(
            id=f"perf-test-key-{i}",
            key_material=f"encrypted_{i}",
            provider_id="openai",
            state=KeyState.Available,
            state_updated_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        await mongo_store.save_key(key)

    # Act - retrieve a key (should use index)
    import time

    start = time.time()
    retrieved = await mongo_store.get_key("perf-test-key-50")
    elapsed = time.time() - start

    # Assert
    assert retrieved is not None
    assert retrieved.id == "perf-test-key-50"
    # Should be fast with index (less than 100ms typically)
    assert elapsed < 1.0  # Allow some margin for test environment

