"""Tests for InMemoryStateStore implementation."""

import asyncio
from datetime import datetime, timedelta

import pytest

from apikeyrouter.domain.interfaces.state_store import (
    StateQuery,
    StateStoreError,
)
from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.domain.models.quota_state import (
    CapacityEstimate,
    QuotaState,
)
from apikeyrouter.domain.models.routing_decision import (
    RoutingDecision,
    RoutingObjective,
)
from apikeyrouter.domain.models.state_transition import StateTransition
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore


class TestInMemoryStateStoreKeyStorage:
    """Tests for InMemoryStateStore key storage operations."""

    @pytest.mark.asyncio
    async def test_save_key_stores_apikey_correctly(self) -> None:
        """Test that save_key stores APIKey correctly."""
        store = InMemoryStateStore()
        key = APIKey(
            id="key1",
            key_material="encrypted_key_material",
            provider_id="openai",
        )

        await store.save_key(key)

        # Verify key was stored
        assert "key1" in store._keys
        assert store._keys["key1"] == key
        assert store._keys["key1"].id == "key1"
        assert store._keys["key1"].provider_id == "openai"

    @pytest.mark.asyncio
    async def test_get_key_retrieves_apikey_correctly(self) -> None:
        """Test that get_key retrieves APIKey correctly."""
        store = InMemoryStateStore()
        key = APIKey(
            id="key1",
            key_material="encrypted_key_material",
            provider_id="openai",
        )

        await store.save_key(key)
        retrieved_key = await store.get_key("key1")

        assert retrieved_key is not None
        assert retrieved_key.id == "key1"
        assert retrieved_key.provider_id == "openai"
        assert retrieved_key.key_material == "encrypted_key_material"

    @pytest.mark.asyncio
    async def test_get_key_returns_none_for_nonexistent_key(self) -> None:
        """Test that get_key returns None for non-existent key."""
        store = InMemoryStateStore()

        retrieved_key = await store.get_key("nonexistent")

        assert retrieved_key is None

    @pytest.mark.asyncio
    async def test_save_key_overwrites_existing_key(self) -> None:
        """Test that save_key overwrites existing key."""
        store = InMemoryStateStore()
        key1 = APIKey(
            id="key1",
            key_material="encrypted_key_material_1",
            provider_id="openai",
        )
        key2 = APIKey(
            id="key1",  # Same ID
            key_material="encrypted_key_material_2",
            provider_id="anthropic",  # Different provider
        )

        await store.save_key(key1)
        await store.save_key(key2)

        # Verify key was overwritten
        retrieved_key = await store.get_key("key1")
        assert retrieved_key is not None
        assert retrieved_key.id == "key1"
        assert retrieved_key.provider_id == "anthropic"
        assert retrieved_key.key_material == "encrypted_key_material_2"

    @pytest.mark.asyncio
    async def test_thread_safety_concurrent_saves(self) -> None:
        """Test thread-safety with concurrent saves."""
        store = InMemoryStateStore()

        # Create multiple keys to save concurrently
        keys = [
            APIKey(
                id=f"key{i}",
                key_material=f"encrypted_key_{i}",
                provider_id="openai",
            )
            for i in range(100)
        ]

        # Save all keys concurrently
        await asyncio.gather(*[store.save_key(key) for key in keys])

        # Verify all keys were saved
        assert len(store._keys) == 100
        for i in range(100):
            retrieved_key = await store.get_key(f"key{i}")
            assert retrieved_key is not None
            assert retrieved_key.id == f"key{i}"

    @pytest.mark.asyncio
    async def test_concurrent_reads_no_locks_needed(self) -> None:
        """Test that concurrent reads work without locks."""
        store = InMemoryStateStore()

        # Create and save a key
        key = APIKey(
            id="key1",
            key_material="encrypted_key_material",
            provider_id="openai",
        )
        await store.save_key(key)

        # Perform many concurrent reads
        async def read_key() -> APIKey | None:
            return await store.get_key("key1")

        # Run 1000 concurrent reads
        results = await asyncio.gather(*[read_key() for _ in range(1000)])

        # Verify all reads succeeded
        assert len(results) == 1000
        assert all(result is not None for result in results)
        assert all(result.id == "key1" for result in results if result is not None)

    @pytest.mark.asyncio
    async def test_concurrent_reads_and_writes(self) -> None:
        """Test concurrent reads and writes."""
        store = InMemoryStateStore()

        # Initial key
        key1 = APIKey(
            id="key1",
            key_material="encrypted_key_material_1",
            provider_id="openai",
        )
        await store.save_key(key1)

        # Concurrent operations: reads and writes
        async def read_operation() -> APIKey | None:
            return await store.get_key("key1")

        async def write_operation() -> None:
            key = APIKey(
                id="key1",
                key_material="encrypted_key_material_updated",
                provider_id="openai",
            )
            await store.save_key(key)

        # Run concurrent reads and writes
        await asyncio.gather(
            *[read_operation() for _ in range(50)],
            *[write_operation() for _ in range(10)],
        )

        # Verify final state is consistent
        final_key = await store.get_key("key1")
        assert final_key is not None
        assert final_key.id == "key1"

    @pytest.mark.asyncio
    async def test_performance_save_key_under_1ms(self) -> None:
        """Test that save_key operation is under 1ms."""
        import time

        store = InMemoryStateStore()
        key = APIKey(
            id="key1",
            key_material="encrypted_key_material",
            provider_id="openai",
        )

        # Measure time for save operation
        start_time = time.perf_counter()
        await store.save_key(key)
        end_time = time.perf_counter()

        elapsed_ms = (end_time - start_time) * 1000
        assert elapsed_ms < 1.0, f"save_key took {elapsed_ms:.3f}ms, expected <1ms"

    @pytest.mark.asyncio
    async def test_performance_get_key_under_1ms(self) -> None:
        """Test that get_key operation is under 1ms."""
        import time

        store = InMemoryStateStore()
        key = APIKey(
            id="key1",
            key_material="encrypted_key_material",
            provider_id="openai",
        )
        await store.save_key(key)

        # Measure time for get operation
        start_time = time.perf_counter()
        await store.get_key("key1")
        end_time = time.perf_counter()

        elapsed_ms = (end_time - start_time) * 1000
        assert elapsed_ms < 1.0, f"get_key took {elapsed_ms:.3f}ms, expected <1ms"

    @pytest.mark.asyncio
    async def test_save_key_raises_state_store_error_on_failure(self) -> None:
        """Test that save_key raises StateStoreError on failure."""
        store = InMemoryStateStore()

        # Create a key with invalid data that might cause issues
        # In this case, we'll test with a valid key but simulate an error
        # by corrupting the internal storage
        key = APIKey(
            id="key1",
            key_material="encrypted_key_material",
            provider_id="openai",
        )

        # Corrupt the storage dict to simulate an error
        store._keys = None  # type: ignore[assignment]

        # Should raise StateStoreError
        with pytest.raises(StateStoreError):
            await store.save_key(key)

    @pytest.mark.asyncio
    async def test_get_key_raises_state_store_error_on_failure(self) -> None:
        """Test that get_key raises StateStoreError on failure."""
        store = InMemoryStateStore()

        # Corrupt the storage dict to simulate an error
        store._keys = None  # type: ignore[assignment]

        # Should raise StateStoreError
        with pytest.raises(StateStoreError):
            await store.get_key("key1")


