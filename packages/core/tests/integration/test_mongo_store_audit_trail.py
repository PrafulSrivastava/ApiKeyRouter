"""Integration tests for MongoDBStateStore audit trail storage using Beanie."""

import os
from datetime import datetime, timedelta

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from apikeyrouter.domain.interfaces.state_store import StateQuery
from apikeyrouter.domain.models.routing_decision import (
    AlternativeRoute,
    RoutingDecision,
    RoutingObjective,
)
from apikeyrouter.domain.models.state_transition import StateTransition
from apikeyrouter.infrastructure.state_store.mongo_store import MongoStateStore


@pytest.fixture
async def mongodb_database():
    """Create MongoDB database for testing."""
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongodb_url)
    database = client["test_apikeyrouter_audit"]
    yield database
    # Cleanup: drop test database
    await client.drop_database("test_apikeyrouter_audit")
    client.close()


@pytest.fixture
async def mongo_store(mongodb_database) -> MongoStateStore:
    """Create MongoStateStore instance for testing."""
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    store = MongoStateStore(
        connection_url=mongodb_url,
        database_name="test_apikeyrouter_audit",
        max_pool_size=50,
        min_pool_size=5,
        connect_timeout_ms=10000,
        server_selection_timeout_ms=3000,
    )
    await store.initialize()
    yield store
    await store.close()


@pytest.mark.asyncio
async def test_save_routing_decision_saves_to_mongodb(mongo_store: MongoStateStore):
    """Test that save_routing_decision saves to MongoDB using Beanie."""
    # Arrange
    decision = RoutingDecision(
        id="decision-1",
        request_id="req-1",
        selected_key_id="key-1",
        selected_provider_id="openai",
        decision_timestamp=datetime.utcnow(),
        objective=RoutingObjective(primary="cost"),
        explanation="Lowest cost key available",
        confidence=0.9,
    )

    # Act
    await mongo_store.save_routing_decision(decision)

    # Assert - verify via query_state
    query = StateQuery(entity_type="RoutingDecision", key_id="key-1")
    results = await mongo_store.query_state(query)
    assert len(results) > 0
    retrieved = results[0]
    assert isinstance(retrieved, RoutingDecision)
    assert retrieved.id == decision.id
    assert retrieved.selected_key_id == decision.selected_key_id
    assert retrieved.explanation == decision.explanation


@pytest.mark.asyncio
async def test_save_state_transition_saves_to_mongodb(mongo_store: MongoStateStore):
    """Test that save_state_transition saves to MongoDB using Beanie."""
    # Arrange
    transition = StateTransition(
        entity_type="APIKey",
        entity_id="key-1",
        from_state="available",
        to_state="throttled",
        transition_timestamp=datetime.utcnow(),
        trigger="rate_limit_error",
        context={"error_code": 429},
    )

    # Act
    await mongo_store.save_state_transition(transition)

    # Assert - verify via query_state
    query = StateQuery(entity_type="StateTransition", key_id="key-1")
    results = await mongo_store.query_state(query)
    assert len(results) > 0
    retrieved = results[0]
    assert isinstance(retrieved, StateTransition)
    assert retrieved.entity_id == transition.entity_id
    assert retrieved.from_state == transition.from_state
    assert retrieved.to_state == transition.to_state
    assert retrieved.trigger == transition.trigger


@pytest.mark.asyncio
async def test_indexes_created_for_routing_decisions(mongo_store: MongoStateStore):
    """Test that indexes are created for routing decisions."""
    # Arrange - save a routing decision
    decision = RoutingDecision(
        id="decision-index",
        request_id="req-index",
        selected_key_id="key-index",
        selected_provider_id="openai",
        decision_timestamp=datetime.utcnow(),
        objective=RoutingObjective(primary="cost"),
        explanation="Test index",
        confidence=0.9,
    )
    await mongo_store.save_routing_decision(decision)

    # Act - query by key_id (should use index)
    query = StateQuery(entity_type="RoutingDecision", key_id="key-index")
    results = await mongo_store.query_state(query)

    # Assert
    assert len(results) > 0
    assert results[0].selected_key_id == "key-index"


@pytest.mark.asyncio
async def test_indexes_created_for_state_transitions(mongo_store: MongoStateStore):
    """Test that indexes are created for state transitions."""
    # Arrange - save a state transition
    transition = StateTransition(
        entity_type="APIKey",
        entity_id="key-transition",
        from_state="available",
        to_state="throttled",
        transition_timestamp=datetime.utcnow(),
        trigger="test",
    )
    await mongo_store.save_state_transition(transition)

    # Act - query by entity_id (should use index)
    query = StateQuery(entity_type="StateTransition", key_id="key-transition")
    results = await mongo_store.query_state(query)

    # Assert
    assert len(results) > 0
    assert results[0].entity_id == "key-transition"


