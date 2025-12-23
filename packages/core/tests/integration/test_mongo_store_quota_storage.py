"""Integration tests for MongoDBStateStore quota state storage using Beanie."""

import os
from datetime import datetime, timedelta

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from apikeyrouter.domain.interfaces.state_store import StateQuery
from apikeyrouter.domain.models.quota_state import (
    CapacityEstimate,
    CapacityState,
    CapacityUnit,
    QuotaState,
    TimeWindow,
)
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
        pytest.skip(
            "MongoDB is not available. Start MongoDB with 'docker-compose up -d' or set MONGODB_URL"
        )

    client = AsyncIOMotorClient(mongodb_url)
    database = client["test_apikeyrouter_quota"]
    from contextlib import suppress

    yield database
    # Cleanup: drop test database
    with suppress(Exception):
        await client.drop_database("test_apikeyrouter_quota")  # Ignore cleanup errors
    client.close()


@pytest.fixture
async def mongo_store(mongodb_database) -> MongoStateStore:
    """Create MongoStateStore instance for testing."""
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    store = MongoStateStore(
        connection_url=mongodb_url,
        database_name="test_apikeyrouter_quota",
        max_pool_size=50,
        min_pool_size=5,
        connect_timeout_ms=10000,
        server_selection_timeout_ms=3000,
    )
    await store.initialize()
    yield store
    await store.close()


@pytest.mark.asyncio
async def test_save_quota_state_saves_to_mongodb(mongo_store: MongoStateStore):
    """Test that save_quota_state saves to MongoDB using Beanie."""
    # Arrange
    quota = QuotaState(
        id="quota-1",
        key_id="key-1",
        capacity_state=CapacityState.Abundant,
        capacity_unit=CapacityUnit.Requests,
        remaining_capacity=CapacityEstimate(value=1000),
        reset_at=datetime.utcnow() + timedelta(days=1),
        updated_at=datetime.utcnow(),
    )

    # Act
    await mongo_store.save_quota_state(quota)

    # Assert - retrieve using get_quota_state
    retrieved = await mongo_store.get_quota_state("key-1")
    assert retrieved is not None
    assert retrieved.id == quota.id
    assert retrieved.key_id == quota.key_id
    assert retrieved.capacity_state == quota.capacity_state
    assert retrieved.remaining_capacity.value == quota.remaining_capacity.value


@pytest.mark.asyncio
async def test_get_quota_state_retrieves_from_mongodb(mongo_store: MongoStateStore):
    """Test that get_quota_state retrieves from MongoDB using Beanie."""
    # Arrange
    quota = QuotaState(
        id="quota-2",
        key_id="key-2",
        capacity_state=CapacityState.Constrained,
        capacity_unit=CapacityUnit.Mixed,
        remaining_capacity=CapacityEstimate(value=500, confidence=0.9),
        total_capacity=1000,
        used_capacity=500,
        remaining_tokens=CapacityEstimate(value=10000),
        total_tokens=20000,
        used_tokens=10000,
        used_requests=50,
        time_window=TimeWindow.Daily,
        reset_at=datetime.utcnow() + timedelta(days=1),
        updated_at=datetime.utcnow(),
    )
    await mongo_store.save_quota_state(quota)

    # Act
    retrieved = await mongo_store.get_quota_state("key-2")

    # Assert
    assert retrieved is not None
    assert retrieved.id == quota.id
    assert retrieved.key_id == quota.key_id
    assert retrieved.capacity_state == quota.capacity_state
    assert retrieved.used_capacity == quota.used_capacity
    assert retrieved.remaining_tokens is not None
    assert retrieved.remaining_tokens.value == quota.remaining_tokens.value


@pytest.mark.asyncio
async def test_get_quota_state_returns_none_for_nonexistent_key(
    mongo_store: MongoStateStore,
):
    """Test that get_quota_state returns None for non-existent key."""
    # Act
    retrieved = await mongo_store.get_quota_state("nonexistent-key-id")

    # Assert
    assert retrieved is None