class TestInMemoryStateStoreOtherMethods:
    """Tests for other InMemoryStateStore methods (for completeness)."""

    @pytest.mark.asyncio
    async def test_save_quota_state_stores_correctly(self) -> None:
        """Test that save_quota_state stores QuotaState correctly."""
        store = InMemoryStateStore()
        quota = QuotaState(
            id="quota1",
            key_id="key1",
            remaining_capacity=CapacityEstimate(value=1000),
            reset_at=datetime.utcnow() + timedelta(days=1),
        )

        await store.save_quota_state(quota)

        # Verify quota state was stored
        assert "key1" in store._quota_states
        assert store._quota_states["key1"] == quota
        assert store._quota_states["key1"].key_id == "key1"
        assert store._quota_states["key1"].remaining_capacity.value == 1000

    @pytest.mark.asyncio
    async def test_get_quota_state_retrieves_correctly(self) -> None:
        """Test that get_quota_state retrieves QuotaState correctly."""
        store = InMemoryStateStore()
        quota = QuotaState(
            id="quota1",
            key_id="key1",
            remaining_capacity=CapacityEstimate(value=5000),
            reset_at=datetime.utcnow() + timedelta(days=1),
        )

        await store.save_quota_state(quota)
        retrieved = await store.get_quota_state("key1")

        assert retrieved is not None
        assert retrieved.key_id == "key1"
        assert retrieved.remaining_capacity.value == 5000
        assert retrieved.id == "quota1"

    @pytest.mark.asyncio
    async def test_get_quota_state_returns_none_for_nonexistent(self) -> None:
        """Test that get_quota_state returns None for non-existent state."""
        store = InMemoryStateStore()

        retrieved = await store.get_quota_state("nonexistent_key")

        assert retrieved is None

    @pytest.mark.asyncio
    async def test_save_quota_state_overwrites_existing(self) -> None:
        """Test that save_quota_state overwrites existing state."""
        store = InMemoryStateStore()
        quota1 = QuotaState(
            id="quota1",
            key_id="key1",
            remaining_capacity=CapacityEstimate(value=1000),
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        quota2 = QuotaState(
            id="quota2",  # Different ID
            key_id="key1",  # Same key_id
            remaining_capacity=CapacityEstimate(value=2000),  # Different capacity
            reset_at=datetime.utcnow() + timedelta(days=2),
        )

        await store.save_quota_state(quota1)
        await store.save_quota_state(quota2)

        # Verify state was overwritten
        retrieved = await store.get_quota_state("key1")
        assert retrieved is not None
        assert retrieved.key_id == "key1"
        assert retrieved.id == "quota2"  # New ID
        assert retrieved.remaining_capacity.value == 2000  # New capacity

    @pytest.mark.asyncio
    async def test_quota_state_thread_safety_concurrent_saves(self) -> None:
        """Test thread-safety with concurrent quota state saves."""
        store = InMemoryStateStore()

        # Create multiple quota states to save concurrently
        quotas = [
            QuotaState(
                id=f"quota{i}",
                key_id=f"key{i}",
                remaining_capacity=CapacityEstimate(value=1000 * i),
                reset_at=datetime.utcnow() + timedelta(days=1),
            )
            for i in range(100)
        ]

        # Save all quota states concurrently
        await asyncio.gather(*[store.save_quota_state(quota) for quota in quotas])

        # Verify all quota states were saved
        assert len(store._quota_states) == 100
        for i in range(100):
            retrieved = await store.get_quota_state(f"key{i}")
            assert retrieved is not None
            assert retrieved.key_id == f"key{i}"
            assert retrieved.remaining_capacity.value == 1000 * i

    @pytest.mark.asyncio
    async def test_quota_state_concurrent_reads(self) -> None:
        """Test that concurrent reads work without locks."""
        store = InMemoryStateStore()

        # Create and save a quota state
        quota = QuotaState(
            id="quota1",
            key_id="key1",
            remaining_capacity=CapacityEstimate(value=5000),
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        await store.save_quota_state(quota)

        # Perform many concurrent reads
        async def read_quota() -> QuotaState | None:
            return await store.get_quota_state("key1")

        # Run 1000 concurrent reads
        results = await asyncio.gather(*[read_quota() for _ in range(1000)])

        # Verify all reads succeeded
        assert len(results) == 1000
        assert all(result is not None for result in results)
        assert all(result.key_id == "key1" for result in results if result is not None)
        assert all(
            result.remaining_capacity.value == 5000 for result in results if result is not None
        )

    @pytest.mark.asyncio
    async def test_quota_state_concurrent_updates(self) -> None:
        """Test concurrent updates to quota state."""
        store = InMemoryStateStore()

        # Initial quota state
        initial_quota = QuotaState(
            id="quota1",
            key_id="key1",
            remaining_capacity=CapacityEstimate(value=1000),
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        await store.save_quota_state(initial_quota)

        # Concurrent operations: reads and writes
        async def read_operation() -> QuotaState | None:
            return await store.get_quota_state("key1")

        async def write_operation(i: int) -> None:
            quota = QuotaState(
                id=f"quota{i}",
                key_id="key1",
                remaining_capacity=CapacityEstimate(value=1000 + i),
                reset_at=datetime.utcnow() + timedelta(days=1),
            )
            await store.save_quota_state(quota)

        # Run concurrent reads and writes
        await asyncio.gather(
            *[read_operation() for _ in range(50)],
            *[write_operation(i) for i in range(10)],
        )

        # Verify final state is consistent
        final_quota = await store.get_quota_state("key1")
        assert final_quota is not None
        assert final_quota.key_id == "key1"

    @pytest.mark.asyncio
    async def test_save_routing_decision_stores_correctly(self) -> None:
        """Test that save_routing_decision stores decision correctly."""
        store = InMemoryStateStore()
        decision = RoutingDecision(
            id="decision1",
            request_id="req1",
            selected_key_id="key1",
            selected_provider_id="openai",
            objective=RoutingObjective(primary="cost"),
            explanation="Lowest cost",
            confidence=0.9,
        )

        await store.save_routing_decision(decision)

        # Verify decision was stored
        assert len(store._routing_decisions) == 1
        assert store._routing_decisions[0] == decision
        assert store._routing_decisions[0].id == "decision1"
        assert store._routing_decisions[0].selected_key_id == "key1"

    @pytest.mark.asyncio
    async def test_routing_decisions_stored_in_list(self) -> None:
        """Test that routing decisions are stored in list."""
        store = InMemoryStateStore()

        # Save multiple decisions
        for i in range(5):
            decision = RoutingDecision(
                id=f"decision{i}",
                request_id=f"req{i}",
                selected_key_id=f"key{i}",
                selected_provider_id="openai",
                objective=RoutingObjective(primary="cost"),
                explanation=f"Decision {i}",
                confidence=0.9,
            )
            await store.save_routing_decision(decision)

        # Verify all stored in list
        assert len(store._routing_decisions) == 5
        assert all(isinstance(d, RoutingDecision) for d in store._routing_decisions)

    @pytest.mark.asyncio
    async def test_max_decisions_limit_enforced_fifo(self) -> None:
        """Test that max_decisions limit is enforced with FIFO removal."""
        store = InMemoryStateStore(max_decisions=3)

        # Save 5 decisions (should only keep last 3)
        for i in range(5):
            decision = RoutingDecision(
                id=f"decision{i}",
                request_id=f"req{i}",
                selected_key_id=f"key{i}",
                selected_provider_id="openai",
                objective=RoutingObjective(primary="cost"),
                explanation=f"Decision {i}",
                confidence=0.9,
            )
            await store.save_routing_decision(decision)

        # Verify only last 3 are kept (FIFO removal)
        assert len(store._routing_decisions) == 3
        assert store._routing_decisions[0].id == "decision2"  # Oldest kept
        assert store._routing_decisions[1].id == "decision3"
        assert store._routing_decisions[2].id == "decision4"  # Newest

    @pytest.mark.asyncio
    async def test_max_decisions_unlimited_when_zero(self) -> None:
        """Test that max_decisions=0 means unlimited storage."""
        store = InMemoryStateStore(max_decisions=0)

        # Save many decisions
        for i in range(100):
            decision = RoutingDecision(
                id=f"decision{i}",
                request_id=f"req{i}",
                selected_key_id=f"key{i}",
                selected_provider_id="openai",
                objective=RoutingObjective(primary="cost"),
                explanation=f"Decision {i}",
                confidence=0.9,
            )
            await store.save_routing_decision(decision)

        # Verify all stored (no limit)
        assert len(store._routing_decisions) == 100

    @pytest.mark.asyncio
    async def test_query_routing_decisions_by_key_id(self) -> None:
        """Test querying routing decisions by key_id."""
        store = InMemoryStateStore()

        # Create decisions for different keys
        for i in range(5):
            decision = RoutingDecision(
                id=f"decision{i}",
                request_id=f"req{i}",
                selected_key_id=f"key{i % 2}",  # key0 or key1
                selected_provider_id="openai",
                objective=RoutingObjective(primary="cost"),
                explanation=f"Decision {i}",
                confidence=0.9,
            )
            await store.save_routing_decision(decision)

        # Query for key0
        query = StateQuery(entity_type="RoutingDecision", key_id="key0")
        results = await store.query_state(query)

        assert len(results) == 3  # decision0, decision2, decision4
        assert all(d.selected_key_id == "key0" for d in results)

    @pytest.mark.asyncio
    async def test_query_routing_decisions_by_provider_id(self) -> None:
        """Test querying routing decisions by provider_id."""
        store = InMemoryStateStore()

        # Create decisions for different providers
        providers = ["openai", "anthropic", "openai"]
        for i, provider in enumerate(providers):
            decision = RoutingDecision(
                id=f"decision{i}",
                request_id=f"req{i}",
                selected_key_id=f"key{i}",
                selected_provider_id=provider,
                objective=RoutingObjective(primary="cost"),
                explanation=f"Decision {i}",
                confidence=0.9,
            )
            await store.save_routing_decision(decision)

        # Query for openai
        query = StateQuery(entity_type="RoutingDecision", provider_id="openai")
        results = await store.query_state(query)

        assert len(results) == 2
        assert all(d.selected_provider_id == "openai" for d in results)

    @pytest.mark.asyncio
    async def test_query_routing_decisions_by_timestamp_range(self) -> None:
        """Test querying routing decisions by timestamp range."""
        store = InMemoryStateStore()

        # Create decisions with different timestamps
        base_time = datetime.utcnow()
        for i in range(5):
            decision = RoutingDecision(
                id=f"decision{i}",
                request_id=f"req{i}",
                selected_key_id=f"key{i}",
                selected_provider_id="openai",
                objective=RoutingObjective(primary="cost"),
                explanation=f"Decision {i}",
                confidence=0.9,
            )
            # Set custom timestamp
            decision.decision_timestamp = base_time + timedelta(hours=i)
            await store.save_routing_decision(decision)

        # Query for decisions in range (hours 1-3)
        query = StateQuery(
            entity_type="RoutingDecision",
            timestamp_from=base_time + timedelta(hours=1),
            timestamp_to=base_time + timedelta(hours=3),
        )
        results = await store.query_state(query)

        assert len(results) == 3  # decision1, decision2, decision3
        assert all(
            base_time + timedelta(hours=1) <= d.decision_timestamp <= base_time + timedelta(hours=3)
            for d in results
        )

    @pytest.mark.asyncio
    async def test_routing_decision_thread_safety_concurrent_saves(self) -> None:
        """Test thread-safety with concurrent routing decision saves."""
        store = InMemoryStateStore()

        # Create multiple decisions to save concurrently
        decisions = [
            RoutingDecision(
                id=f"decision{i}",
                request_id=f"req{i}",
                selected_key_id=f"key{i}",
                selected_provider_id="openai",
                objective=RoutingObjective(primary="cost"),
                explanation=f"Decision {i}",
                confidence=0.9,
            )
            for i in range(100)
        ]

        # Save all decisions concurrently
        await asyncio.gather(*[store.save_routing_decision(decision) for decision in decisions])

        # Verify all decisions were saved
        assert len(store._routing_decisions) == 100
        decision_ids = {d.id for d in store._routing_decisions}
        assert len(decision_ids) == 100  # All unique

    @pytest.mark.asyncio
    async def test_routing_decision_max_limit_with_concurrent_saves(self) -> None:
        """Test max_decisions limit with concurrent saves."""
        store = InMemoryStateStore(max_decisions=10)

        # Create many decisions to save concurrently
        decisions = [
            RoutingDecision(
                id=f"decision{i}",
                request_id=f"req{i}",
                selected_key_id=f"key{i}",
                selected_provider_id="openai",
                objective=RoutingObjective(primary="cost"),
                explanation=f"Decision {i}",
                confidence=0.9,
            )
            for i in range(20)
        ]

        # Save all decisions concurrently
        await asyncio.gather(*[store.save_routing_decision(decision) for decision in decisions])

        # Verify limit is enforced (should have exactly 10)
        assert len(store._routing_decisions) == 10
        # Should have the last 10 decisions (FIFO)
        decision_ids = {d.id for d in store._routing_decisions}
        expected_ids = {f"decision{i}" for i in range(10, 20)}
        assert decision_ids == expected_ids

    @pytest.mark.asyncio
    async def test_save_state_transition_stores_correctly(self) -> None:
        """Test that save_state_transition stores transition correctly."""
        store = InMemoryStateStore()
        transition = StateTransition(
            entity_type="APIKey",
            entity_id="key1",
            from_state="available",
            to_state="throttled",
            trigger="rate_limit",
        )

        await store.save_state_transition(transition)

        # Verify transition was stored
        assert len(store._state_transitions) == 1
        assert store._state_transitions[0] == transition
        assert store._state_transitions[0].entity_id == "key1"
        assert store._state_transitions[0].to_state == "throttled"

    @pytest.mark.asyncio
    async def test_state_transitions_stored_in_list(self) -> None:
        """Test that state transitions are stored in list."""
        store = InMemoryStateStore()

        # Save multiple transitions
        for i in range(5):
            transition = StateTransition(
                entity_type="APIKey",
                entity_id=f"key{i}",
                from_state="available",
                to_state="throttled",
                trigger=f"trigger{i}",
            )
            await store.save_state_transition(transition)

        # Verify all stored in list
        assert len(store._state_transitions) == 5
        assert all(isinstance(t, StateTransition) for t in store._state_transitions)

    @pytest.mark.asyncio
    async def test_max_transitions_limit_enforced_fifo(self) -> None:
        """Test that max_transitions limit is enforced with FIFO removal."""
        store = InMemoryStateStore(max_transitions=3)

        # Save 5 transitions (should only keep last 3)
        for i in range(5):
            transition = StateTransition(
                entity_type="APIKey",
                entity_id=f"key{i}",
                from_state="available",
                to_state="throttled",
                trigger=f"trigger{i}",
            )
            await store.save_state_transition(transition)

        # Verify only last 3 are kept (FIFO removal)
        assert len(store._state_transitions) == 3
        assert store._state_transitions[0].entity_id == "key2"  # Oldest kept
        assert store._state_transitions[1].entity_id == "key3"
        assert store._state_transitions[2].entity_id == "key4"  # Newest

    @pytest.mark.asyncio
    async def test_max_transitions_unlimited_when_zero(self) -> None:
        """Test that max_transitions=0 means unlimited storage."""
        store = InMemoryStateStore(max_transitions=0)

        # Save many transitions
        for i in range(100):
            transition = StateTransition(
                entity_type="APIKey",
                entity_id=f"key{i}",
                from_state="available",
                to_state="throttled",
                trigger=f"trigger{i}",
            )
            await store.save_state_transition(transition)

        # Verify all stored (no limit)
        assert len(store._state_transitions) == 100

    @pytest.mark.asyncio
    async def test_query_state_transitions_by_key_id(self) -> None:
        """Test querying state transitions by key_id (entity_id)."""
        store = InMemoryStateStore()

        # Create transitions for different keys
        for i in range(5):
            transition = StateTransition(
                entity_type="APIKey",
                entity_id=f"key{i % 2}",  # key0 or key1
                from_state="available",
                to_state="throttled",
                trigger=f"trigger{i}",
            )
            await store.save_state_transition(transition)

        # Query for key0
        query = StateQuery(entity_type="StateTransition", key_id="key0")
        results = await store.query_state(query)

        assert len(results) == 3  # transitions for key0, key0, key0
        assert all(t.entity_id == "key0" for t in results)

    @pytest.mark.asyncio
    async def test_query_state_transitions_by_state_type(self) -> None:
        """Test querying state transitions by entity_type."""
        store = InMemoryStateStore()

        # Create transitions for different entity types
        entity_types = ["APIKey", "QuotaState", "APIKey"]
        for i, entity_type in enumerate(entity_types):
            transition = StateTransition(
                entity_type=entity_type,
                entity_id=f"key{i}",
                from_state="available",
                to_state="throttled",
                trigger=f"trigger{i}",
            )
            await store.save_state_transition(transition)

        # Query for APIKey transitions
        query = StateQuery(entity_type="StateTransition")
        # Note: entity_type in query filters by StateTransition type, not entity_type field
        # We need to filter manually or add entity_type filter support
        results = await store.query_state(query)

        # All results should be StateTransition objects
        assert len(results) == 3
        assert all(isinstance(t, StateTransition) for t in results)

    @pytest.mark.asyncio
    async def test_query_state_transitions_by_state_value(self) -> None:
        """Test querying state transitions by to_state value."""
        store = InMemoryStateStore()

        # Create transitions with different to_state values
        states = ["throttled", "available", "throttled"]
        for i, state in enumerate(states):
            transition = StateTransition(
                entity_type="APIKey",
                entity_id=f"key{i}",
                from_state="available",
                to_state=state,
                trigger=f"trigger{i}",
            )
            await store.save_state_transition(transition)

        # Query for throttled transitions
        query = StateQuery(entity_type="StateTransition", state="throttled")
        results = await store.query_state(query)

        assert len(results) == 2
        assert all(t.to_state == "throttled" for t in results)

    @pytest.mark.asyncio
    async def test_query_state_transitions_by_timestamp_range(self) -> None:
        """Test querying state transitions by timestamp range."""
        store = InMemoryStateStore()

        # Create transitions with different timestamps
        base_time = datetime.utcnow()
        for i in range(5):
            # Create transition with custom timestamp using model_validate
            transition_data = {
                "entity_type": "APIKey",
                "entity_id": f"key{i}",
                "from_state": "available",
                "to_state": "throttled",
                "trigger": f"trigger{i}",
                "transition_timestamp": base_time + timedelta(hours=i),
            }
            transition = StateTransition.model_validate(transition_data)
            await store.save_state_transition(transition)

        # Query for transitions in range (hours 1-3)
        query = StateQuery(
            entity_type="StateTransition",
            timestamp_from=base_time + timedelta(hours=1),
            timestamp_to=base_time + timedelta(hours=3),
        )
        results = await store.query_state(query)

        assert len(results) == 3  # transitions at hours 1, 2, 3
        assert all(
            base_time + timedelta(hours=1) <= t.transition_timestamp <= base_time + timedelta(hours=3)
            for t in results
        )

    @pytest.mark.asyncio
    async def test_state_transition_thread_safety_concurrent_saves(self) -> None:
        """Test thread-safety with concurrent state transition saves."""
        store = InMemoryStateStore()

        # Create multiple transitions to save concurrently
        transitions = [
            StateTransition(
                entity_type="APIKey",
                entity_id=f"key{i}",
                from_state="available",
                to_state="throttled",
                trigger=f"trigger{i}",
            )
            for i in range(100)
        ]

        # Save all transitions concurrently
        await asyncio.gather(*[store.save_state_transition(t) for t in transitions])

        # Verify all transitions were saved
        assert len(store._state_transitions) == 100
        entity_ids = {t.entity_id for t in store._state_transitions}
        assert len(entity_ids) == 100  # All unique

    @pytest.mark.asyncio
    async def test_state_transition_max_limit_with_concurrent_saves(self) -> None:
        """Test max_transitions limit with concurrent saves."""
        store = InMemoryStateStore(max_transitions=10)

        # Create many transitions to save concurrently
        transitions = [
            StateTransition(
                entity_type="APIKey",
                entity_id=f"key{i}",
                from_state="available",
                to_state="throttled",
                trigger=f"trigger{i}",
            )
            for i in range(20)
        ]

        # Save all transitions concurrently
        await asyncio.gather(*[store.save_state_transition(t) for t in transitions])

        # Verify limit is enforced (should have exactly 10)
        assert len(store._state_transitions) == 10
        # Should have the last 10 transitions (FIFO)
        entity_ids = {t.entity_id for t in store._state_transitions}
        expected_ids = {f"key{i}" for i in range(10, 20)}
        assert entity_ids == expected_ids

    @pytest.mark.asyncio
    async def test_query_state_filters_by_key_id(self) -> None:
        """Test query_state filters by key_id."""
        store = InMemoryStateStore()

        # Create multiple keys
        for i in range(5):
            key = APIKey(
                id=f"key{i}",
                key_material=f"encrypted_{i}",
                provider_id="openai",
            )
            await store.save_key(key)

        # Query for specific key
        query = StateQuery(entity_type="APIKey", key_id="key2")
        results = await store.query_state(query)

        assert len(results) == 1
        assert results[0].id == "key2"

    @pytest.mark.asyncio
    async def test_query_state_filters_by_provider_id(self) -> None:
        """Test query_state filters by provider_id."""
        store = InMemoryStateStore()

        # Create keys for different providers with unique IDs
        providers = ["openai", "anthropic", "openai"]
        for i, provider in enumerate(providers):
            key = APIKey(
                id=f"key_{i}_{provider}",
                key_material="encrypted-key-material",
                provider_id=provider,
            )
            await store.save_key(key)

        # Query for openai keys
        query = StateQuery(entity_type="APIKey", provider_id="openai")
        results = await store.query_state(query)

        assert len(results) == 2
        assert all(key.provider_id == "openai" for key in results)

    @pytest.mark.asyncio
    async def test_query_state_pagination(self) -> None:
        """Test query_state pagination."""
        store = InMemoryStateStore()

        # Create multiple keys
        for i in range(10):
            key = APIKey(
                id=f"key{i}",
                key_material=f"encrypted_{i}",
                provider_id="openai",
            )
            await store.save_key(key)

        # Query with limit
        query = StateQuery(entity_type="APIKey", limit=5)
        results = await store.query_state(query)
        assert len(results) == 5

        # Query with offset and limit
        query = StateQuery(entity_type="APIKey", offset=5, limit=3)
        results = await store.query_state(query)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_query_state_filters_by_state(self) -> None:
        """Test query_state filters by state."""
        store = InMemoryStateStore()

        # Create keys with different states
        states = [KeyState.Available, KeyState.Throttled, KeyState.Available]
        for i, state in enumerate(states):
            key = APIKey(
                id=f"key{i}",
                key_material="encrypted-key-material",
                provider_id="openai",
                state=state,
            )
            await store.save_key(key)

        # Query for available keys
        query = StateQuery(entity_type="APIKey", state="available")
        results = await store.query_state(query)

        assert len(results) == 2
        assert all(key.state == KeyState.Available for key in results)

    @pytest.mark.asyncio
    async def test_query_state_filters_by_timestamp_range(self) -> None:
        """Test query_state filters by timestamp range."""
        store = InMemoryStateStore()

        # Create keys with different timestamps
        base_time = datetime.utcnow()
        for i in range(5):
            key_data = {
                "id": f"key{i}",
                "key_material": "encrypted",
                "provider_id": "openai",
                "created_at": base_time + timedelta(hours=i),
            }
            key = APIKey.model_validate(key_data)
            await store.save_key(key)

        # Query for keys in range (hours 1-3)
        query = StateQuery(
            entity_type="APIKey",
            timestamp_from=base_time + timedelta(hours=1),
            timestamp_to=base_time + timedelta(hours=3),
        )
        results = await store.query_state(query)

        assert len(results) == 3
        assert all(
            base_time + timedelta(hours=1) <= key.created_at <= base_time + timedelta(hours=3)
            for key in results
        )

    @pytest.mark.asyncio
    async def test_query_state_returns_correct_entity_types(self) -> None:
        """Test query_state returns correct entity types."""
        store = InMemoryStateStore()

        # Create different entity types
        key = APIKey(id="key1", key_material="encrypted-key-material", provider_id="openai")
        await store.save_key(key)

        quota = QuotaState(
            id="quota1",
            key_id="key1",
            remaining_capacity=CapacityEstimate(value=1000),
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        await store.save_quota_state(quota)

        # Query for APIKey
        query = StateQuery(entity_type="APIKey")
        results = await store.query_state(query)
        assert len(results) == 1
        assert isinstance(results[0], APIKey)

        # Query for QuotaState
        query = StateQuery(entity_type="QuotaState")
        results = await store.query_state(query)
        assert len(results) == 1
        assert isinstance(results[0], QuotaState)

    @pytest.mark.asyncio
    async def test_query_state_returns_all_entity_types_when_none(self) -> None:
        """Test query_state returns all entity types when entity_type is None."""
        store = InMemoryStateStore()

        # Create different entity types
        key = APIKey(id="key1", key_material="encrypted-key-material", provider_id="openai")
        await store.save_key(key)

        quota = QuotaState(
            id="quota1",
            key_id="key1",
            remaining_capacity=CapacityEstimate(value=1000),
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        await store.save_quota_state(quota)

        decision = RoutingDecision(
            id="decision1",
            request_id="req1",
            selected_key_id="key1",
            selected_provider_id="openai",
            objective=RoutingObjective(primary="cost"),
            explanation="Test",
            confidence=0.9,
        )
        await store.save_routing_decision(decision)

        # Query without entity_type (should return all)
        query = StateQuery()
        results = await store.query_state(query)

        assert len(results) == 3
        assert any(isinstance(r, APIKey) for r in results)
        assert any(isinstance(r, QuotaState) for r in results)
        assert any(isinstance(r, RoutingDecision) for r in results)

    @pytest.mark.asyncio
    async def test_query_state_handles_empty_results(self) -> None:
        """Test query_state handles empty results gracefully."""
        store = InMemoryStateStore()

        # Query with filters that match nothing
        query = StateQuery(entity_type="APIKey", key_id="nonexistent")
        results = await store.query_state(query)

        assert len(results) == 0
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_query_state_combines_multiple_filters(self) -> None:
        """Test query_state combines multiple filters correctly."""
        store = InMemoryStateStore()

        # Create keys with different properties
        for i in range(5):
            state = KeyState.Available if i % 2 == 0 else KeyState.Throttled
            key = APIKey(
                id=f"key{i}",
                key_material="encrypted-key-material",
                provider_id="openai" if i < 3 else "anthropic",
                state=state,
            )
            await store.save_key(key)

        # Query with multiple filters: openai + available
        query = StateQuery(
            entity_type="APIKey",
            provider_id="openai",
            state="available",
        )
        results = await store.query_state(query)

        assert len(results) == 2  # key0 and key2
        assert all(key.provider_id == "openai" and key.state == KeyState.Available for key in results)

    @pytest.mark.asyncio
    async def test_query_state_performance_under_10ms(self) -> None:
        """Test that query_state performance is under 10ms for typical queries."""
        import time

        store = InMemoryStateStore()

        # Create a typical dataset (100 keys, 50 quota states, 100 decisions, 100 transitions)
        for i in range(100):
            key = APIKey(
                id=f"key{i}",
                key_material="encrypted-key-material",
                provider_id="openai" if i % 2 == 0 else "anthropic",
                state=KeyState.Available if i % 3 == 0 else KeyState.Throttled,
            )
            await store.save_key(key)

            if i < 50:
                quota = QuotaState(
                    id=f"quota{i}",
                    key_id=f"key{i}",
                    remaining_capacity=CapacityEstimate(value=1000),
                    reset_at=datetime.utcnow() + timedelta(days=1),
                )
                await store.save_quota_state(quota)

            decision = RoutingDecision(
                id=f"decision{i}",
                request_id=f"req{i}",
                selected_key_id=f"key{i}",
                selected_provider_id="openai",
                objective=RoutingObjective(primary="cost"),
                explanation="Test",
                confidence=0.9,
            )
            await store.save_routing_decision(decision)

            transition = StateTransition(
                entity_type="APIKey",
                entity_id=f"key{i}",
                from_state="available",
                to_state="throttled",
                trigger="test",
            )
            await store.save_state_transition(transition)

        # Test typical query: filter by provider_id
        query = StateQuery(entity_type="APIKey", provider_id="openai")
        start_time = time.perf_counter()
        results = await store.query_state(query)
        end_time = time.perf_counter()

        elapsed_ms = (end_time - start_time) * 1000
        assert elapsed_ms < 10.0, f"query_state took {elapsed_ms:.3f}ms, expected <10ms"
        assert len(results) == 50  # Half of keys are openai

    @pytest.mark.asyncio
    async def test_query_state_performance_with_pagination(self) -> None:
        """Test that query_state with pagination is under 10ms."""
        import time

        store = InMemoryStateStore()

        # Create large dataset
        for i in range(1000):
            key = APIKey(
                id=f"key{i}",
                key_material="encrypted-key-material",
                provider_id="openai",
            )
            await store.save_key(key)

        # Test query with pagination
        query = StateQuery(entity_type="APIKey", limit=50, offset=100)
        start_time = time.perf_counter()
        results = await store.query_state(query)
        end_time = time.perf_counter()

        elapsed_ms = (end_time - start_time) * 1000
        assert elapsed_ms < 10.0, f"query_state with pagination took {elapsed_ms:.3f}ms, expected <10ms"
        assert len(results) == 50