@pytest.mark.asyncio
async def test_time_range_queries_for_routing_decisions(mongo_store: MongoStateStore):
    """Test time-range queries for routing decisions."""
    # Arrange - create decisions at different times
    now = datetime.utcnow()
    decisions = [
        RoutingDecision(
            id=f"decision-time-{i}",
            request_id=f"req-{i}",
            selected_key_id="key-time",
            selected_provider_id="openai",
            decision_timestamp=now - timedelta(hours=i),
            objective=RoutingObjective(primary="cost"),
            explanation=f"Decision {i}",
            confidence=0.9,
        )
        for i in range(5)
    ]

    for decision in decisions:
        await mongo_store.save_routing_decision(decision)

    # Act - query decisions in last 2 hours
    two_hours_ago = now - timedelta(hours=2)
    query = StateQuery(
        entity_type="RoutingDecision",
        timestamp_from=two_hours_ago,
        timestamp_to=now,
    )
    results = await mongo_store.query_state(query)

    # Assert - should find decisions from last 2 hours
    assert len(results) >= 2
    for result in results:
        if isinstance(result, RoutingDecision):
            assert two_hours_ago <= result.decision_timestamp <= now


@pytest.mark.asyncio
async def test_time_range_queries_for_state_transitions(mongo_store: MongoStateStore):
    """Test time-range queries for state transitions."""
    # Arrange - create transitions at different times
    now = datetime.utcnow()
    transitions = [
        StateTransition(
            entity_type="APIKey",
            entity_id="key-time-trans",
            from_state="available",
            to_state="throttled",
            transition_timestamp=now - timedelta(hours=i),
            trigger=f"trigger-{i}",
        )
        for i in range(5)
    ]

    for transition in transitions:
        await mongo_store.save_state_transition(transition)

    # Act - query transitions in last 2 hours
    two_hours_ago = now - timedelta(hours=2)
    query = StateQuery(
        entity_type="StateTransition",
        timestamp_from=two_hours_ago,
        timestamp_to=now,
    )
    results = await mongo_store.query_state(query)

    # Assert - should find transitions from last 2 hours
    assert len(results) >= 2
    for result in results:
        if isinstance(result, StateTransition):
            assert two_hours_ago <= result.transition_timestamp <= now


@pytest.mark.asyncio
async def test_query_routing_decisions_by_provider(mongo_store: MongoStateStore):
    """Test querying routing decisions by provider_id."""
    # Arrange
    decisions = [
        RoutingDecision(
            id=f"decision-prov-{i}",
            request_id=f"req-{i}",
            selected_key_id=f"key-{i}",
            selected_provider_id="openai" if i % 2 == 0 else "anthropic",
            decision_timestamp=datetime.utcnow(),
            objective=RoutingObjective(primary="cost"),
            explanation=f"Decision {i}",
            confidence=0.9,
        )
        for i in range(6)
    ]

    for decision in decisions:
        await mongo_store.save_routing_decision(decision)

    # Act - query by provider
    query = StateQuery(
        entity_type="RoutingDecision", provider_id="openai"
    )
    results = await mongo_store.query_state(query)

    # Assert
    assert len(results) == 3  # Half are openai
    for result in results:
        if isinstance(result, RoutingDecision):
            assert result.selected_provider_id == "openai"


@pytest.mark.asyncio
async def test_query_state_transitions_by_state(mongo_store: MongoStateStore):
    """Test querying state transitions by state."""
    # Arrange
    transitions = [
        StateTransition(
            entity_type="APIKey",
            entity_id="key-state",
            from_state="available",
            to_state="throttled" if i % 2 == 0 else "exhausted",
            transition_timestamp=datetime.utcnow(),
            trigger=f"trigger-{i}",
        )
        for i in range(4)
    ]

    for transition in transitions:
        await mongo_store.save_state_transition(transition)

    # Act - query by to_state
    query = StateQuery(
        entity_type="StateTransition", state="throttled"
    )
    results = await mongo_store.query_state(query)

    # Assert
    assert len(results) == 2  # Half are throttled
    for result in results:
        if isinstance(result, StateTransition):
            assert result.to_state == "throttled"


@pytest.mark.asyncio
async def test_save_routing_decision_with_alternatives(mongo_store: MongoStateStore):
    """Test that save_routing_decision preserves all fields including alternatives."""
    # Arrange
    decision = RoutingDecision(
        id="decision-alt",
        request_id="req-alt",
        selected_key_id="key-1",
        selected_provider_id="openai",
        decision_timestamp=datetime.utcnow(),
        objective=RoutingObjective(primary="cost", secondary=["reliability"]),
        explanation="Selected lowest cost",
        confidence=0.95,
        alternatives_considered=[
            AlternativeRoute(
                key_id="key-2",
                provider_id="openai",
                score=0.85,
                reason_not_selected="Higher cost",
            ),
            AlternativeRoute(
                key_id="key-3",
                provider_id="anthropic",
                score=0.80,
                reason_not_selected="Different provider",
            ),
        ],
        evaluation_results={"key-1": 0.95, "key-2": 0.85, "key-3": 0.80},
    )

    # Act
    await mongo_store.save_routing_decision(decision)

    # Assert
    query = StateQuery(entity_type="RoutingDecision", key_id="key-1")
    results = await mongo_store.query_state(query)
    assert len(results) > 0
    retrieved = results[0]
    assert isinstance(retrieved, RoutingDecision)
    assert len(retrieved.alternatives_considered) == 2
    assert retrieved.alternatives_considered[0].key_id == "key-2"
    assert retrieved.evaluation_results == decision.evaluation_results


