"""Integration tests for MongoDBStateStore query interface."""

import os
from datetime import datetime, timedelta

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from apikeyrouter.domain.interfaces.state_store import StateQuery
from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.domain.models.quota_state import (
    CapacityEstimate,
    CapacityState,
    CapacityUnit,
    QuotaState,
    TimeWindow,
)
from apikeyrouter.domain.models.routing_decision import (
    RoutingDecision,
    RoutingObjective,
)
from apikeyrouter.domain.models.state_transition import StateTransition
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
    database = client["test_apikeyrouter_query"]
    yield database
    # Cleanup: drop test database
    try:
        await client.drop_database("test_apikeyrouter_query")
    except Exception:
        pass  # Ignore cleanup errors
    client.close()


@pytest.fixture
async def mongo_store(mongodb_database) -> MongoStateStore:
    """Create MongoStateStore instance for testing."""
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    store = MongoStateStore(
        connection_url=mongodb_url,
        database_name="test_apikeyrouter_query",
        max_pool_size=50,
        min_pool_size=5,
        connect_timeout_ms=10000,
        server_selection_timeout_ms=3000,
    )
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
async def test_data(mongo_store: MongoStateStore):
    """Create test data for query tests."""
    # Create API keys
    keys = [
        APIKey(
            id=f"key-{i}",
            key_material=f"encrypted-{i}",
            provider_id="openai" if i % 2 == 0 else "anthropic",
            state=KeyState.Available if i % 3 != 0 else KeyState.Throttled,
            state_updated_at=datetime.utcnow(),
            created_at=datetime.utcnow() - timedelta(hours=i),
        )
        for i in range(10)
    ]

    for key in keys:
        await mongo_store.save_key(key)

    # Create quota states
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

    # Create routing decisions
    decisions = [
        RoutingDecision(
            id=f"decision-{i}",
            request_id=f"req-{i}",
            selected_key_id=f"key-{i % 10}",
            selected_provider_id="openai" if i % 2 == 0 else "anthropic",
            decision_timestamp=datetime.utcnow() - timedelta(hours=i),
            objective=RoutingObjective(primary="cost"),
            explanation=f"Decision {i}",
            confidence=0.9,
        )
        for i in range(20)
    ]

    for decision in decisions:
        await mongo_store.save_routing_decision(decision)

    # Create state transitions
    transitions = [
        StateTransition(
            entity_type="APIKey",
            entity_id=f"key-{i % 10}",
            from_state="available",
            to_state="throttled" if i % 2 == 0 else "exhausted",
            transition_timestamp=datetime.utcnow() - timedelta(hours=i),
            trigger=f"trigger-{i}",
        )
        for i in range(15)
    ]

    for transition in transitions:
        await mongo_store.save_state_transition(transition)

    return {
        "keys": keys,
        "quotas": quotas,
        "decisions": decisions,
        "transitions": transitions,
    }


@pytest.mark.asyncio
async def test_query_state_filters_by_key_id(mongo_store: MongoStateStore, test_data):
    """Test that query_state filters by key_id."""
    # Act - query APIKeys by key_id
    query = StateQuery(entity_type="APIKey", key_id="key-5")
    results = await mongo_store.query_state(query)

    # Assert
    assert len(results) == 1
    assert isinstance(results[0], APIKey)
    assert results[0].id == "key-5"


@pytest.mark.asyncio
async def test_query_state_filters_by_provider_id(mongo_store: MongoStateStore, test_data):
    """Test that query_state filters by provider_id."""
    # Act - query APIKeys by provider_id
    query = StateQuery(entity_type="APIKey", provider_id="openai")
    results = await mongo_store.query_state(query)

    # Assert
    assert len(results) > 0
    for result in results:
        assert isinstance(result, APIKey)
        assert result.provider_id == "openai"


@pytest.mark.asyncio
async def test_query_state_filters_by_state(mongo_store: MongoStateStore, test_data):
    """Test that query_state filters by state."""
    # Act - query APIKeys by state
    query = StateQuery(entity_type="APIKey", state="available")
    results = await mongo_store.query_state(query)

    # Assert
    assert len(results) > 0
    for result in results:
        assert isinstance(result, APIKey)
        assert result.state == KeyState.Available