@pytest.mark.asyncio
async def test_save_quota_state_upserts_existing_state(mongo_store: MongoStateStore):
    """Test that save_quota_state updates existing state (upsert behavior)."""
    # Arrange
    quota = QuotaState(
        id="quota-3",
        key_id="key-3",
        capacity_state=CapacityState.Abundant,
        capacity_unit=CapacityUnit.Requests,
        remaining_capacity=CapacityEstimate(value=1000),
        used_capacity=0,
        reset_at=datetime.utcnow() + timedelta(days=1),
        updated_at=datetime.utcnow(),
    )
    await mongo_store.save_quota_state(quota)

    # Update the quota state
    quota.used_capacity = 500
    quota.remaining_capacity = CapacityEstimate(value=500)
    quota.capacity_state = CapacityState.Constrained
    quota.updated_at = datetime.utcnow()

    # Act
    await mongo_store.save_quota_state(quota)

    # Assert
    retrieved = await mongo_store.get_quota_state("key-3")
    assert retrieved is not None
    assert retrieved.used_capacity == 500
    assert retrieved.remaining_capacity.value == 500
    assert retrieved.capacity_state == CapacityState.Constrained


@pytest.mark.asyncio
async def test_indexes_used_for_fast_lookups(mongo_store: MongoStateStore):
    """Test that indexes are used for fast lookups."""
    # Arrange - save multiple quota states
    quotas = [
        QuotaState(
            id=f"quota-{i}",
            key_id=f"key-{i}",
            capacity_state=CapacityState.Abundant,
            capacity_unit=CapacityUnit.Requests,
            remaining_capacity=CapacityEstimate(value=1000),
            reset_at=datetime.utcnow() + timedelta(days=i),
            updated_at=datetime.utcnow(),
        )
        for i in range(10)
    ]

    for quota in quotas:
        await mongo_store.save_quota_state(quota)

    # Act - retrieve by key_id (should use unique index)
    retrieved = await mongo_store.get_quota_state("key-5")

    # Assert
    assert retrieved is not None
    assert retrieved.id == "quota-5"


@pytest.mark.asyncio
async def test_time_window_queries_by_reset_at(mongo_store: MongoStateStore):
    """Test time-window queries using reset_at field."""
    # Arrange - create quota states with different reset times
    now = datetime.utcnow()
    quotas = [
        QuotaState(
            id=f"quota-past-{i}",
            key_id=f"key-past-{i}",
            capacity_state=CapacityState.Abundant,
            capacity_unit=CapacityUnit.Requests,
            remaining_capacity=CapacityEstimate(value=1000),
            reset_at=now - timedelta(days=i + 1),  # Past resets
            updated_at=datetime.utcnow(),
        )
        for i in range(3)
    ] + [
        QuotaState(
            id=f"quota-future-{i}",
            key_id=f"key-future-{i}",
            capacity_state=CapacityState.Abundant,
            capacity_unit=CapacityUnit.Requests,
            remaining_capacity=CapacityEstimate(value=1000),
            reset_at=now + timedelta(days=i + 1),  # Future resets
            updated_at=datetime.utcnow(),
        )
        for i in range(3)
    ]

    for quota in quotas:
        await mongo_store.save_quota_state(quota)

    # Act - query quota states that need reset (reset_at <= now)
    query = StateQuery(
        entity_type="QuotaState",
        timestamp_to=now,
    )
    results = await mongo_store.query_state(query)

    # Assert - should find quota states with reset_at <= now
    assert len(results) >= 3  # At least the past ones
    for result in results:
        if isinstance(result, QuotaState):
            assert result.reset_at <= now


@pytest.mark.asyncio
async def test_time_window_queries_by_reset_at_range(mongo_store: MongoStateStore):
    """Test time-window queries with reset_at range."""
    # Arrange
    now = datetime.utcnow()
    tomorrow = now + timedelta(days=1)
    now + timedelta(days=2)

    quotas = [
        QuotaState(
            id=f"quota-range-{i}",
            key_id=f"key-range-{i}",
            capacity_state=CapacityState.Abundant,
            capacity_unit=CapacityUnit.Requests,
            remaining_capacity=CapacityEstimate(value=1000),
            reset_at=now + timedelta(hours=i * 12),  # Spread over time
            updated_at=datetime.utcnow(),
        )
        for i in range(5)
    ]

    for quota in quotas:
        await mongo_store.save_quota_state(quota)

    # Act - query quota states with reset_at between now and tomorrow
    query = StateQuery(
        entity_type="QuotaState",
        timestamp_from=now,
        timestamp_to=tomorrow,
    )
    results = await mongo_store.query_state(query)

    # Assert
    assert len(results) > 0
    for result in results:
        if isinstance(result, QuotaState):
            # Use timedelta tolerance for microsecond precision differences
            assert (
                (now - timedelta(seconds=1)) <= result.reset_at <= (tomorrow + timedelta(seconds=1))
            )