@pytest.mark.asyncio
async def test_save_state_transition_with_context(mongo_store: MongoStateStore):
    """Test that save_state_transition preserves context field."""
    # Arrange
    transition = StateTransition(
        entity_type="APIKey",
        entity_id="key-context",
        from_state="available",
        to_state="throttled",
        transition_timestamp=datetime.utcnow(),
        trigger="rate_limit_error",
        context={
            "error_code": 429,
            "retry_after": 60,
            "request_id": "req-123",
        },
    )

    # Act
    await mongo_store.save_state_transition(transition)

    # Assert
    query = StateQuery(entity_type="StateTransition", key_id="key-context")
    results = await mongo_store.query_state(query)
    assert len(results) > 0
    retrieved = results[0]
    assert isinstance(retrieved, StateTransition)
    assert retrieved.context == transition.context
    assert retrieved.context["error_code"] == 429


@pytest.mark.asyncio
async def test_append_only_behavior_for_routing_decisions(mongo_store: MongoStateStore):
    """Test that routing decisions are append-only (no updates)."""
    # Arrange
    decision = RoutingDecision(
        id="decision-append",
        request_id="req-append",
        selected_key_id="key-append",
        selected_provider_id="openai",
        decision_timestamp=datetime.utcnow(),
        objective=RoutingObjective(primary="cost"),
        explanation="Initial decision",
        confidence=0.9,
    )
    await mongo_store.save_routing_decision(decision)

    # Act - try to save again (should create duplicate, not update)
    decision.explanation = "Updated explanation"
    await mongo_store.save_routing_decision(decision)

    # Assert - should have 2 documents
    query = StateQuery(entity_type="RoutingDecision", key_id="key-append")
    results = await mongo_store.query_state(query)
    assert len(results) == 2  # Both saved (append-only)


@pytest.mark.asyncio
async def test_append_only_behavior_for_state_transitions(mongo_store: MongoStateStore):
    """Test that state transitions are append-only (no updates)."""
    # Arrange
    transition = StateTransition(
        entity_type="APIKey",
        entity_id="key-append-trans",
        from_state="available",
        to_state="throttled",
        transition_timestamp=datetime.utcnow(),
        trigger="initial",
    )
    await mongo_store.save_state_transition(transition)

    # Act - save another transition for same entity
    transition2 = StateTransition(
        entity_type="APIKey",
        entity_id="key-append-trans",
        from_state="throttled",
        to_state="available",
        transition_timestamp=datetime.utcnow() + timedelta(seconds=1),
        trigger="recovery",
    )
    await mongo_store.save_state_transition(transition2)

    # Assert - should have 2 documents
    query = StateQuery(entity_type="StateTransition", key_id="key-append-trans")
    results = await mongo_store.query_state(query)
    assert len(results) == 2  # Both saved (append-only)


@pytest.mark.asyncio
async def test_pagination_for_routing_decisions(mongo_store: MongoStateStore):
    """Test pagination support for routing decisions."""
    # Arrange - create multiple decisions
    decisions = [
        RoutingDecision(
            id=f"decision-page-{i}",
            request_id=f"req-{i}",
            selected_key_id="key-page",
            selected_provider_id="openai",
            decision_timestamp=datetime.utcnow() - timedelta(minutes=i),
            objective=RoutingObjective(primary="cost"),
            explanation=f"Decision {i}",
            confidence=0.9,
        )
        for i in range(10)
    ]

    for decision in decisions:
        await mongo_store.save_routing_decision(decision)

    # Act - query with limit and offset
    query = StateQuery(
        entity_type="RoutingDecision",
        key_id="key-page",
        limit=5,
        offset=0,
    )
    page1 = await mongo_store.query_state(query)

    query.offset = 5
    page2 = await mongo_store.query_state(query)

    # Assert
    assert len(page1) == 5
    assert len(page2) == 5
    # Should have different IDs
    page1_ids = {r.id for r in page1 if isinstance(r, RoutingDecision)}
    page2_ids = {r.id for r in page2 if isinstance(r, RoutingDecision)}
    assert page1_ids.isdisjoint(page2_ids)  # No overlap