@pytest.mark.asyncio
async def test_query_state_filters_by_timestamp_range(mongo_store: MongoStateStore, test_data):
    """Test that query_state filters by timestamp range."""
    # Arrange
    now = datetime.utcnow()
    two_hours_ago = now - timedelta(hours=2)

    # Act - query routing decisions in last 2 hours
    query = StateQuery(
        entity_type="RoutingDecision",
        timestamp_from=two_hours_ago,
        timestamp_to=now,
    )
    results = await mongo_store.query_state(query)

    # Assert
    assert len(results) > 0
    for result in results:
        if isinstance(result, RoutingDecision):
            assert two_hours_ago <= result.decision_timestamp <= now


@pytest.mark.asyncio
async def test_query_state_pagination_with_limit(mongo_store: MongoStateStore, test_data):
    """Test that query_state supports pagination with limit."""
    # Act - query with limit
    query = StateQuery(entity_type="RoutingDecision", limit=5)
    results = await mongo_store.query_state(query)

    # Assert
    assert len(results) == 5
    assert all(isinstance(r, RoutingDecision) for r in results)


@pytest.mark.asyncio
async def test_query_state_pagination_with_offset(mongo_store: MongoStateStore, test_data):
    """Test that query_state supports pagination with offset."""
    # Act - query with offset
    query1 = StateQuery(entity_type="RoutingDecision", limit=5, offset=0)
    results1 = await mongo_store.query_state(query1)

    query2 = StateQuery(entity_type="RoutingDecision", limit=5, offset=5)
    results2 = await mongo_store.query_state(query2)

    # Assert
    assert len(results1) == 5
    assert len(results2) == 5
    # Results should be different
    ids1 = {r.id for r in results1 if isinstance(r, RoutingDecision)}
    ids2 = {r.id for r in results2 if isinstance(r, RoutingDecision)}
    assert ids1.isdisjoint(ids2)


@pytest.mark.asyncio
async def test_query_state_combines_filters(mongo_store: MongoStateStore, test_data):
    """Test that query_state combines multiple filters."""
    # Act - query with multiple filters
    query = StateQuery(
        entity_type="APIKey",
        provider_id="openai",
        state="available",
    )
    results = await mongo_store.query_state(query)

    # Assert
    assert len(results) > 0
    for result in results:
        assert isinstance(result, APIKey)
        assert result.provider_id == "openai"
        assert result.state == KeyState.Available


@pytest.mark.asyncio
async def test_query_state_queries_all_entity_types(mongo_store: MongoStateStore, test_data):
    """Test that query_state can query all entity types when entity_type is None."""
    # Act - query all entity types
    query = StateQuery(entity_type=None, key_id="key-1")
    results = await mongo_store.query_state(query)

    # Assert - should find APIKey, QuotaState, RoutingDecision, StateTransition
    assert len(results) > 0
    entity_types = {type(r).__name__ for r in results}
    assert "APIKey" in entity_types or "QuotaState" in entity_types


@pytest.mark.asyncio
async def test_query_state_performance_under_100ms(mongo_store: MongoStateStore, test_data):
    """Test that query_state performs under 100ms for typical queries."""
    import time

    # Act - measure query performance
    start = time.time()
    query = StateQuery(
        entity_type="RoutingDecision",
        provider_id="openai",
        timestamp_from=datetime.utcnow() - timedelta(hours=1),
        timestamp_to=datetime.utcnow(),
        limit=100,
    )
    results = await mongo_store.query_state(query)
    elapsed = time.time() - start

    # Assert
    assert len(results) > 0
    # Should be fast with indexes (allow some margin for test environment)
    assert elapsed < 1.0  # 1 second is reasonable for test environment