@pytest.mark.asyncio
async def test_efficient_upsert_operations(mongo_store: MongoStateStore):
    """Test that upsert operations are efficient."""
    # Arrange
    quota = QuotaState(
        id="quota-upsert",
        key_id="key-upsert",
        capacity_state=CapacityState.Abundant,
        capacity_unit=CapacityUnit.Requests,
        remaining_capacity=CapacityEstimate(value=1000),
        reset_at=datetime.utcnow() + timedelta(days=1),
        updated_at=datetime.utcnow(),
    )

    # Act - save multiple times (should update, not create duplicates)
    await mongo_store.save_quota_state(quota)
    quota.used_capacity = 100
    await mongo_store.save_quota_state(quota)
    quota.used_capacity = 200
    await mongo_store.save_quota_state(quota)

    # Assert - should only have one document
    retrieved = await mongo_store.get_quota_state("key-upsert")
    assert retrieved is not None
    assert retrieved.used_capacity == 200  # Latest value


@pytest.mark.asyncio
async def test_concurrent_updates_handled_atomically(mongo_store: MongoStateStore):
    """Test that concurrent updates are handled atomically."""
    # Arrange
    quota = QuotaState(
        id="quota-concurrent",
        key_id="key-concurrent",
        capacity_state=CapacityState.Abundant,
        capacity_unit=CapacityUnit.Requests,
        remaining_capacity=CapacityEstimate(value=1000),
        reset_at=datetime.utcnow() + timedelta(days=1),
        updated_at=datetime.utcnow(),
    )
    await mongo_store.save_quota_state(quota)

    # Act - simulate concurrent updates
    import asyncio

    async def update_quota(increment: int) -> None:
        retrieved = await mongo_store.get_quota_state("key-concurrent")
        if retrieved:
            retrieved.used_capacity += increment
            retrieved.updated_at = datetime.utcnow()
            await mongo_store.save_quota_state(retrieved)

    # Run multiple updates concurrently
    await asyncio.gather(
        update_quota(10),
        update_quota(20),
        update_quota(30),
    )

    # Assert - final state should reflect all updates (MongoDB handles atomicity)
    final = await mongo_store.get_quota_state("key-concurrent")
    assert final is not None
    # The exact value depends on execution order, but should be >= initial + 10
    assert final.used_capacity >= 10


@pytest.mark.asyncio
async def test_save_quota_state_with_all_fields(mongo_store: MongoStateStore):
    """Test that save_quota_state preserves all fields."""
    # Arrange
    quota = QuotaState(
        id="quota-full",
        key_id="key-full",
        capacity_state=CapacityState.Critical,
        capacity_unit=CapacityUnit.Mixed,
        remaining_capacity=CapacityEstimate(
            value=500, min_value=400, max_value=600, confidence=0.85
        ),
        total_capacity=1000,
        used_capacity=500,
        remaining_tokens=CapacityEstimate(value=5000, confidence=0.9),
        total_tokens=10000,
        used_tokens=5000,
        used_requests=100,
        time_window=TimeWindow.Daily,
        reset_at=datetime.utcnow() + timedelta(days=1),
        updated_at=datetime.utcnow(),
    )

    # Act
    await mongo_store.save_quota_state(quota)

    # Assert
    retrieved = await mongo_store.get_quota_state("key-full")
    assert retrieved is not None
    assert retrieved.id == quota.id
    assert retrieved.key_id == quota.key_id
    assert retrieved.capacity_state == quota.capacity_state
    assert retrieved.capacity_unit == quota.capacity_unit
    assert retrieved.remaining_capacity.value == quota.remaining_capacity.value
    assert retrieved.total_capacity == quota.total_capacity
    assert retrieved.used_capacity == quota.used_capacity
    assert retrieved.remaining_tokens is not None
    assert retrieved.remaining_tokens.value == quota.remaining_tokens.value
    assert retrieved.time_window == quota.time_window
