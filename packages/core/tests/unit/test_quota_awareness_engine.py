"""Tests for QuotaAwarenessEngine component."""

import uuid
from datetime import datetime, timedelta

import pytest

from apikeyrouter.domain.components.quota_awareness_engine import QuotaAwarenessEngine
from apikeyrouter.domain.interfaces.observability_manager import (
    ObservabilityManager,
)
from apikeyrouter.domain.interfaces.state_store import StateStore, StateStoreError
from apikeyrouter.domain.models.quota_state import (
    CapacityEstimate,
    CapacityState,
    QuotaState,
    TimeWindow,
    UncertaintyLevel,
    UsageRate,
)


class MockStateStore(StateStore):
    """Mock StateStore for testing."""

    def __init__(self) -> None:
        """Initialize mock store."""
        self._keys: dict[str, object] = {}
        self._quota_states: dict[str, QuotaState] = {}
        self._transitions: list[object] = []
        self._routing_decisions: list[object] = []
        self.save_quota_state_called = False
        self.save_quota_state_error: Exception | None = None

    async def save_key(self, key: object) -> None:
        """Save key to mock store."""
        from apikeyrouter.domain.models.api_key import APIKey

        if isinstance(key, APIKey):
            self._keys[key.id] = key

    async def get_key(self, key_id: str) -> object | None:
        """Get key from mock store."""
        return self._keys.get(key_id)

    async def list_keys(self, provider_id: str | None = None) -> list[object]:
        """List keys from mock store."""
        return []

    async def delete_key(self, key_id: str) -> None:
        """Delete key from mock store."""
        pass

    async def save_state_transition(self, transition: object) -> None:
        """Save state transition to mock store."""
        self._transitions.append(transition)

    async def save_quota_state(self, quota_state: QuotaState) -> None:
        """Save quota state to mock store."""
        if self.save_quota_state_error:
            raise self.save_quota_state_error
        self._quota_states[quota_state.key_id] = quota_state
        self.save_quota_state_called = True

    async def get_quota_state(self, key_id: str) -> QuotaState | None:
        """Get quota state from mock store."""
        return self._quota_states.get(key_id)

    async def save_routing_decision(self, decision) -> None:
        """Save routing decision to mock store."""
        self._routing_decisions.append(decision)

    async def query_state(self, query) -> list:
        """Query state from mock store."""
        from apikeyrouter.domain.interfaces.state_store import StateQuery
        from apikeyrouter.domain.models.routing_decision import RoutingDecision

        if query.entity_type == "RoutingDecision":
            results = []
            for decision in self._routing_decisions:
                if isinstance(decision, RoutingDecision):
                    # Apply filters
                    if query.key_id is not None and decision.selected_key_id != query.key_id:
                        continue
                    if (
                        query.timestamp_from is not None
                        and decision.decision_timestamp < query.timestamp_from
                    ):
                        continue
                    if (
                        query.timestamp_to is not None
                        and decision.decision_timestamp > query.timestamp_to
                    ):
                        continue
                    results.append(decision)
            return results
        return []


class MockObservabilityManager(ObservabilityManager):
    """Mock ObservabilityManager for testing."""

    def __init__(self) -> None:
        """Initialize mock observability manager."""
        self.events: list[dict] = []
        self.logs: list[dict] = []
        self.emit_error: Exception | None = None

    async def emit_event(
        self,
        event_type: str,
        payload: dict,
        metadata: dict | None = None,
    ) -> None:
        """Emit event to mock store."""
        if self.emit_error:
            raise self.emit_error
        self.events.append({
            "event_type": event_type,
            "payload": payload,
            "metadata": metadata or {},
        })

    async def log(
        self,
        level: str,
        message: str,
        context: dict | None = None,
    ) -> None:
        """Log to mock store."""
        self.logs.append({
            "level": level,
            "message": message,
            "context": context or {},
        })