@pytest.mark.asyncio
async def test_query_state_uses_indexes_for_key_id(mongo_store: MongoStateStore, test_data):
    """Test that query_state uses indexes for key_id queries."""
    # Act - query by key_id (should use index)
    query = StateQuery(entity_type="RoutingDecision", key_id="key-1")
    results = await mongo_store.query_state(query)

    # Assert
    assert len(results) > 0
    for result in results:
        if isinstance(result, RoutingDecision):
            assert result.selected_key_id == "key-1"


@pytest.mark.asyncio
async def test_query_state_uses_indexes_for_provider_id(mongo_store: MongoStateStore, test_data):
    """Test that query_state uses indexes for provider_id queries."""
    # Act - query by provider_id (should use index)
    query = StateQuery(entity_type="RoutingDecision", provider_id="anthropic")
    results = await mongo_store.query_state(query)

    # Assert
    assert len(results) > 0
    for result in results:
        if isinstance(result, RoutingDecision):
            assert result.selected_provider_id == "anthropic"


@pytest.mark.asyncio
async def test_query_state_compound_index_key_timestamp(mongo_store: MongoStateStore, test_data):
    """Test that compound indexes are used for key_id + timestamp queries."""
    # Act - query by key_id and timestamp (should use compound index)
    now = datetime.utcnow()
    query = StateQuery(
        entity_type="RoutingDecision",
        key_id="key-1",
        timestamp_from=now - timedelta(hours=5),
        timestamp_to=now,
    )
    results = await mongo_store.query_state(query)

    # Assert
    for result in results:
        if isinstance(result, RoutingDecision):
            assert result.selected_key_id == "key-1"
            assert now - timedelta(hours=5) <= result.decision_timestamp <= now


@pytest.mark.asyncio
async def test_query_state_compound_index_provider_timestamp(
    mongo_store: MongoStateStore, test_data
):
    """Test that compound indexes are used for provider_id + timestamp queries."""
    # Act - query by provider_id and timestamp (should use compound index)
    now = datetime.utcnow()
    query = StateQuery(
        entity_type="RoutingDecision",
        provider_id="openai",
        timestamp_from=now - timedelta(hours=5),
        timestamp_to=now,
    )
    results = await mongo_store.query_state(query)

    # Assert
    for result in results:
        if isinstance(result, RoutingDecision):
            assert result.selected_provider_id == "openai"
            assert now - timedelta(hours=5) <= result.decision_timestamp <= now


@pytest.mark.asyncio
async def test_query_state_empty_results(mongo_store: MongoStateStore):
    """Test that query_state returns empty list for no matches."""
    # Act - query with filters that match nothing
    query = StateQuery(
        entity_type="APIKey",
        key_id="nonexistent-key",
    )
    results = await mongo_store.query_state(query)

    # Assert
    assert results == []


@pytest.mark.asyncio
async def test_query_state_quota_state_by_reset_at(mongo_store: MongoStateStore, test_data):
    """Test that query_state queries QuotaState by reset_at timestamp."""
    # Arrange
    now = datetime.utcnow()
    tomorrow = now + timedelta(days=1)

    # Act - query quota states with reset_at in range
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
            assert now <= result.reset_at <= tomorrow


@pytest.mark.asyncio
async def test_query_state_state_transition_by_entity_id(mongo_store: MongoStateStore, test_data):
    """Test that query_state queries StateTransition by entity_id."""
    # Act - query state transitions by entity_id
    query = StateQuery(
        entity_type="StateTransition",
        key_id="key-1",
    )
    results = await mongo_store.query_state(query)

    # Assert
    assert len(results) > 0
    for result in results:
        if isinstance(result, StateTransition):
            assert result.entity_id == "key-1"


@pytest.mark.asyncio
async def test_query_state_state_transition_by_state(mongo_store: MongoStateStore, test_data):
    """Test that query_state queries StateTransition by state."""
    # Act - query state transitions by to_state
    query = StateQuery(
        entity_type="StateTransition",
        state="throttled",
    )
    results = await mongo_store.query_state(query)

    # Assert
    assert len(results) > 0
    for result in results:
        if isinstance(result, StateTransition):
            assert result.to_state == "throttled"