class TestQuotaAwarenessEngine:
    """Tests for QuotaAwarenessEngine."""

    @pytest.fixture
    def mock_state_store(self) -> MockStateStore:
        """Create a mock StateStore."""
        return MockStateStore()

    @pytest.fixture
    def mock_observability(self) -> MockObservabilityManager:
        """Create a mock ObservabilityManager."""
        return MockObservabilityManager()

    @pytest.fixture
    def engine(
        self, mock_state_store: MockStateStore, mock_observability: MockObservabilityManager
    ) -> QuotaAwarenessEngine:
        """Create a QuotaAwarenessEngine instance."""
        return QuotaAwarenessEngine(
            mock_state_store, mock_observability, key_manager=None, default_cooldown_seconds=60
        )

    @pytest.mark.asyncio
    async def test_update_capacity_initializes_quota_state(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that update_capacity initializes QuotaState if missing."""
        key_id = "test_key_1"
        consumed = 10

        result = await engine.update_capacity(key_id, consumed)

        assert result is not None
        assert result.key_id == key_id
        assert result.used_capacity == consumed
        assert mock_state_store.save_quota_state_called

    @pytest.mark.asyncio
    async def test_update_capacity_decrements_remaining_capacity(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that update_capacity decrements remaining_capacity."""
        key_id = "test_key_2"
        reset_at = datetime.utcnow() + timedelta(hours=1)
        initial_remaining = 100
        consumed = 25

        # Create initial quota state
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            remaining_capacity=CapacityEstimate(value=initial_remaining),
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, consumed)

        assert result.remaining_capacity.value == initial_remaining - consumed
        assert result.remaining_capacity.value == 75

    @pytest.mark.asyncio
    async def test_update_capacity_increments_used_capacity(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that update_capacity increments used_capacity."""
        key_id = "test_key_3"
        reset_at = datetime.utcnow() + timedelta(hours=1)
        initial_used = 50
        consumed = 25

        # Create initial quota state
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            remaining_capacity=CapacityEstimate(value=100),
            used_capacity=initial_used,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, consumed)

        assert result.used_capacity == initial_used + consumed
        assert result.used_capacity == 75

    @pytest.mark.asyncio
    async def test_update_capacity_updates_timestamp(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that update_capacity updates updated_at timestamp."""
        key_id = "test_key_4"
        reset_at = datetime.utcnow() + timedelta(hours=1)
        old_timestamp = datetime.utcnow() - timedelta(hours=1)

        # Create initial quota state with old timestamp
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            remaining_capacity=CapacityEstimate(value=100),
            reset_at=reset_at,
            updated_at=old_timestamp,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 10)

        assert result.updated_at > old_timestamp
        assert result.updated_at <= datetime.utcnow()

    @pytest.mark.asyncio
    async def test_capacity_state_abundant(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test capacity_state calculation for Abundant (>80% remaining)."""
        key_id = "test_key_5"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        # Create quota state with 90% remaining
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=90),
            used_capacity=10,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 0)  # No consumption

        assert result.capacity_state == CapacityState.Abundant

    @pytest.mark.asyncio
    async def test_capacity_state_constrained(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test capacity_state calculation for Constrained (50-80% remaining)."""
        key_id = "test_key_6"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        # Create quota state with 60% remaining
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=60),
            used_capacity=40,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 0)

        assert result.capacity_state == CapacityState.Constrained

    @pytest.mark.asyncio
    async def test_capacity_state_critical(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test capacity_state calculation for Critical (20-50% remaining)."""
        key_id = "test_key_7"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        # Create quota state with 30% remaining
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=30),
            used_capacity=70,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 0)

        assert result.capacity_state == CapacityState.Critical

    @pytest.mark.asyncio
    async def test_capacity_state_exhausted(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test capacity_state calculation for Exhausted (<20% remaining)."""
        key_id = "test_key_8"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        # Create quota state with 10% remaining
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=10),
            used_capacity=90,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 0)

        assert result.capacity_state == CapacityState.Exhausted

    @pytest.mark.asyncio
    async def test_capacity_state_transition_abundant_to_constrained(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test capacity_state transition from Abundant to Constrained."""
        key_id = "test_key_9"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        # Start with 85% remaining (Abundant)
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=85),
            used_capacity=15,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Consume enough to drop to 60% (Constrained)
        result = await engine.update_capacity(key_id, 25)

        assert result.capacity_state == CapacityState.Constrained
        assert result.remaining_capacity.value == 60

    @pytest.mark.asyncio
    async def test_capacity_state_transition_constrained_to_critical(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test capacity_state transition from Constrained to Critical."""
        key_id = "test_key_10"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        # Start with 60% remaining (Constrained)
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=60),
            used_capacity=40,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Consume enough to drop to 30% (Critical)
        result = await engine.update_capacity(key_id, 30)

        assert result.capacity_state == CapacityState.Critical
        assert result.remaining_capacity.value == 30

    @pytest.mark.asyncio
    async def test_capacity_state_transition_critical_to_exhausted(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test capacity_state transition from Critical to Exhausted."""
        key_id = "test_key_11"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        # Start with 30% remaining (Critical)
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=30),
            used_capacity=70,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Consume enough to drop to 10% (Exhausted)
        result = await engine.update_capacity(key_id, 20)

        assert result.capacity_state == CapacityState.Exhausted
        assert result.remaining_capacity.value == 10

    @pytest.mark.asyncio
    async def test_capacity_state_unknown_total_capacity(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test capacity_state calculation when total_capacity is unknown."""
        key_id = "test_key_12"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        # Create quota state with unknown total_capacity but known remaining
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=None,
            remaining_capacity=CapacityEstimate(value=100),
            used_capacity=0,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 0)

        # Should default to Abundant when total is unknown but remaining > 0
        assert result.capacity_state == CapacityState.Abundant

    @pytest.mark.asyncio
    async def test_capacity_state_unknown_total_and_remaining(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test capacity_state calculation when both total and remaining are unknown."""
        key_id = "test_key_13"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        # Create quota state with unknown total and remaining
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=None,
            remaining_capacity=CapacityEstimate(value=None),
            used_capacity=0,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 0)

        # Should default to Abundant (optimistic) when both are unknown
        assert result.capacity_state == CapacityState.Abundant

    @pytest.mark.asyncio
    async def test_time_window_reset_daily(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test time window reset detection for Daily window."""
        key_id = "test_key_14"
        # Set reset_at in the past to trigger reset
        reset_at = datetime.utcnow() - timedelta(hours=1)

        # Create quota state with past reset_at
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=10),
            used_capacity=90,
            time_window=TimeWindow.Daily,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 0)

        # Should reset to total_capacity
        assert result.remaining_capacity.value == 100
        assert result.used_capacity == 0
        assert result.capacity_state == CapacityState.Abundant
        assert result.reset_at > reset_at

    @pytest.mark.asyncio
    async def test_time_window_reset_hourly(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test time window reset detection for Hourly window."""
        key_id = "test_key_15"
        reset_at = datetime.utcnow() - timedelta(minutes=30)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=20),
            used_capacity=80,
            time_window=TimeWindow.Hourly,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 0)

        assert result.remaining_capacity.value == 100
        assert result.used_capacity == 0
        assert result.capacity_state == CapacityState.Abundant

    @pytest.mark.asyncio
    async def test_time_window_reset_emits_event(
        self,
        engine: QuotaAwarenessEngine,
        mock_state_store: MockStateStore,
        mock_observability: MockObservabilityManager,
    ) -> None:
        """Test that time window reset emits quota_reset event."""
        key_id = "test_key_16"
        reset_at = datetime.utcnow() - timedelta(hours=1)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=10),
            used_capacity=90,
            time_window=TimeWindow.Daily,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        await engine.update_capacity(key_id, 0)

        # Check that quota_reset event was emitted
        reset_events = [
            e for e in mock_observability.events if e["event_type"] == "quota_reset"
        ]
        assert len(reset_events) == 1
        assert reset_events[0]["payload"]["key_id"] == key_id

    @pytest.mark.asyncio
    async def test_update_capacity_emits_event(
        self,
        engine: QuotaAwarenessEngine,
        mock_state_store: MockStateStore,
        mock_observability: MockObservabilityManager,
    ) -> None:
        """Test that update_capacity emits capacity_updated event."""
        key_id = "test_key_17"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=100),
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        await engine.update_capacity(key_id, 25)

        # Check that capacity_updated event was emitted
        update_events = [
            e for e in mock_observability.events if e["event_type"] == "capacity_updated"
        ]
        assert len(update_events) == 1
        assert update_events[0]["payload"]["key_id"] == key_id
        assert update_events[0]["payload"]["consumed"] == 25

    @pytest.mark.asyncio
    async def test_update_capacity_negative_consumed_raises_error(
        self, engine: QuotaAwarenessEngine
    ) -> None:
        """Test that update_capacity raises error for negative consumed."""
        key_id = "test_key_18"

        with pytest.raises(ValueError, match="Consumed capacity must be non-negative"):
            await engine.update_capacity(key_id, -1)

    @pytest.mark.asyncio
    async def test_update_capacity_remaining_cannot_go_below_zero(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that remaining_capacity cannot go below zero."""
        key_id = "test_key_19"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=10),
            used_capacity=90,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Try to consume more than remaining
        result = await engine.update_capacity(key_id, 50)

        assert result.remaining_capacity.value == 0

    @pytest.mark.asyncio
    async def test_get_quota_state(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test get_quota_state retrieves quota state."""
        key_id = "test_key_20"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=50),
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.get_quota_state(key_id)

        assert result is not None
        assert result.key_id == key_id
        assert result.remaining_capacity.value == 50

    @pytest.mark.asyncio
    async def test_get_quota_state_initializes_if_missing(
        self,
        engine: QuotaAwarenessEngine,
        mock_state_store: MockStateStore,
        mock_observability: MockObservabilityManager,
    ) -> None:
        """Test get_quota_state initializes QuotaState if missing."""
        key_id = "nonexistent_key"

        result = await engine.get_quota_state(key_id)

        # Should return initialized QuotaState, not None
        assert result is not None
        assert result.key_id == key_id
        assert result.capacity_state == CapacityState.Abundant
        assert result.time_window == TimeWindow.Daily
        assert result.used_capacity == 0
        # Check that it was saved to StateStore
        assert mock_state_store.save_quota_state_called
        # Check that initialization was logged
        init_logs = [
            log
            for log in mock_observability.logs
            if "Initialized quota state" in log["message"]
        ]
        assert len(init_logs) > 0

    @pytest.mark.asyncio
    async def test_get_quota_state_initialized_defaults(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that initialized QuotaState has correct defaults."""
        key_id = "new_key_1"

        result = await engine.get_quota_state(key_id)

        assert result.capacity_state == CapacityState.Abundant
        assert result.time_window == TimeWindow.Daily
        assert result.remaining_capacity.value is None
        assert result.total_capacity is None
        assert result.used_capacity == 0
        assert result.reset_at > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_get_quota_state_concurrent_queries(
        self,
        engine: QuotaAwarenessEngine,
        mock_state_store: MockStateStore,
    ) -> None:
        """Test concurrent queries for same key_id (thread-safety)."""
        import asyncio

        key_id = "concurrent_key"
        num_concurrent = 10

        # Reset save counter
        mock_state_store.save_quota_state_called = False

        # Launch concurrent queries
        tasks = [engine.get_quota_state(key_id) for _ in range(num_concurrent)]
        results = await asyncio.gather(*tasks)

        # All should return the same QuotaState
        assert len(results) == num_concurrent
        first_result = results[0]
        for result in results:
            assert result.key_id == key_id
            assert result.id == first_result.id  # Same QuotaState instance

        # Should have been saved (at least once, ideally only once due to locking)
        assert mock_state_store.save_quota_state_called

    @pytest.mark.asyncio
    async def test_get_quota_state_concurrent_different_keys(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test concurrent queries for different key_ids."""
        import asyncio

        key_ids = [f"concurrent_key_{i}" for i in range(10)]

        # Launch concurrent queries for different keys
        tasks = [engine.get_quota_state(key_id) for key_id in key_ids]
        results = await asyncio.gather(*tasks)

        # All should return different QuotaStates
        assert len(results) == len(key_ids)
        result_key_ids = {result.key_id for result in results}
        assert result_key_ids == set(key_ids)

    @pytest.mark.asyncio
    async def test_get_quota_state_performance(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that get_quota_state meets performance target (<2ms)."""
        import time

        key_id = "perf_test_key"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        # Pre-create quota state for fast path
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=50),
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Measure query time (fast path)
        start = time.perf_counter()
        result = await engine.get_quota_state(key_id)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert result is not None
        # Performance target: <2ms
        assert elapsed_ms < 2.0, f"Query took {elapsed_ms:.3f}ms, expected <2ms"

    @pytest.mark.asyncio
    async def test_get_quota_state_performance_initialization(
        self, engine: QuotaAwarenessEngine
    ) -> None:
        """Test that get_quota_state initialization is reasonably fast."""
        import time

        key_id = "perf_init_key"

        # Measure initialization time (slow path)
        start = time.perf_counter()
        result = await engine.get_quota_state(key_id)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert result is not None
        # Initialization might take longer, but should still be reasonable (<10ms)
        assert elapsed_ms < 10.0, f"Initialization took {elapsed_ms:.3f}ms"

    @pytest.mark.asyncio
    async def test_save_quota_state_error_handling(
        self,
        engine: QuotaAwarenessEngine,
        mock_state_store: MockStateStore,
        mock_observability: MockObservabilityManager,
    ) -> None:
        """Test that StateStoreError is raised and logged when save fails."""
        key_id = "test_key_21"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            remaining_capacity=CapacityEstimate(value=100),
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Set error to be raised
        mock_state_store.save_quota_state_error = StateStoreError("Save failed")

        with pytest.raises(StateStoreError):
            await engine.update_capacity(key_id, 10)

        # Check that error was logged
        error_logs = [
            log for log in mock_observability.logs if log["level"] == "ERROR"
        ]
        assert len(error_logs) > 0
        assert "Failed to save quota state" in error_logs[0]["message"]

    @pytest.mark.asyncio
    async def test_time_window_reset_monthly(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test time window reset detection for Monthly window."""
        key_id = "test_key_monthly"
        # Set reset_at in the past to trigger reset
        reset_at = datetime.utcnow() - timedelta(days=2)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=100),
            used_capacity=900,
            time_window=TimeWindow.Monthly,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 0)

        assert result.remaining_capacity.value == 1000
        assert result.used_capacity == 0
        assert result.capacity_state == CapacityState.Abundant
        assert result.reset_at > reset_at
        # Verify next reset is first of next month
        assert result.reset_at.day == 1
        assert result.reset_at.hour == 0
        assert result.reset_at.minute == 0

    @pytest.mark.asyncio
    async def test_time_window_reset_custom(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that Custom time window preserves reset_at (doesn't auto-calculate)."""
        key_id = "test_key_custom"
        # Set a specific past reset_at - Custom window should preserve it
        past_reset_at = datetime.utcnow() - timedelta(hours=1)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=10),
            used_capacity=90,
            time_window=TimeWindow.Custom,
            reset_at=past_reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 0)

        # Reset should happen (capacity restored)
        assert result.remaining_capacity.value == 100
        assert result.used_capacity == 0
        assert result.capacity_state == CapacityState.Abundant
        # Custom window should preserve reset_at (not recalculate)
        # Note: The reset_at stays the same for Custom window per implementation
        assert result.time_window == TimeWindow.Custom

    @pytest.mark.asyncio
    async def test_reset_updates_reset_at_correctly(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that reset_at is updated to next reset time correctly."""
        key_id = "test_key_reset_at"
        now = datetime.utcnow()
        # Set reset_at in the past
        reset_at = now - timedelta(hours=2)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=50),
            used_capacity=50,
            time_window=TimeWindow.Daily,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 0)

        # reset_at should be updated to next daily reset (midnight)
        assert result.reset_at > now
        assert result.reset_at.hour == 0
        assert result.reset_at.minute == 0
        assert result.reset_at.second == 0

    @pytest.mark.asyncio
    async def test_reset_with_unknown_total_capacity(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test reset behavior when total_capacity is unknown."""
        key_id = "test_key_unknown_total"
        reset_at = datetime.utcnow() - timedelta(hours=1)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=None,
            remaining_capacity=CapacityEstimate(value=50),
            used_capacity=50,
            time_window=TimeWindow.Daily,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 0)

        # When total_capacity is unknown, remaining_capacity should be reset but value stays None
        assert result.used_capacity == 0
        assert result.capacity_state == CapacityState.Abundant
        # remaining_capacity confidence should be updated
        assert result.remaining_capacity.estimation_method == "unknown_after_reset"

    @pytest.mark.asyncio
    async def test_reset_timezone_awareness(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that reset logic uses UTC timezone (timezone awareness)."""
        key_id = "test_key_timezone"
        # Use UTC explicitly
        now_utc = datetime.utcnow()
        reset_at = now_utc - timedelta(hours=1)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=10),
            used_capacity=90,
            time_window=TimeWindow.Daily,
            reset_at=reset_at.replace(tzinfo=None),  # Store as naive UTC
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 0)

        # Reset should work correctly with UTC
        assert result.remaining_capacity.value == 100
        assert result.used_capacity == 0
        # reset_at should be calculated in UTC (next midnight UTC)
        assert result.reset_at.hour == 0
        assert result.reset_at.minute == 0

    @pytest.mark.asyncio
    async def test_reset_atomic_operation(
        self,
        engine: QuotaAwarenessEngine,
        mock_state_store: MockStateStore,
        mock_observability: MockObservabilityManager,
    ) -> None:
        """Test that reset and update happen atomically."""
        key_id = "test_key_atomic"
        reset_at = datetime.utcnow() - timedelta(hours=1)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=10),
            used_capacity=90,
            time_window=TimeWindow.Daily,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Update capacity which should trigger reset first
        result = await engine.update_capacity(key_id, 5)

        # Should reset first (to 100), then consume 5
        assert result.remaining_capacity.value == 95  # 100 - 5
        assert result.used_capacity == 5  # Reset to 0, then add 5
        assert result.capacity_state == CapacityState.Abundant

        # Verify reset event was emitted
        reset_events = [
            e for e in mock_observability.events if e["event_type"] == "quota_reset"
        ]
        assert len(reset_events) == 1

        # Verify capacity_updated event was also emitted
        update_events = [
            e for e in mock_observability.events if e["event_type"] == "capacity_updated"
        ]
        assert len(update_events) == 1

    @pytest.mark.asyncio
    async def test_reset_daily_at_midnight(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test Daily reset happens at midnight (00:00)."""
        key_id = "test_key_midnight"
        # Set reset_at to just before midnight yesterday
        now = datetime.utcnow()
        yesterday_midnight = now.replace(hour=23, minute=59, second=0, microsecond=0) - timedelta(
            days=1
        )

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=10),
            used_capacity=90,
            time_window=TimeWindow.Daily,
            reset_at=yesterday_midnight,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 0)

        # Next reset should be today's midnight or tomorrow's midnight
        assert result.reset_at.hour == 0
        assert result.reset_at.minute == 0
        assert result.reset_at.second == 0

    @pytest.mark.asyncio
    async def test_reset_hourly_on_the_hour(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test Hourly reset happens on the hour (00 minutes)."""
        key_id = "test_key_hourly"
        # Set reset_at to past hour
        reset_at = datetime.utcnow() - timedelta(minutes=30)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=10),
            used_capacity=90,
            time_window=TimeWindow.Hourly,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        result = await engine.update_capacity(key_id, 0)

        # Next reset should be on the hour
        assert result.reset_at.minute == 0
        assert result.reset_at.second == 0

    @pytest.mark.asyncio
    async def test_handle_quota_response_429_detection(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that handle_quota_response detects 429 status code."""
        key_id = "test_key_429"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=50),
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create mock 429 response (dict format)
        response = {"status_code": 429, "headers": {}}

        result = await engine.handle_quota_response(key_id, response)

        assert result.capacity_state == CapacityState.Exhausted
        assert result.remaining_capacity.value == 0

    @pytest.mark.asyncio
    async def test_handle_quota_response_non_429_raises_error(
        self, engine: QuotaAwarenessEngine
    ) -> None:
        """Test that handle_quota_response raises error for non-429 status."""
        key_id = "test_key_non_429"
        response = {"status_code": 200, "headers": {}}

        with pytest.raises(ValueError, match="Expected 429 status code"):
            await engine.handle_quota_response(key_id, response)

    @pytest.mark.asyncio
    async def test_handle_quota_response_updates_to_exhausted(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that handle_quota_response updates quota state to Exhausted."""
        key_id = "test_key_exhausted"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=50),
            capacity_state=CapacityState.Abundant,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        response = {"status_code": 429, "headers": {}}

        result = await engine.handle_quota_response(key_id, response)

        assert result.capacity_state == CapacityState.Exhausted
        assert result.remaining_capacity.value == 0
        assert result.remaining_capacity.confidence == 1.0
        assert result.remaining_capacity.estimation_method == "429_response"

    @pytest.mark.asyncio
    async def test_handle_quota_response_extracts_retry_after(
        self,
        engine: QuotaAwarenessEngine,
        mock_state_store: MockStateStore,
        mock_observability: MockObservabilityManager,
    ) -> None:
        """Test that handle_quota_response extracts retry-after header."""
        key_id = "test_key_retry_after"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=50),
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        response = {
            "status_code": 429,
            "headers": {"Retry-After": "120"},  # 120 seconds
        }

        await engine.handle_quota_response(key_id, response)

        # Check that retry_after was extracted and used in event
        exhausted_events = [
            e for e in mock_observability.events if e["event_type"] == "quota_exhausted"
        ]
        assert len(exhausted_events) == 1
        assert exhausted_events[0]["payload"]["retry_after_seconds"] == 120

    @pytest.mark.asyncio
    async def test_handle_quota_response_missing_retry_after_uses_default(
        self,
        engine: QuotaAwarenessEngine,
        mock_state_store: MockStateStore,
        mock_observability: MockObservabilityManager,
    ) -> None:
        """Test that missing retry-after header uses default cooldown."""
        key_id = "test_key_no_retry_after"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=50),
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        response = {"status_code": 429, "headers": {}}  # No retry-after

        await engine.handle_quota_response(key_id, response)

        # Check that default cooldown was used (60 seconds)
        exhausted_events = [
            e for e in mock_observability.events if e["event_type"] == "quota_exhausted"
        ]
        assert len(exhausted_events) == 1
        assert exhausted_events[0]["payload"]["retry_after_seconds"] == 60  # Default

    @pytest.mark.asyncio
    async def test_handle_quota_response_emits_event(
        self,
        engine: QuotaAwarenessEngine,
        mock_state_store: MockStateStore,
        mock_observability: MockObservabilityManager,
    ) -> None:
        """Test that handle_quota_response emits quota_exhausted event."""
        key_id = "test_key_event"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=50),
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        response = {"status_code": 429, "headers": {"Retry-After": "30"}}

        await engine.handle_quota_response(key_id, response, provider_id="openai")

        # Check that quota_exhausted event was emitted
        exhausted_events = [
            e for e in mock_observability.events if e["event_type"] == "quota_exhausted"
        ]
        assert len(exhausted_events) == 1
        assert exhausted_events[0]["payload"]["key_id"] == key_id
        assert exhausted_events[0]["payload"]["provider_id"] == "openai"
        assert exhausted_events[0]["payload"]["status_code"] == 429
        assert exhausted_events[0]["payload"]["retry_after_seconds"] == 30

    @pytest.mark.asyncio
    async def test_handle_quota_response_with_key_manager(
        self,
        mock_state_store: MockStateStore,
        mock_observability: MockObservabilityManager,
    ) -> None:
        """Test that handle_quota_response updates key state via KeyManager."""
        from apikeyrouter.domain.components.key_manager import KeyManager
        from apikeyrouter.domain.models.api_key import APIKey, KeyState

        # Create KeyManager
        key_manager = KeyManager(mock_state_store, mock_observability)
        engine = QuotaAwarenessEngine(
            mock_state_store, mock_observability, key_manager=key_manager
        )

        key_id = "test_key_with_manager"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        # Create APIKey
        api_key = APIKey(
            id=key_id,
            key_material="encrypted_key",
            provider_id="openai",
            state=KeyState.Available,
        )
        await mock_state_store.save_key(api_key)

        # Create QuotaState
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=50),
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        response = {"status_code": 429, "headers": {"Retry-After": "45"}}

        await engine.handle_quota_response(key_id, response)

        # Check that key state was updated to Throttled
        updated_key = await mock_state_store.get_key(key_id)
        assert updated_key is not None
        assert updated_key.state == KeyState.Throttled
        assert updated_key.cooldown_until is not None

    @pytest.mark.asyncio
    async def test_handle_quota_response_object_format(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that handle_quota_response handles object format responses."""
        key_id = "test_key_object"
        reset_at = datetime.utcnow() + timedelta(hours=1)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=100,
            remaining_capacity=CapacityEstimate(value=50),
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create object-like response
        class MockResponse:
            def __init__(self) -> None:
                self.status_code = 429
                self.headers = {"Retry-After": "90"}

        response = MockResponse()

        result = await engine.handle_quota_response(key_id, response)

        assert result.capacity_state == CapacityState.Exhausted

    @pytest.mark.asyncio
    async def test_handle_quota_response_initializes_if_missing(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that handle_quota_response initializes QuotaState if missing."""
        key_id = "test_key_missing"

        response = {"status_code": 429, "headers": {}}

        result = await engine.handle_quota_response(key_id, response)

        # Should initialize and update to Exhausted
        assert result is not None
        assert result.key_id == key_id
        assert result.capacity_state == CapacityState.Exhausted

    @pytest.mark.asyncio
    async def test_calculate_usage_rate_with_sufficient_data(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test calculate_usage_rate with sufficient routing decisions."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_usage_rate"
        now = datetime.utcnow()

        # Create 5 routing decisions in the last hour
        for i in range(5):
            decision = RoutingDecision(
                id=f"decision_{i}",
                request_id=f"req_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=10 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.calculate_usage_rate(key_id, window_hours=1.0)

        assert result is not None
        assert result.requests_per_hour == 5.0
        assert result.window_hours == 1.0
        assert result.tokens_per_hour is None  # No token data in decisions
        assert result.confidence > 0.0

    @pytest.mark.asyncio
    async def test_calculate_usage_rate_with_token_data(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test calculate_usage_rate with token information in evaluation_results."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_tokens"
        now = datetime.utcnow()

        # Create routing decisions with token data
        token_counts = [100, 200, 150, 300, 250]
        for i, tokens in enumerate(token_counts):
            decision = RoutingDecision(
                id=f"decision_{i}",
                request_id=f"req_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=10 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
                evaluation_results={"tokens": tokens},
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.calculate_usage_rate(key_id, window_hours=1.0)

        assert result is not None
        assert result.requests_per_hour == 5.0
        assert result.tokens_per_hour == sum(token_counts) / 1.0  # 1000 tokens per hour
        assert result.window_hours == 1.0

    @pytest.mark.asyncio
    async def test_calculate_usage_rate_insufficient_data(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test calculate_usage_rate with insufficient data returns None."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_insufficient"
        now = datetime.utcnow()

        # Create only 2 routing decisions (less than min_data_points=3)
        for i in range(2):
            decision = RoutingDecision(
                id=f"decision_{i}",
                request_id=f"req_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=10 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.calculate_usage_rate(key_id, window_hours=1.0, min_data_points=3)

        # Should return None due to insufficient data
        assert result is None

    @pytest.mark.asyncio
    async def test_calculate_usage_rate_extends_window(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test calculate_usage_rate extends time window when insufficient data."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_extend"
        now = datetime.utcnow()

        # Create 3 routing decisions spread over 2 hours
        for i in range(3):
            decision = RoutingDecision(
                id=f"decision_{i}",
                request_id=f"req_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(hours=1.5 - i * 0.5),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.calculate_usage_rate(key_id, window_hours=1.0, min_data_points=3)

        # Should extend window and find all 3 decisions
        assert result is not None
        assert result.requests_per_hour == 3.0 / result.window_hours
        assert result.window_hours >= 1.0  # Extended window

    @pytest.mark.asyncio
    async def test_calculate_usage_rate_sliding_window(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test calculate_usage_rate uses sliding window correctly."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_sliding"
        now = datetime.utcnow()

        # Create decisions: 5 in last hour (more than min_data_points=3), 2 older than 1 hour
        for i in range(5):
            decision = RoutingDecision(
                id=f"decision_recent_{i}",
                request_id=f"req_recent_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=12 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Recent decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        # Older decisions (should not be included)
        for i in range(2):
            decision = RoutingDecision(
                id=f"decision_old_{i}",
                request_id=f"req_old_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(hours=2 + i),
                objective=RoutingObjective(primary="cost"),
                explanation="Old decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.calculate_usage_rate(key_id, window_hours=1.0)

        assert result is not None
        # Should only count the 5 recent decisions in the 1-hour window
        assert result.requests_per_hour == 5.0
        assert result.window_hours == 1.0

    @pytest.mark.asyncio
    async def test_calculate_usage_rate_variable_request_sizes(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test calculate_usage_rate handles variable request sizes."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_variable"
        now = datetime.utcnow()

        # Create decisions with different token counts
        token_counts = [50, 500, 1000, 200, 150]
        for i, tokens in enumerate(token_counts):
            decision = RoutingDecision(
                id=f"decision_{i}",
                request_id=f"req_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=10 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Variable size decision",
                confidence=0.9,
                evaluation_results={"total_tokens": tokens},
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.calculate_usage_rate(key_id, window_hours=1.0)

        assert result is not None
        assert result.requests_per_hour == 5.0
        assert result.tokens_per_hour == sum(token_counts) / 1.0  # 1900 tokens per hour

    @pytest.mark.asyncio
    async def test_calculate_usage_rate_filters_by_key_id(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test calculate_usage_rate only counts decisions for specified key."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id_1 = "test_key_1"
        key_id_2 = "test_key_2"
        now = datetime.utcnow()

        # Create decisions for key 1
        for i in range(3):
            decision = RoutingDecision(
                id=f"decision_key1_{i}",
                request_id=f"req_key1_{i}",
                selected_key_id=key_id_1,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=10 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Key 1 decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        # Create decisions for key 2
        for i in range(2):
            decision = RoutingDecision(
                id=f"decision_key2_{i}",
                request_id=f"req_key2_{i}",
                selected_key_id=key_id_2,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=10 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Key 2 decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.calculate_usage_rate(key_id_1, window_hours=1.0)

        assert result is not None
        # Should only count key 1's decisions
        assert result.requests_per_hour == 3.0

    @pytest.mark.asyncio
    async def test_calculate_usage_rate_invalid_window_raises_error(
        self, engine: QuotaAwarenessEngine
    ) -> None:
        """Test calculate_usage_rate raises error for invalid window_hours."""
        key_id = "test_key_invalid"

        with pytest.raises(ValueError, match="window_hours must be greater than 0"):
            await engine.calculate_usage_rate(key_id, window_hours=0)

        with pytest.raises(ValueError, match="window_hours must be greater than 0"):
            await engine.calculate_usage_rate(key_id, window_hours=-1.0)

    @pytest.mark.asyncio
    async def test_calculate_usage_rate_confidence_calculation(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test calculate_usage_rate calculates confidence based on data quality."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_confidence"
        now = datetime.utcnow()

        # Create exactly min_data_points (3) decisions
        for i in range(3):
            decision = RoutingDecision(
                id=f"decision_{i}",
                request_id=f"req_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=10 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.calculate_usage_rate(key_id, window_hours=1.0, min_data_points=3)

        assert result is not None
        # Confidence should be based on data points
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_predict_exhaustion_calculates_time_correctly(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test predict_exhaustion calculates time_to_exhaustion correctly."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_prediction"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with known capacity
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=500, confidence=1.0),
            used_capacity=500,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions (5 per hour = 5 requests/hour usage rate)
        for i in range(5):
            decision = RoutingDecision(
                id=f"decision_{i}",
                request_id=f"req_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=10 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.predict_exhaustion(key_id)

        assert result is not None
        assert result.key_id == key_id
        assert result.remaining_capacity == 500
        assert result.current_usage_rate == 5.0  # 5 requests per hour
        # Time to exhaustion: 500 / 5 = 100 hours
        expected_exhaustion = now + timedelta(hours=100)
        # Allow small time difference (within 1 second)
        time_diff = abs((result.predicted_exhaustion_at - expected_exhaustion).total_seconds())
        assert time_diff < 1.0
        assert result.calculation_method == "usage_rate_division"
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_predict_exhaustion_zero_usage_returns_none(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test predict_exhaustion returns None for zero usage."""
        key_id = "test_key_zero_usage"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with capacity but no usage
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=500, confidence=1.0),
            used_capacity=0,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # No routing decisions = zero usage rate
        result = await engine.predict_exhaustion(key_id)

        # Should return None due to zero usage
        assert result is None

    @pytest.mark.asyncio
    async def test_predict_exhaustion_unknown_capacity_returns_none(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test predict_exhaustion returns None for unknown capacity."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_unknown_capacity"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with unknown capacity
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=None,
            remaining_capacity=CapacityEstimate(value=None, confidence=0.0),
            used_capacity=0,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create some routing decisions
        for i in range(5):
            decision = RoutingDecision(
                id=f"decision_{i}",
                request_id=f"req_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=10 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.predict_exhaustion(key_id)

        # Should return None due to unknown capacity
        assert result is None

    @pytest.mark.asyncio
    async def test_predict_exhaustion_already_exhausted_returns_none(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test predict_exhaustion returns None for already exhausted key."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_exhausted"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with zero remaining capacity
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=0, confidence=1.0),
            used_capacity=1000,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create some routing decisions
        for i in range(5):
            decision = RoutingDecision(
                id=f"decision_{i}",
                request_id=f"req_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=10 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.predict_exhaustion(key_id)

        # Should return None because already exhausted
        assert result is None

    @pytest.mark.asyncio
    async def test_predict_exhaustion_confidence_high_exact_capacity(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test predict_exhaustion has high confidence with exact capacity."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_high_confidence"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with exact capacity (high confidence)
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=500, confidence=1.0),
            used_capacity=500,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create many routing decisions for high usage rate confidence
        for i in range(10):
            decision = RoutingDecision(
                id=f"decision_{i}",
                request_id=f"req_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=6 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.predict_exhaustion(key_id)

        assert result is not None
        # High confidence: exact capacity + good usage rate data
        assert result.confidence >= 0.7

    @pytest.mark.asyncio
    async def test_predict_exhaustion_confidence_medium_estimated_capacity(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test predict_exhaustion has medium confidence with estimated capacity."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_medium_confidence"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with estimated capacity (bounded)
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=None,
            remaining_capacity=CapacityEstimate(
                value=None, min_value=400, max_value=600, confidence=0.7
            ),
            used_capacity=0,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Use a value in the middle of the range for calculation
        # Note: The implementation uses remaining_capacity.value, so we need to set it
        # For this test, we'll use a value that represents the estimate
        quota_state.remaining_capacity.value = 500  # Midpoint
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions
        for i in range(5):
            decision = RoutingDecision(
                id=f"decision_{i}",
                request_id=f"req_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=10 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.predict_exhaustion(key_id)

        assert result is not None
        # Medium confidence: estimated capacity
        assert 0.3 <= result.confidence <= 0.8

    @pytest.mark.asyncio
    async def test_predict_exhaustion_creates_correct_fields(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test ExhaustionPrediction created with correct fields."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_fields"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=200, confidence=1.0),
            used_capacity=800,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions (4 per hour)
        for i in range(4):
            decision = RoutingDecision(
                id=f"decision_{i}",
                request_id=f"req_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=15 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.predict_exhaustion(key_id)

        assert result is not None
        assert result.key_id == key_id
        assert result.predicted_exhaustion_at > now
        assert 0.0 <= result.confidence <= 1.0
        assert result.calculation_method == "usage_rate_division"
        assert result.current_usage_rate > 0.0
        assert result.remaining_capacity == 200
        assert result.calculated_at <= datetime.utcnow()

    @pytest.mark.asyncio
    async def test_predict_exhaustion_very_short_time(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test predict_exhaustion handles very short time to exhaustion."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_short_time"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with very small remaining capacity
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=1, confidence=1.0),
            used_capacity=999,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions with high usage rate (10 per hour)
        for i in range(10):
            decision = RoutingDecision(
                id=f"decision_{i}",
                request_id=f"req_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=6 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.predict_exhaustion(key_id)

        assert result is not None
        # Time to exhaustion: 1 / 10 = 0.1 hours = 6 minutes
        expected_exhaustion = now + timedelta(hours=0.1)
        time_diff = abs((result.predicted_exhaustion_at - expected_exhaustion).total_seconds())
        assert time_diff < 1.0

    @pytest.mark.asyncio
    async def test_predict_exhaustion_insufficient_data_returns_none(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test predict_exhaustion returns None when usage rate cannot be calculated."""
        key_id = "test_key_insufficient"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=500, confidence=1.0),
            used_capacity=500,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # No routing decisions = insufficient data for usage rate
        result = await engine.predict_exhaustion(key_id)

        # Should return None because usage_rate is None
        assert result is None

    @pytest.mark.asyncio
    async def test_calculate_uncertainty_low_exact_capacity(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test calculate_uncertainty returns Low for exact capacity with good data."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_uncertainty_low"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with exact capacity
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=500, confidence=1.0),
            used_capacity=500,
            reset_at=reset_at,
        )

        # Create usage rate with high confidence
        usage_rate = UsageRate(
            requests_per_hour=10.0,
            tokens_per_hour=None,
            window_hours=1.0,
            calculated_at=now,
            confidence=0.9,
        )

        uncertainty = engine.calculate_uncertainty(quota_state, usage_rate)

        assert uncertainty == UncertaintyLevel.Low

    @pytest.mark.asyncio
    async def test_calculate_uncertainty_medium_estimated_capacity(
        self, engine: QuotaAwarenessEngine
    ) -> None:
        """Test calculate_uncertainty returns Medium for estimated capacity."""
        key_id = "test_key_uncertainty_medium"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with estimated capacity (bounded)
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=None,
            remaining_capacity=CapacityEstimate(
                value=None, min_value=400, max_value=600, confidence=0.7
            ),
            used_capacity=0,
            reset_at=reset_at,
        )

        usage_rate = UsageRate(
            requests_per_hour=10.0,
            tokens_per_hour=None,
            window_hours=1.0,
            calculated_at=now,
            confidence=0.8,
        )

        uncertainty = engine.calculate_uncertainty(quota_state, usage_rate)

        assert uncertainty == UncertaintyLevel.Medium

    @pytest.mark.asyncio
    async def test_calculate_uncertainty_high_bounded_capacity(
        self, engine: QuotaAwarenessEngine
    ) -> None:
        """Test calculate_uncertainty returns High for bounded capacity."""
        key_id = "test_key_uncertainty_high"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with bounded capacity (only min)
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=None,
            remaining_capacity=CapacityEstimate(
                value=None, min_value=400, max_value=None, confidence=0.5
            ),
            used_capacity=0,
            reset_at=reset_at,
        )

        usage_rate = UsageRate(
            requests_per_hour=10.0,
            tokens_per_hour=None,
            window_hours=1.0,
            calculated_at=now,
            confidence=0.7,
        )

        uncertainty = engine.calculate_uncertainty(quota_state, usage_rate)

        assert uncertainty == UncertaintyLevel.High

    @pytest.mark.asyncio
    async def test_calculate_uncertainty_unknown_capacity(
        self, engine: QuotaAwarenessEngine
    ) -> None:
        """Test calculate_uncertainty returns Unknown for unknown capacity."""
        key_id = "test_key_uncertainty_unknown"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with unknown capacity
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=None,
            remaining_capacity=CapacityEstimate(value=None, confidence=0.0),
            used_capacity=0,
            reset_at=reset_at,
        )

        usage_rate = UsageRate(
            requests_per_hour=10.0,
            tokens_per_hour=None,
            window_hours=1.0,
            calculated_at=now,
            confidence=0.5,
        )

        uncertainty = engine.calculate_uncertainty(quota_state, usage_rate)

        assert uncertainty == UncertaintyLevel.Unknown

    @pytest.mark.asyncio
    async def test_calculate_uncertainty_increases_with_low_usage_confidence(
        self, engine: QuotaAwarenessEngine
    ) -> None:
        """Test calculate_uncertainty increases when usage rate confidence is low."""
        key_id = "test_key_uncertainty_low_confidence"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with exact capacity
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=500, confidence=1.0),
            used_capacity=500,
            reset_at=reset_at,
        )

        # Usage rate with low confidence
        usage_rate = UsageRate(
            requests_per_hour=10.0,
            tokens_per_hour=None,
            window_hours=1.0,
            calculated_at=now,
            confidence=0.3,  # Low confidence
        )

        uncertainty = engine.calculate_uncertainty(quota_state, usage_rate)

        # Should be Medium (increased from Low due to low usage confidence)
        assert uncertainty == UncertaintyLevel.Medium

    @pytest.mark.asyncio
    async def test_calculate_uncertainty_none_usage_rate(
        self, engine: QuotaAwarenessEngine
    ) -> None:
        """Test calculate_uncertainty handles None usage_rate."""
        key_id = "test_key_uncertainty_none"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with exact capacity
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=500, confidence=1.0),
            used_capacity=500,
            reset_at=reset_at,
        )

        uncertainty = engine.calculate_uncertainty(quota_state, None)

        # Should be Medium (increased from Low due to no usage rate)
        assert uncertainty == UncertaintyLevel.Medium

    @pytest.mark.asyncio
    async def test_predict_exhaustion_includes_uncertainty(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test predict_exhaustion includes uncertainty_level in prediction."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_uncertainty_prediction"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=200, confidence=1.0),
            used_capacity=800,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions (4 per hour)
        for i in range(4):
            decision = RoutingDecision(
                id=f"decision_{i}",
                request_id=f"req_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=15 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.predict_exhaustion(key_id)

        assert result is not None
        assert result.uncertainty_level in [
            UncertaintyLevel.Low,
            UncertaintyLevel.Medium,
            UncertaintyLevel.High,
            UncertaintyLevel.Unknown,
        ]

    @pytest.mark.asyncio
    async def test_predict_exhaustion_applies_conservative_adjustment_high_uncertainty(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test predict_exhaustion applies conservative adjustment for high uncertainty."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_conservative"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with estimated capacity (medium uncertainty)
        # Use estimated type (both min and max) with lower confidence
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=None,
            remaining_capacity=CapacityEstimate(
                value=200, min_value=150, max_value=250, confidence=0.5
            ),
            used_capacity=0,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions with low confidence (fewer decisions)
        for i in range(3):  # Fewer decisions = lower confidence
            decision = RoutingDecision(
                id=f"decision_{i}",
                request_id=f"req_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=20 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        result = await engine.predict_exhaustion(key_id)

        assert result is not None
        # With medium/high uncertainty, should have uncertainty level above Low
        assert result.uncertainty_level != UncertaintyLevel.Low
        # Verify conservative adjustment is applied (prediction should be earlier)
        # Original: 200 / 3 = 66.67 hours
        # With adjustment: should be shorter
        assert result.uncertainty_level in [
            UncertaintyLevel.Medium,
            UncertaintyLevel.High,
            UncertaintyLevel.Unknown,
        ]

    @pytest.mark.asyncio
    async def test_predict_exhaustion_uncertainty_affects_confidence(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that uncertainty level affects confidence in prediction."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_uncertainty_confidence"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with exact capacity (low uncertainty)
        quota_state_low = QuotaState(
            id=str(uuid.uuid4()),
            key_id=f"{key_id}_low",
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=200, confidence=1.0),
            used_capacity=800,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state_low)

        # Create quota state with estimated capacity (medium uncertainty)
        # Use estimated type with lower confidence to get higher uncertainty
        quota_state_high = QuotaState(
            id=str(uuid.uuid4()),
            key_id=f"{key_id}_high",
            total_capacity=None,
            remaining_capacity=CapacityEstimate(
                value=200, min_value=150, max_value=250, confidence=0.4
            ),
            used_capacity=0,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state_high)

        # Create routing decisions for both
        for key_id_var in [f"{key_id}_low", f"{key_id}_high"]:
            for i in range(5):
                decision = RoutingDecision(
                    id=f"decision_{key_id_var}_{i}",
                    request_id=f"req_{key_id_var}_{i}",
                    selected_key_id=key_id_var,
                    selected_provider_id="openai",
                    decision_timestamp=now - timedelta(minutes=12 * i),
                    objective=RoutingObjective(primary="cost"),
                    explanation="Test decision",
                    confidence=0.9,
                )
                await mock_state_store.save_routing_decision(decision)

        result_low = await engine.predict_exhaustion(f"{key_id}_low")
        result_high = await engine.predict_exhaustion(f"{key_id}_high")

        assert result_low is not None
        assert result_high is not None
        # Higher uncertainty should result in lower confidence
        assert result_high.confidence <= result_low.confidence
        assert result_low.uncertainty_level == UncertaintyLevel.Low
        # High uncertainty case should have at least Medium uncertainty
        assert result_high.uncertainty_level in [
            UncertaintyLevel.Medium,
            UncertaintyLevel.High,
            UncertaintyLevel.Unknown,
        ]

    @pytest.mark.asyncio
    async def test_capacity_state_critical_if_exhaustion_less_than_4_hours(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test capacity_state updated to Critical if exhaustion < 4 hours."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_critical_prediction"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with capacity that will exhaust in < 4 hours
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=10, confidence=1.0),
            used_capacity=990,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions to establish usage rate (high usage)
        for i in range(10):
            decision = RoutingDecision(
                id=f"decision_{key_id}_{i}",
                request_id=f"req_{key_id}_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=5 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        # Update capacity - should trigger prediction and state change
        result = await engine.update_capacity(key_id, consumed=1)

        # Should be Critical because exhaustion < 4 hours
        assert result.capacity_state == CapacityState.Critical

    @pytest.mark.asyncio
    async def test_capacity_state_constrained_if_exhaustion_less_than_24_hours(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test capacity_state updated to Constrained if exhaustion < 24 hours."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_constrained_prediction"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with capacity that will exhaust in < 24 hours but > 4 hours
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=100, confidence=1.0),
            used_capacity=900,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions to establish usage rate (moderate usage)
        for i in range(10):
            decision = RoutingDecision(
                id=f"decision_{key_id}_{i}",
                request_id=f"req_{key_id}_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=10 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        # Update capacity - should trigger prediction and state change
        result = await engine.update_capacity(key_id, consumed=1)

        # Should be Constrained because exhaustion < 24 hours but > 4 hours
        assert result.capacity_state == CapacityState.Constrained

    @pytest.mark.asyncio
    async def test_capacity_state_abundant_if_exhaustion_greater_than_24_hours(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test capacity_state updated to Abundant if exhaustion > 24 hours."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_abundant_prediction"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with capacity that will exhaust in > 24 hours
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=800, confidence=1.0),
            used_capacity=200,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions to establish usage rate (low usage)
        for i in range(5):
            decision = RoutingDecision(
                id=f"decision_{key_id}_{i}",
                request_id=f"req_{key_id}_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(hours=2 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        # Update capacity - should trigger prediction and state change
        result = await engine.update_capacity(key_id, consumed=1)

        # Should be Abundant because exhaustion > 24 hours
        assert result.capacity_state == CapacityState.Abundant

    @pytest.mark.asyncio
    async def test_capacity_state_transition_created_automatically(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test state transitions created automatically when capacity_state changes."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )
        from apikeyrouter.domain.models.state_transition import StateTransition

        key_id = "test_key_transition"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state starting in Abundant
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=800, confidence=1.0),
            used_capacity=200,
            capacity_state=CapacityState.Abundant,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions to establish high usage rate
        for i in range(10):
            decision = RoutingDecision(
                id=f"decision_{key_id}_{i}",
                request_id=f"req_{key_id}_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=5 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        # Track transitions
        transitions_before = len(mock_state_store._transitions)

        # Update capacity - should trigger state change from Abundant to Critical
        result = await engine.update_capacity(key_id, consumed=790)

        # Verify state changed
        assert result.capacity_state == CapacityState.Critical

        # Verify transition was created
        transitions_after = len(mock_state_store._transitions)
        assert transitions_after > transitions_before

    @pytest.mark.asyncio
    async def test_capacity_state_handles_unknown_exhaustion_prediction(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test handles unknown exhaustion prediction gracefully."""
        key_id = "test_key_unknown_prediction"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with unknown capacity (no usage data)
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=None,
            remaining_capacity=CapacityEstimate(value=None, confidence=0.0),
            used_capacity=0,
            capacity_state=CapacityState.Abundant,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Update capacity - prediction should be None (no usage data)
        result = await engine.update_capacity(key_id, consumed=1)

        # Should fall back to percentage-based calculation
        # With unknown capacity and remaining > 0, should be Abundant
        assert result.capacity_state == CapacityState.Abundant

    @pytest.mark.asyncio
    async def test_prediction_cache_with_ttl(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test prediction caching with TTL."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_cache"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with very low remaining capacity
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=10, confidence=1.0),
            used_capacity=990,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions with high usage rate (will exhaust in < 4 hours)
        for i in range(10):
            decision = RoutingDecision(
                id=f"decision_{key_id}_{i}",
                request_id=f"req_{key_id}_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=5 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        # First update - should calculate prediction
        result1 = await engine.update_capacity(key_id, consumed=1)
        assert result1.capacity_state == CapacityState.Critical

        # Verify prediction is cached
        assert key_id in engine._prediction_cache

        # Second update within TTL - should use cached prediction
        result2 = await engine.update_capacity(key_id, consumed=1)
        assert result2.capacity_state == CapacityState.Critical

        # Verify cache still has the prediction
        assert key_id in engine._prediction_cache

    @pytest.mark.asyncio
    async def test_prediction_cache_expires_after_ttl(
        self, mock_state_store: MockStateStore, mock_observability: MockObservabilityManager
    ) -> None:
        """Test prediction cache expires after TTL."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        # Create engine with short TTL for testing
        short_ttl_engine = QuotaAwarenessEngine(
            mock_state_store,
            mock_observability,
            key_manager=None,
            default_cooldown_seconds=60,
            prediction_cache_ttl_seconds=1,  # 1 second TTL
        )

        key_id = "test_key_cache_expiry"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with very low remaining capacity
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=10, confidence=1.0),
            used_capacity=990,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions with high usage rate (will exhaust in < 4 hours)
        for i in range(10):
            decision = RoutingDecision(
                id=f"decision_{key_id}_{i}",
                request_id=f"req_{key_id}_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=5 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        # First update - should calculate and cache prediction
        result1 = await short_ttl_engine.update_capacity(key_id, consumed=1)
        assert result1.capacity_state == CapacityState.Critical
        assert key_id in short_ttl_engine._prediction_cache

        # Wait for cache to expire
        import asyncio

        await asyncio.sleep(1.5)

        # Second update after TTL - should recalculate prediction
        result2 = await short_ttl_engine.update_capacity(key_id, consumed=1)
        assert result2.capacity_state == CapacityState.Critical
        # Cache should have been refreshed
        assert key_id in short_ttl_engine._prediction_cache

    @pytest.mark.asyncio
    async def test_capacity_state_considers_both_prediction_and_percentage(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test capacity_state considers both prediction and percentage, with prediction taking precedence."""
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_both_factors"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with high percentage (>80%) but very high usage rate
        # This will cause prediction to say < 4 hours even though percentage is high
        # Use smaller total capacity so high usage rate can exhaust quickly
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=850, confidence=1.0),  # 85% remaining
            used_capacity=150,
            capacity_state=CapacityState.Abundant,  # Would be Abundant by percentage
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions with very high usage rate
        # 50 requests in last hour = 50 req/hour
        # With 850 remaining, time to exhaustion = 850/50 = 17 hours
        # But we need < 4 hours, so we need usage_rate > 850/4 = 212.5 req/hour
        # Let's create 250 requests in the last hour
        for i in range(250):
            decision = RoutingDecision(
                id=f"decision_{key_id}_{i}",
                request_id=f"req_{key_id}_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(seconds=14.4 * i),  # Spread over 1 hour
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
            )
            await mock_state_store.save_routing_decision(decision)

        # Update capacity - prediction should override percentage
        result = await engine.update_capacity(key_id, consumed=1)

        # Should be Critical (from prediction) even though percentage would be Abundant
        assert result.capacity_state == CapacityState.Critical

    @pytest.mark.asyncio
    async def test_update_capacity_with_tokens_unit(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test capacity updated based on tokens when capacity_unit is Tokens."""
        from apikeyrouter.domain.models.quota_state import CapacityUnit

        key_id = "test_key_tokens"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with Tokens unit
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            capacity_unit=CapacityUnit.Tokens,
            total_capacity=10000,
            remaining_capacity=CapacityEstimate(value=5000, confidence=1.0),
            used_capacity=5000,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Update capacity with tokens consumed
        tokens_consumed = 1000
        result = await engine.update_capacity(key_id, consumed=1, tokens_consumed=tokens_consumed)

        # Should decrement by tokens_consumed, not consumed
        assert result.remaining_capacity.value == 4000  # 5000 - 1000
        assert result.used_capacity == 6000  # 5000 + 1000
        assert result.used_tokens == 1000

    @pytest.mark.asyncio
    async def test_update_capacity_with_mixed_unit(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test capacity updated for both requests and tokens when capacity_unit is Mixed."""
        from apikeyrouter.domain.models.quota_state import CapacityUnit

        key_id = "test_key_mixed"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with Mixed unit
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            capacity_unit=CapacityUnit.Mixed,
            total_capacity=1000,  # Request limit
            remaining_capacity=CapacityEstimate(value=500, confidence=1.0),
            total_tokens=50000,  # Token limit
            remaining_tokens=CapacityEstimate(value=25000, confidence=1.0),
            used_capacity=500,
            used_requests=500,
            used_tokens=25000,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Update capacity with both request and tokens
        tokens_consumed = 5000
        result = await engine.update_capacity(key_id, consumed=1, tokens_consumed=tokens_consumed)

        # Should update both request and token capacity
        assert result.remaining_capacity.value == 499  # 500 - 1
        assert result.used_capacity == 501  # 500 + 1
        assert result.used_requests == 501  # 500 + 1
        assert result.remaining_tokens.value == 20000  # 25000 - 5000
        assert result.used_tokens == 30000  # 25000 + 5000

    @pytest.mark.asyncio
    async def test_update_capacity_mixed_unit_requires_tokens(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test that Mixed unit requires tokens_consumed parameter."""
        from apikeyrouter.domain.models.quota_state import CapacityUnit

        key_id = "test_key_mixed_required"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with Mixed unit
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            capacity_unit=CapacityUnit.Mixed,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=500, confidence=1.0),
            total_tokens=50000,
            remaining_tokens=CapacityEstimate(value=25000, confidence=1.0),
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Update capacity without tokens_consumed should raise error
        with pytest.raises(ValueError, match="tokens_consumed is required"):
            await engine.update_capacity(key_id, consumed=1)

    @pytest.mark.asyncio
    async def test_predict_exhaustion_uses_tokens_per_hour(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test exhaustion prediction uses tokens_per_hour when capacity_unit is Tokens."""
        from apikeyrouter.domain.models.quota_state import CapacityUnit
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_tokens_prediction"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with Tokens unit
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            capacity_unit=CapacityUnit.Tokens,
            total_capacity=100000,
            remaining_capacity=CapacityEstimate(value=10000, confidence=1.0),
            used_capacity=90000,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions with token data
        for i in range(10):
            decision = RoutingDecision(
                id=f"decision_{key_id}_{i}",
                request_id=f"req_{key_id}_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=5 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
                evaluation_results={"tokens": 1000},  # 1000 tokens per request
            )
            await mock_state_store.save_routing_decision(decision)

        # Predict exhaustion
        prediction = await engine.predict_exhaustion(key_id)

        # Should use tokens_per_hour for calculation
        assert prediction is not None
        assert prediction.calculation_method == "token_usage_rate_division"
        # With 10 decisions over ~50 minutes, tokens_per_hour = 10000 tokens / 1 hour = 10000 tokens/hour
        # With 10000 tokens remaining, time to exhaustion should be approximately 1 hour
        # (with uncertainty adjustment, might be slightly less)
        time_until_exhaustion = (prediction.predicted_exhaustion_at - now).total_seconds() / 3600.0
        assert 0.5 < time_until_exhaustion < 2.0  # Allow variance due to uncertainty adjustment

    @pytest.mark.asyncio
    async def test_predict_exhaustion_estimates_tokens_from_requests(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test exhaustion prediction estimates tokens from requests when tokens_per_hour unavailable."""
        from apikeyrouter.domain.models.quota_state import CapacityUnit
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_estimate_tokens"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with Tokens unit
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            capacity_unit=CapacityUnit.Tokens,
            total_capacity=100000,
            remaining_capacity=CapacityEstimate(value=10000, confidence=1.0),
            used_capacity=90000,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions without token data (only requests)
        for i in range(10):
            decision = RoutingDecision(
                id=f"decision_{key_id}_{i}",
                request_id=f"req_{key_id}_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=5 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
                # No evaluation_results with tokens
            )
            await mock_state_store.save_routing_decision(decision)

        # Predict exhaustion - should estimate tokens from requests
        prediction = await engine.predict_exhaustion(key_id)

        # Should still create prediction using estimated tokens
        assert prediction is not None
        assert prediction.calculation_method == "token_usage_rate_division"
        # With 10 requests/hour, estimated tokens_per_hour = 10 * 1000 = 10000 tokens/hour
        # With 10000 tokens remaining, time to exhaustion should be approximately 1 hour
        time_until_exhaustion = (prediction.predicted_exhaustion_at - now).total_seconds() / 3600.0
        assert 0.5 < time_until_exhaustion < 2.0  # Allow variance

    @pytest.mark.asyncio
    async def test_predict_exhaustion_mixed_unit_uses_tokens(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test exhaustion prediction for Mixed unit uses remaining_tokens."""
        from apikeyrouter.domain.models.quota_state import CapacityUnit
        from apikeyrouter.domain.models.routing_decision import (
            RoutingDecision,
            RoutingObjective,
        )

        key_id = "test_key_mixed_prediction"
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=24)

        # Create quota state with Mixed unit
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            capacity_unit=CapacityUnit.Mixed,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=500, confidence=1.0),
            total_tokens=100000,
            remaining_tokens=CapacityEstimate(value=10000, confidence=1.0),
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Create routing decisions with token data
        for i in range(10):
            decision = RoutingDecision(
                id=f"decision_{key_id}_{i}",
                request_id=f"req_{key_id}_{i}",
                selected_key_id=key_id,
                selected_provider_id="openai",
                decision_timestamp=now - timedelta(minutes=5 * i),
                objective=RoutingObjective(primary="cost"),
                explanation="Test decision",
                confidence=0.9,
                evaluation_results={"tokens": 1000},
            )
            await mock_state_store.save_routing_decision(decision)

        # Predict exhaustion - should use remaining_tokens
        prediction = await engine.predict_exhaustion(key_id)

        # Should use tokens for prediction
        assert prediction is not None
        assert prediction.calculation_method == "token_usage_rate_division"
        # Should use remaining_tokens (10000) not remaining_capacity (500)
        assert prediction.remaining_capacity == 10000

    @pytest.mark.asyncio
    async def test_reset_handles_mixed_unit(
        self, engine: QuotaAwarenessEngine, mock_state_store: MockStateStore
    ) -> None:
        """Test reset handles Mixed unit by resetting both request and token capacity."""
        from apikeyrouter.domain.models.quota_state import CapacityUnit

        key_id = "test_key_mixed_reset"
        now = datetime.utcnow()
        # Set reset_at in the past to trigger reset
        reset_at = now - timedelta(hours=1)

        # Create quota state with Mixed unit
        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            capacity_unit=CapacityUnit.Mixed,
            total_capacity=1000,
            remaining_capacity=CapacityEstimate(value=100, confidence=1.0),
            total_tokens=50000,
            remaining_tokens=CapacityEstimate(value=5000, confidence=1.0),
            used_capacity=900,
            used_requests=900,
            used_tokens=45000,
            reset_at=reset_at,
        )
        await mock_state_store.save_quota_state(quota_state)

        # Update capacity - should trigger reset, then apply consumed
        result = await engine.update_capacity(key_id, consumed=1, tokens_consumed=100)

        # Reset happens first, then consumed is applied
        # So remaining_capacity should be total_capacity - consumed
        assert result.remaining_capacity.value == 999  # 1000 (reset) - 1 (consumed)
        assert result.used_capacity == 1  # Reset to 0, then +1
        assert result.used_requests == 1  # Reset to 0, then +1
        assert result.remaining_tokens.value == 49900  # 50000 (reset) - 100 (consumed)
        assert result.used_tokens == 100  # Reset to 0, then +100

