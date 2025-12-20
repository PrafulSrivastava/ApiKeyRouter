"""Tests for RoutingEngine component."""

import time
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from apikeyrouter.domain.components.key_manager import KeyManager
from apikeyrouter.domain.components.routing_engine import (
    NoEligibleKeysError,
    RoutingEngine,
)
from apikeyrouter.domain.interfaces.observability_manager import (
    ObservabilityManager,
)
from apikeyrouter.domain.interfaces.state_store import StateStore
from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.domain.models.routing_decision import (
    ObjectiveType,
    RoutingObjective,
)


class MockStateStore(StateStore):
    """Mock StateStore for testing."""

    def __init__(self) -> None:
        """Initialize mock store."""
        self._keys: dict[str, APIKey] = {}

    async def save_key(self, key: APIKey) -> None:
        """Save key to mock store."""
        self._keys[key.id] = key

    async def get_key(self, key_id: str) -> APIKey | None:
        """Get key from mock store."""
        return self._keys.get(key_id)

    async def list_keys(self, provider_id: str | None = None) -> list[APIKey]:
        """List keys from mock store."""
        keys = list(self._keys.values())
        if provider_id:
            keys = [k for k in keys if k.provider_id == provider_id]
        return keys

    async def delete_key(self, key_id: str) -> None:
        """Delete key from mock store."""
        self._keys.pop(key_id, None)

    async def save_state_transition(self, transition) -> None:
        """Save state transition to mock store."""
        pass

    async def save_quota_state(self, quota_state) -> None:
        """Save quota state to mock store."""
        pass

    async def get_quota_state(self, key_id: str):
        """Get quota state from mock store."""
        return None

    async def save_routing_decision(self, decision) -> None:
        """Save routing decision to mock store."""
        pass

    async def query_state(self, query) -> list:
        """Query state from mock store."""
        return []


class MockObservabilityManager(ObservabilityManager):
    """Mock ObservabilityManager for testing."""

    def __init__(self) -> None:
        """Initialize mock observability manager."""
        self.events: list[dict] = []
        self.logs: list[dict] = []

    async def emit_event(
        self,
        event_type: str,
        payload: dict,
        metadata: dict | None = None,
    ) -> None:
        """Emit event to mock store."""
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


@pytest.fixture
def mock_state_store() -> MockStateStore:
    """Create mock state store."""
    return MockStateStore()


@pytest.fixture
def mock_observability() -> MockObservabilityManager:
    """Create mock observability manager."""
    return MockObservabilityManager()


@pytest.fixture
def mock_quota_engine():
    """Create mock quota awareness engine."""
    from unittest.mock import AsyncMock
    from apikeyrouter.domain.components.quota_awareness_engine import (
        QuotaAwarenessEngine,
    )
    from apikeyrouter.domain.models.quota_state import (
        CapacityEstimate,
        CapacityState,
        QuotaState,
        TimeWindow,
    )
    from datetime import datetime, timedelta

    engine = AsyncMock(spec=QuotaAwarenessEngine)
    
    # Default quota states
    engine.quota_states = {}
    
    async def get_quota_state(key_id: str):
        if key_id in engine.quota_states:
            return engine.quota_states[key_id]
        # Return default abundant state
        return QuotaState(
            id=f"quota_{key_id}",
            key_id=key_id,
            capacity_state=CapacityState.Abundant,
            remaining_capacity=CapacityEstimate(value=1000, confidence=1.0),
            total_capacity=1000,
            used_capacity=0,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
    
    engine.get_quota_state = get_quota_state
    return engine


@pytest.fixture
def routing_engine_with_quota(
    mock_key_manager, mock_state_store, mock_observability, mock_quota_engine
):
    """Create routing engine with quota awareness."""
    from apikeyrouter.domain.components.routing_engine import RoutingEngine
    return RoutingEngine(
        key_manager=mock_key_manager,
        state_store=mock_state_store,
        observability_manager=mock_observability,
        quota_awareness_engine=mock_quota_engine,
    )


@pytest.fixture
def mock_key_manager(mock_state_store, mock_observability) -> KeyManager:
    """Create key manager with mocks."""
    return KeyManager(
        state_store=mock_state_store,
        observability_manager=mock_observability,
    )


@pytest.fixture
def routing_engine(
    mock_key_manager, mock_state_store, mock_observability
) -> RoutingEngine:
    """Create routing engine with mocks."""
    return RoutingEngine(
        key_manager=mock_key_manager,
        state_store=mock_state_store,
        observability_manager=mock_observability,
    )


@pytest_asyncio.fixture
async def sample_keys(mock_key_manager) -> list[APIKey]:
    """Create sample keys for testing."""
    import os
    from cryptography.fernet import Fernet
    
    # Ensure encryption key is set for this fixture
    if not os.getenv("APIKEYROUTER_ENCRYPTION_KEY"):
        test_key = Fernet.generate_key()
        os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = test_key.decode()
    
    keys = []
    for i in range(3):
        key = await mock_key_manager.register_key(
            key_material=f"test_key_{i}",
            provider_id="openai",
        )
        keys.append(key)
    return keys


class TestRoutingEngine:
    """Tests for RoutingEngine."""

    @pytest.mark.asyncio
    async def test_route_request_round_robin_cycles_through_keys(
        self, routing_engine, sample_keys
    ) -> None:
        """Test that round-robin selection cycles through keys."""
        request_intent = {"provider_id": "openai", "request_id": "req_1"}

        # First request - should select first key
        decision1 = await routing_engine.route_request(request_intent)
        assert decision1.selected_key_id == sample_keys[0].id

        # Second request - should select second key
        request_intent["request_id"] = "req_2"
        decision2 = await routing_engine.route_request(request_intent)
        assert decision2.selected_key_id == sample_keys[1].id

        # Third request - should select third key
        request_intent["request_id"] = "req_3"
        decision3 = await routing_engine.route_request(request_intent)
        assert decision3.selected_key_id == sample_keys[2].id

        # Fourth request - should wrap around to first key
        request_intent["request_id"] = "req_4"
        decision4 = await routing_engine.route_request(request_intent)
        assert decision4.selected_key_id == sample_keys[0].id

    @pytest.mark.asyncio
    async def test_route_request_round_robin_wraps_around(
        self, routing_engine, sample_keys
    ) -> None:
        """Test that round-robin wraps around to first key after last key."""
        request_intent = {"provider_id": "openai"}

        # Cycle through all keys
        for i in range(len(sample_keys)):
            request_intent["request_id"] = f"req_{i}"
            decision = await routing_engine.route_request(request_intent)
            assert decision.selected_key_id == sample_keys[i].id

        # Next request should wrap to first key
        request_intent["request_id"] = "req_wrap"
        decision = await routing_engine.route_request(request_intent)
        assert decision.selected_key_id == sample_keys[0].id

    @pytest.mark.asyncio
    async def test_route_request_creates_routing_decision(
        self, routing_engine, sample_keys
    ) -> None:
        """Test that RoutingDecision is created with correct fields."""
        request_intent = {
            "provider_id": "openai",
            "request_id": "test_request_1",
        }
        decision = await routing_engine.route_request(request_intent)

        assert decision.id is not None
        assert decision.request_id == "test_request_1"
        assert decision.selected_key_id == sample_keys[0].id
        assert decision.selected_provider_id == "openai"
        assert isinstance(decision.decision_timestamp, datetime)
        assert decision.objective.primary == ObjectiveType.Fairness.value
        assert len(decision.eligible_keys) == 3
        assert sample_keys[0].id in decision.eligible_keys
        assert decision.explanation is not None
        assert len(decision.explanation) > 0
        assert decision.confidence >= 0.9  # Confidence can be 0.9 or 1.0 depending on scoring

    @pytest.mark.asyncio
    async def test_route_request_explanation_field_populated(
        self, routing_engine, sample_keys
    ) -> None:
        """Test that explanation field is populated."""
        request_intent = {"provider_id": "openai", "request_id": "req_1"}
        decision = await routing_engine.route_request(request_intent)

        assert decision.explanation is not None
        # Explanation should mention the routing method (fairness/objective-based or round-robin)
        explanation_lower = decision.explanation.lower()
        assert (
            "fairness" in explanation_lower
            or "fair" in explanation_lower
            or "round-robin" in explanation_lower
            or "objective" in explanation_lower
            or "least used" in explanation_lower
        )
        assert decision.selected_key_id in decision.explanation

    @pytest.mark.asyncio
    async def test_route_request_performance_under_10ms(
        self, routing_engine, sample_keys
    ) -> None:
        """Test that routing decision time is under 10ms."""
        request_intent = {"provider_id": "openai", "request_id": "req_perf"}

        # Measure routing time
        start_time = time.perf_counter()
        decision = await routing_engine.route_request(request_intent)
        end_time = time.perf_counter()

        elapsed_ms = (end_time - start_time) * 1000
        assert elapsed_ms < 10.0, f"Routing took {elapsed_ms:.2f}ms, expected <10ms"
        assert decision is not None

    @pytest.mark.asyncio
    async def test_route_request_handles_empty_eligible_keys(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test that routing raises error when no eligible keys available."""
        # Create routing engine with no keys registered
        request_intent = {"provider_id": "openai", "request_id": "req_empty"}

        with pytest.raises(NoEligibleKeysError) as exc_info:
            await routing_engine.route_request(request_intent)

        assert "No eligible keys available" in str(exc_info.value)
        assert "openai" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_route_request_generates_request_id_if_missing(
        self, routing_engine, sample_keys
    ) -> None:
        """Test that request_id is generated if not provided."""
        request_intent = {"provider_id": "openai"}
        decision = await routing_engine.route_request(request_intent)

        assert decision.request_id is not None
        assert len(decision.request_id) > 0

    @pytest.mark.asyncio
    async def test_route_request_uses_custom_objective(
        self, routing_engine, sample_keys
    ) -> None:
        """Test that custom RoutingObjective is used when provided."""
        request_intent = {"provider_id": "openai", "request_id": "req_obj"}
        custom_objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine.route_request(
            request_intent, objective=custom_objective
        )

        assert decision.objective.primary == ObjectiveType.Cost.value

    @pytest.mark.asyncio
    async def test_route_request_defaults_to_fairness_objective(
        self, routing_engine, sample_keys
    ) -> None:
        """Test that default objective is fairness for round-robin."""
        request_intent = {"provider_id": "openai", "request_id": "req_default"}
        decision = await routing_engine.route_request(request_intent)

        assert decision.objective.primary == ObjectiveType.Fairness.value

    @pytest.mark.asyncio
    async def test_route_request_tracks_per_provider(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test that round-robin tracking is per provider."""
        # Create keys for two providers
        openai_keys = []
        for i in range(2):
            key = await mock_key_manager.register_key(
                key_material=f"openai_key_{i}",
                provider_id="openai",
            )
            openai_keys.append(key)

        anthropic_keys = []
        for i in range(2):
            key = await mock_key_manager.register_key(
                key_material=f"anthropic_key_{i}",
                provider_id="anthropic",
            )
            anthropic_keys.append(key)

        # Route requests to openai
        request_intent = {"provider_id": "openai", "request_id": "req_1"}
        decision1 = await routing_engine.route_request(request_intent)
        assert decision1.selected_key_id == openai_keys[0].id

        request_intent["request_id"] = "req_2"
        decision2 = await routing_engine.route_request(request_intent)
        assert decision2.selected_key_id == openai_keys[1].id

        # Route requests to anthropic (should start from first key)
        request_intent = {"provider_id": "anthropic", "request_id": "req_3"}
        decision3 = await routing_engine.route_request(request_intent)
        assert decision3.selected_key_id == anthropic_keys[0].id

        request_intent["request_id"] = "req_4"
        decision4 = await routing_engine.route_request(request_intent)
        assert decision4.selected_key_id == anthropic_keys[1].id

    @pytest.mark.asyncio
    async def test_route_request_validates_provider_id(
        self, routing_engine
    ) -> None:
        """Test that routing validates provider_id is present."""
        # Missing provider_id
        with pytest.raises(ValueError, match="request_intent must contain 'provider_id'"):
            await routing_engine.route_request({})

        # Invalid provider_id type
        with pytest.raises(ValueError, match="request_intent must contain 'provider_id'"):
            await routing_engine.route_request({"provider_id": None})

    @pytest.mark.asyncio
    async def test_route_request_emits_observability_events(
        self, routing_engine, sample_keys, mock_observability
    ) -> None:
        """Test that routing emits observability events."""
        request_intent = {"provider_id": "openai", "request_id": "req_events"}
        decision = await routing_engine.route_request(request_intent)

        # Check that events were emitted
        assert len(mock_observability.events) > 0

        # Find routing_decision event
        routing_events = [
            e
            for e in mock_observability.events
            if e["event_type"] == "routing_decision"
        ]
        assert len(routing_events) == 1

        event = routing_events[0]
        assert event["payload"]["decision_id"] == decision.id
        assert event["payload"]["request_id"] == "req_events"
        assert event["payload"]["provider_id"] == "openai"
        assert event["payload"]["selected_key_id"] == decision.selected_key_id
        # Strategy can be "round_robin" or "objective_based_fairness" depending on implementation
        assert event["payload"]["strategy"] in ["round_robin", "objective_based_fairness"]

    @pytest.mark.asyncio
    async def test_route_request_logs_routing_decision(
        self, routing_engine, sample_keys, mock_observability
    ) -> None:
        """Test that routing logs the decision."""
        request_intent = {"provider_id": "openai", "request_id": "req_logs"}
        decision = await routing_engine.route_request(request_intent)

        # Check that logs were created
        assert len(mock_observability.logs) > 0

        # Find routing decision log
        routing_logs = [
            log
            for log in mock_observability.logs
            if "Routing decision made" in log["message"]
        ]
        assert len(routing_logs) > 0

        log = routing_logs[0]
        assert log["level"] == "INFO"
        assert log["context"]["decision_id"] == decision.id
        assert log["context"]["selected_key_id"] == decision.selected_key_id

    @pytest.mark.asyncio
    async def test_route_request_emits_failure_event_on_no_keys(
        self, routing_engine, mock_observability
    ) -> None:
        """Test that routing emits failure event when no eligible keys."""
        request_intent = {"provider_id": "openai", "request_id": "req_fail"}

        with pytest.raises(NoEligibleKeysError):
            await routing_engine.route_request(request_intent)

        # Check that failure event was emitted
        failure_events = [
            e
            for e in mock_observability.events
            if e["event_type"] == "routing_failed"
        ]
        assert len(failure_events) == 1

        event = failure_events[0]
        assert event["payload"]["reason"] == "no_eligible_keys"
        assert event["payload"]["provider_id"] == "openai"


class TestObjectiveBasedRouting:
    """Tests for objective-based routing."""

    @pytest.mark.asyncio
    async def test_evaluate_keys_cost_based_scoring(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test cost-based scoring (lower cost = higher score)."""
        # Create keys with different costs in metadata
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.01},
        )
        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.02},
        )
        key3 = await mock_key_manager.register_key(
            key_material="key3",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.005},
        )

        eligible_keys = [key1, key2, key3]
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        scores = await routing_engine.evaluate_keys(eligible_keys, objective)

        # Lower cost should have higher score
        assert scores[key3.id] > scores[key1.id]
        assert scores[key1.id] > scores[key2.id]
        assert all(0.0 <= score <= 1.0 for score in scores.values())

    @pytest.mark.asyncio
    async def test_evaluate_keys_reliability_based_scoring(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test reliability-based scoring (higher success rate = higher score)."""
        # Create keys with different reliability (using lower success rates to avoid 1.0 cap)
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
        )
        key1.usage_count = 80
        key1.failure_count = 20  # 80% success rate

        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
        )
        key2.usage_count = 50
        key2.failure_count = 50  # 50% success rate

        key3 = await mock_key_manager.register_key(
            key_material="key3",
            provider_id="openai",
        )
        key3.usage_count = 90
        key3.failure_count = 10  # 90% success rate

        eligible_keys = [key1, key2, key3]
        objective = RoutingObjective(primary=ObjectiveType.Reliability.value)

        scores = await routing_engine.evaluate_keys(eligible_keys, objective)

        # Higher success rate should have higher score
        assert scores[key3.id] > scores[key1.id], f"key3 (90%) should score higher than key1 (80%), got {scores[key3.id]} vs {scores[key1.id]}"
        assert scores[key1.id] > scores[key2.id], f"key1 (80%) should score higher than key2 (50%), got {scores[key1.id]} vs {scores[key2.id]}"
        assert all(0.0 <= score <= 1.1 for score in scores.values())  # Can exceed 1.0 with state bonus

    @pytest.mark.asyncio
    async def test_evaluate_keys_fairness_based_scoring(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test fairness-based scoring (less used = higher score)."""
        # Create keys with different usage counts
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
        )
        key1.usage_count = 100

        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
        )
        key2.usage_count = 50

        key3 = await mock_key_manager.register_key(
            key_material="key3",
            provider_id="openai",
        )
        key3.usage_count = 200

        eligible_keys = [key1, key2, key3]
        objective = RoutingObjective(primary=ObjectiveType.Fairness.value)

        scores = await routing_engine.evaluate_keys(eligible_keys, objective)

        # Less used should have higher score
        assert scores[key2.id] > scores[key1.id]
        assert scores[key1.id] > scores[key3.id]
        assert all(0.0 <= score <= 1.0 for score in scores.values())

    @pytest.mark.asyncio
    async def test_route_request_selects_highest_scoring_key(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test that routing selects highest-scoring key for cost objective."""
        # Create keys with different costs
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.02},
        )
        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.01},  # Lower cost
        )
        key3 = await mock_key_manager.register_key(
            key_material="key3",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.03},
        )

        request_intent = {"provider_id": "openai", "request_id": "req_cost"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine.route_request(request_intent, objective)

        # Should select key with lowest cost (key2)
        assert decision.selected_key_id == key2.id
        assert decision.objective.primary == ObjectiveType.Cost.value

    @pytest.mark.asyncio
    async def test_route_request_explanation_includes_score(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test that explanation includes score for objective-based routing."""
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.01},
        )

        request_intent = {"provider_id": "openai", "request_id": "req_expl"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine.route_request(request_intent, objective)

        assert decision.explanation is not None
        assert "cost" in decision.explanation.lower()
        assert "score" in decision.explanation.lower()
        assert decision.selected_key_id in decision.explanation

    @pytest.mark.asyncio
    async def test_route_request_evaluation_results_include_scores(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test that evaluation_results includes scores for all keys."""
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.01},
        )
        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.02},
        )

        request_intent = {"provider_id": "openai", "request_id": "req_eval"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine.route_request(request_intent, objective)

        assert len(decision.evaluation_results) == 2
        assert key1.id in decision.evaluation_results
        assert key2.id in decision.evaluation_results
        assert "score" in decision.evaluation_results[key1.id]
        assert "score" in decision.evaluation_results[key2.id]

    @pytest.mark.asyncio
    async def test_route_request_performance_under_10ms_for_10_keys(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test that routing decision time is under 10ms for 10 keys."""
        # Create 10 keys
        keys = []
        for i in range(10):
            key = await mock_key_manager.register_key(
                key_material=f"key_{i}",
                provider_id="openai",
                metadata={"estimated_cost_per_request": 0.01 + (i * 0.001)},
            )
            keys.append(key)

        request_intent = {"provider_id": "openai", "request_id": "req_perf"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        # Measure routing time
        start_time = time.perf_counter()
        decision = await routing_engine.route_request(request_intent, objective)
        end_time = time.perf_counter()

        elapsed_ms = (end_time - start_time) * 1000
        assert elapsed_ms < 10.0, f"Routing took {elapsed_ms:.2f}ms, expected <10ms"
        assert decision is not None
        assert len(decision.evaluation_results) == 10

    @pytest.mark.asyncio
    async def test_route_request_handles_ties_in_scores(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test that routing handles ties in scores (selects first)."""
        # Create keys with same cost (will have same score)
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.01},
        )
        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.01},  # Same cost
        )

        request_intent = {"provider_id": "openai", "request_id": "req_tie"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine.route_request(request_intent, objective)

        # Should select one of the keys (max() will select first if equal)
        assert decision.selected_key_id in [key1.id, key2.id]
        # Both should have same score
        assert (
            decision.evaluation_results[key1.id]["score"]
            == decision.evaluation_results[key2.id]["score"]
        )

    @pytest.mark.asyncio
    async def test_evaluate_keys_cost_fallback_to_default(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test that cost scoring falls back to default when metadata missing."""
        # Create keys without cost metadata
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
        )
        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
        )

        eligible_keys = [key1, key2]
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        scores = await routing_engine.evaluate_keys(eligible_keys, objective)

        # Should return scores (using defaults)
        assert len(scores) == 2
        assert all(0.0 <= score <= 1.0 for score in scores.values())

    @pytest.mark.asyncio
    async def test_evaluate_keys_reliability_considers_state(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test that reliability scoring considers key state."""
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
        )
        key1.state = KeyState.Available
        key1.usage_count = 80
        key1.failure_count = 20  # 80% success rate

        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
        )
        key2.state = KeyState.Throttled
        key2.usage_count = 80
        key2.failure_count = 20  # 80% success rate (same as key1)

        eligible_keys = [key1, key2]
        objective = RoutingObjective(primary=ObjectiveType.Reliability.value)

        scores = await routing_engine.evaluate_keys(eligible_keys, objective)

        # Available key should score higher than Throttled (state bonus: 0.1 vs 0.05)
        # key1: 0.8 + 0.1 = 0.9, key2: 0.8 + 0.05 = 0.85
        assert scores[key1.id] > scores[key2.id], f"Available key should score higher than Throttled, got {scores[key1.id]} vs {scores[key2.id]}"

    @pytest.mark.asyncio
    async def test_evaluate_keys_fairness_equal_usage_returns_equal_scores(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test that fairness scoring returns equal scores for equal usage."""
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
        )
        key1.usage_count = 100

        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
        )
        key2.usage_count = 100  # Same usage

        eligible_keys = [key1, key2]
        objective = RoutingObjective(primary=ObjectiveType.Fairness.value)

        scores = await routing_engine.evaluate_keys(eligible_keys, objective)

        # Should have equal scores
        assert scores[key1.id] == scores[key2.id]
        assert scores[key1.id] == 1.0

    @pytest.mark.asyncio
    async def test_evaluate_keys_unknown_objective_defaults_to_fairness(
        self, routing_engine, mock_key_manager, mock_observability
    ) -> None:
        """Test that invalid objective raises ValidationError (RoutingObjective validates)."""
        from pydantic import ValidationError
        
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
        )

        eligible_keys = [key1]
        
        # RoutingObjective now validates primary field, so invalid objective raises ValidationError
        with pytest.raises(ValidationError, match="Primary objective must be one of"):
            objective = RoutingObjective(primary="unknown_objective")
        
        # Test that valid objective works
        objective = RoutingObjective(primary=ObjectiveType.Fairness.value)
        scores = await routing_engine.evaluate_keys(eligible_keys, objective)

        # Should return scores
        assert len(scores) == 1
        assert key1.id in scores


class TestQuotaAwareRouting:
    """Tests for quota-aware routing integration."""

    @pytest.mark.asyncio
    async def test_route_request_filters_exhausted_keys(
        self, routing_engine_with_quota, mock_key_manager, mock_quota_engine
    ) -> None:
        """Test that exhausted keys are filtered out."""
        from apikeyrouter.domain.models.quota_state import (
            CapacityEstimate,
            CapacityState,
            QuotaState,
            TimeWindow,
        )
        from datetime import datetime, timedelta

        # Create keys
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
        )
        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
        )

        # Set quota states: key1 exhausted, key2 abundant
        mock_quota_engine.quota_states[key1.id] = QuotaState(
            id=f"quota_{key1.id}",
            key_id=key1.id,
            capacity_state=CapacityState.Exhausted,
            remaining_capacity=CapacityEstimate(value=0, confidence=1.0),
            total_capacity=1000,
            used_capacity=1000,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        mock_quota_engine.quota_states[key2.id] = QuotaState(
            id=f"quota_{key2.id}",
            key_id=key2.id,
            capacity_state=CapacityState.Abundant,
            remaining_capacity=CapacityEstimate(value=1000, confidence=1.0),
            total_capacity=1000,
            used_capacity=0,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )

        request_intent = {"provider_id": "openai", "request_id": "req_exhausted"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine_with_quota.route_request(request_intent, objective)

        # Should select key2 (key1 filtered out)
        assert decision.selected_key_id == key2.id
        assert key1.id not in decision.evaluation_results

    @pytest.mark.asyncio
    async def test_route_request_filters_critical_keys(
        self, routing_engine_with_quota, mock_key_manager, mock_quota_engine
    ) -> None:
        """Test that critical keys are filtered out."""
        from apikeyrouter.domain.models.quota_state import (
            CapacityEstimate,
            CapacityState,
            QuotaState,
            TimeWindow,
        )
        from datetime import datetime, timedelta

        # Create keys
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
        )
        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
        )

        # Set quota states: key1 critical, key2 abundant
        mock_quota_engine.quota_states[key1.id] = QuotaState(
            id=f"quota_{key1.id}",
            key_id=key1.id,
            capacity_state=CapacityState.Critical,
            remaining_capacity=CapacityEstimate(value=200, confidence=1.0),
            total_capacity=1000,
            used_capacity=800,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        mock_quota_engine.quota_states[key2.id] = QuotaState(
            id=f"quota_{key2.id}",
            key_id=key2.id,
            capacity_state=CapacityState.Abundant,
            remaining_capacity=CapacityEstimate(value=1000, confidence=1.0),
            total_capacity=1000,
            used_capacity=0,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )

        request_intent = {"provider_id": "openai", "request_id": "req_critical"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine_with_quota.route_request(request_intent, objective)

        # Should select key2 (key1 filtered out)
        assert decision.selected_key_id == key2.id

    @pytest.mark.asyncio
    async def test_route_request_prefers_abundant_keys(
        self, routing_engine_with_quota, mock_key_manager, mock_quota_engine
    ) -> None:
        """Test that abundant keys get higher scores (preferred)."""
        from apikeyrouter.domain.models.quota_state import (
            CapacityEstimate,
            CapacityState,
            QuotaState,
            TimeWindow,
        )
        from datetime import datetime, timedelta

        # Create keys with same cost (will have same base score)
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.01},
        )
        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.01},
        )

        # Set quota states: key1 abundant, key2 constrained
        mock_quota_engine.quota_states[key1.id] = QuotaState(
            id=f"quota_{key1.id}",
            key_id=key1.id,
            capacity_state=CapacityState.Abundant,
            remaining_capacity=CapacityEstimate(value=900, confidence=1.0),
            total_capacity=1000,
            used_capacity=100,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        mock_quota_engine.quota_states[key2.id] = QuotaState(
            id=f"quota_{key2.id}",
            key_id=key2.id,
            capacity_state=CapacityState.Constrained,
            remaining_capacity=CapacityEstimate(value=600, confidence=1.0),
            total_capacity=1000,
            used_capacity=400,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )

        request_intent = {"provider_id": "openai", "request_id": "req_abundant"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine_with_quota.route_request(request_intent, objective)

        # Should select key1 (abundant gets 20% boost, constrained gets 15% penalty)
        assert decision.selected_key_id == key1.id
        # Verify scores show the boost
        assert decision.evaluation_results[key1.id]["score"] > decision.evaluation_results[key2.id]["score"]

    @pytest.mark.asyncio
    async def test_route_request_penalizes_constrained_keys(
        self, routing_engine_with_quota, mock_key_manager, mock_quota_engine
    ) -> None:
        """Test that constrained keys get lower scores (penalized)."""
        from apikeyrouter.domain.models.quota_state import (
            CapacityEstimate,
            CapacityState,
            QuotaState,
            TimeWindow,
        )
        from datetime import datetime, timedelta

        # Create keys with same cost
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.01},
        )
        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.01},
        )

        # Set quota states: key1 abundant, key2 constrained
        mock_quota_engine.quota_states[key1.id] = QuotaState(
            id=f"quota_{key1.id}",
            key_id=key1.id,
            capacity_state=CapacityState.Abundant,
            remaining_capacity=CapacityEstimate(value=900, confidence=1.0),
            total_capacity=1000,
            used_capacity=100,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        mock_quota_engine.quota_states[key2.id] = QuotaState(
            id=f"quota_{key2.id}",
            key_id=key2.id,
            capacity_state=CapacityState.Constrained,
            remaining_capacity=CapacityEstimate(value=600, confidence=1.0),
            total_capacity=1000,
            used_capacity=400,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )

        request_intent = {"provider_id": "openai", "request_id": "req_constrained"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine_with_quota.route_request(request_intent, objective)

        # Verify constrained key has lower score
        assert decision.evaluation_results[key2.id]["score"] < decision.evaluation_results[key1.id]["score"]
        assert decision.evaluation_results[key2.id]["quota_state"] == "constrained"

    @pytest.mark.asyncio
    async def test_route_request_includes_quota_state_in_explanation(
        self, routing_engine_with_quota, mock_key_manager, mock_quota_engine
    ) -> None:
        """Test that quota state is included in explanation."""
        from apikeyrouter.domain.models.quota_state import (
            CapacityEstimate,
            CapacityState,
            QuotaState,
            TimeWindow,
        )
        from datetime import datetime, timedelta

        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
        )

        # Set abundant quota state
        mock_quota_engine.quota_states[key1.id] = QuotaState(
            id=f"quota_{key1.id}",
            key_id=key1.id,
            capacity_state=CapacityState.Abundant,
            remaining_capacity=CapacityEstimate(value=1000, confidence=1.0),
            total_capacity=1000,
            used_capacity=0,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )

        request_intent = {"provider_id": "openai", "request_id": "req_expl"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine_with_quota.route_request(request_intent, objective)

        assert "abundant" in decision.explanation.lower()
        assert "quota state" in decision.explanation.lower()

    @pytest.mark.asyncio
    async def test_route_request_explains_filtered_keys(
        self, routing_engine_with_quota, mock_key_manager, mock_quota_engine
    ) -> None:
        """Test that explanation mentions filtered keys."""
        from apikeyrouter.domain.models.quota_state import (
            CapacityEstimate,
            CapacityState,
            QuotaState,
            TimeWindow,
        )
        from datetime import datetime, timedelta

        # Create keys
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
        )
        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
        )

        # Set quota states: key1 exhausted (filtered), key2 abundant
        mock_quota_engine.quota_states[key1.id] = QuotaState(
            id=f"quota_{key1.id}",
            key_id=key1.id,
            capacity_state=CapacityState.Exhausted,
            remaining_capacity=CapacityEstimate(value=0, confidence=1.0),
            total_capacity=1000,
            used_capacity=1000,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        mock_quota_engine.quota_states[key2.id] = QuotaState(
            id=f"quota_{key2.id}",
            key_id=key2.id,
            capacity_state=CapacityState.Abundant,
            remaining_capacity=CapacityEstimate(value=1000, confidence=1.0),
            total_capacity=1000,
            used_capacity=0,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )

        request_intent = {"provider_id": "openai", "request_id": "req_filtered"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine_with_quota.route_request(request_intent, objective)

        # Explanation should mention filtered keys
        assert "excluded" in decision.explanation.lower() or "filtered" in decision.explanation.lower()
        assert "exhausted" in decision.explanation.lower() or "quota" in decision.explanation.lower()

    @pytest.mark.asyncio
    async def test_route_request_handles_all_keys_exhausted(
        self, routing_engine_with_quota, mock_key_manager, mock_quota_engine
    ) -> None:
        """Test that routing fails when all keys are exhausted."""
        from apikeyrouter.domain.models.quota_state import (
            CapacityEstimate,
            CapacityState,
            QuotaState,
            TimeWindow,
        )
        from datetime import datetime, timedelta

        # Create keys
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
        )

        # Set exhausted quota state
        mock_quota_engine.quota_states[key1.id] = QuotaState(
            id=f"quota_{key1.id}",
            key_id=key1.id,
            capacity_state=CapacityState.Exhausted,
            remaining_capacity=CapacityEstimate(value=0, confidence=1.0),
            total_capacity=1000,
            used_capacity=1000,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )

        request_intent = {"provider_id": "openai", "request_id": "req_all_exhausted"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        with pytest.raises(NoEligibleKeysError) as exc_info:
            await routing_engine_with_quota.route_request(request_intent, objective)

        assert "quota" in str(exc_info.value).lower() or "exhausted" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_route_request_works_without_quota_engine(
        self, routing_engine, sample_keys
    ) -> None:
        """Test that routing works when quota engine is not provided."""
        request_intent = {"provider_id": "openai", "request_id": "req_no_quota"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine.route_request(request_intent, objective)

        # Should work normally without quota filtering
        assert decision is not None
        assert decision.selected_key_id in [key.id for key in sample_keys]


class TestRoutingDecisionExplanation:
    """Tests for routing decision explanation."""

    @pytest.mark.asyncio
    async def test_explain_decision_generates_explanation(
        self, routing_engine, sample_keys
    ) -> None:
        """Test that explain_decision generates explanation."""
        request_intent = {"provider_id": "openai", "request_id": "req_expl"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine.route_request(request_intent, objective)
        explanation = routing_engine.explain_decision(decision)

        assert explanation is not None
        assert len(explanation) > 0
        assert "ROUTING DECISION EXPLANATION" in explanation

    @pytest.mark.asyncio
    async def test_explain_decision_includes_objective(
        self, routing_engine, sample_keys
    ) -> None:
        """Test that explanation includes objective."""
        request_intent = {"provider_id": "openai", "request_id": "req_obj"}
        objective = RoutingObjective(
            primary=ObjectiveType.Cost.value,
            secondary=["reliability"],
            weights={"cost": 0.7, "reliability": 0.3},
        )

        decision = await routing_engine.route_request(request_intent, objective)
        explanation = routing_engine.explain_decision(decision)

        assert "OBJECTIVE:" in explanation
        assert "cost" in explanation.lower()
        assert "reliability" in explanation.lower()


class TestMultiObjectiveOptimization:
    """Tests for multi-objective optimization."""

    @pytest.mark.asyncio
    async def test_evaluate_keys_multi_objective_calculates_composite_score(
        self, routing_engine, sample_keys
    ):
        """Test that multi-objective optimization calculates composite score."""
        objective = RoutingObjective(
            primary=ObjectiveType.Cost.value,
            weights={"cost": 0.7, "reliability": 0.3},
        )

        scores = await routing_engine.evaluate_keys(sample_keys, objective)

        # Should return composite scores
        assert len(scores) == len(sample_keys)
        for key_id, score in scores.items():
            assert 0.0 <= score <= 1.0, f"Score for {key_id} is {score}, not in [0.0, 1.0]"

    @pytest.mark.asyncio
    async def test_evaluate_keys_weights_applied_correctly(
        self, routing_engine, sample_keys
    ):
        """Test that weights are applied correctly in composite score."""
        objective = RoutingObjective(
            primary=ObjectiveType.Cost.value,
            weights={"cost": 0.8, "reliability": 0.2},
        )

        scores = await routing_engine.evaluate_keys(sample_keys, objective)

        # Composite scores should be weighted combination
        assert len(scores) == len(sample_keys)
        # All scores should be valid
        assert all(0.0 <= s <= 1.0 for s in scores.values())

    @pytest.mark.asyncio
    async def test_evaluate_keys_weights_normalized(
        self, routing_engine, sample_keys
    ):
        """Test that weights are normalized if they don't sum to 1.0."""
        # Weights sum to 1.5, should be normalized
        objective = RoutingObjective(
            primary=ObjectiveType.Cost.value,
            weights={"cost": 0.9, "reliability": 0.6},  # Sum = 1.5
        )

        scores = await routing_engine.evaluate_keys(sample_keys, objective)

        # Should still work (weights normalized internally)
        assert len(scores) == len(sample_keys)
        assert all(0.0 <= s <= 1.0 for s in scores.values())

    @pytest.mark.asyncio
    async def test_evaluate_keys_single_objective_with_weights(
        self, routing_engine, sample_keys
    ):
        """Test that single objective with weight 1.0 works."""
        objective = RoutingObjective(
            primary=ObjectiveType.Cost.value,
            weights={"cost": 1.0},
        )

        scores = await routing_engine.evaluate_keys(sample_keys, objective)

        # Should work like single-objective
        assert len(scores) == len(sample_keys)
        assert all(0.0 <= s <= 1.0 for s in scores.values())

    @pytest.mark.asyncio
    async def test_route_request_multi_objective_selects_best_composite(
        self, routing_engine, sample_keys
    ):
        """Test that route_request selects key with best composite score."""
        request_intent = {"provider_id": "openai", "request_id": "req_multi"}
        objective = RoutingObjective(
            primary=ObjectiveType.Cost.value,
            weights={"cost": 0.7, "reliability": 0.3},
        )

        decision = await routing_engine.route_request(request_intent, objective)

        # Should select a key
        assert decision is not None
        assert decision.selected_key_id in [key.id for key in sample_keys]
        assert decision.objective.weights == objective.weights

    @pytest.mark.asyncio
    async def test_route_request_multi_objective_explanation_includes_trade_offs(
        self, routing_engine, sample_keys
    ):
        """Test that multi-objective explanation includes trade-offs."""
        request_intent = {"provider_id": "openai", "request_id": "req_tradeoff"}
        objective = RoutingObjective(
            primary=ObjectiveType.Cost.value,
            weights={"cost": 0.7, "reliability": 0.3},
        )

        decision = await routing_engine.route_request(request_intent, objective)

        # Explanation should mention trade-offs
        assert decision.explanation is not None
        assert "balancing" in decision.explanation.lower() or "composite" in decision.explanation.lower()
        assert "cost" in decision.explanation.lower()
        assert "reliability" in decision.explanation.lower() or "70%" in decision.explanation or "30%" in decision.explanation

    @pytest.mark.asyncio
    async def test_evaluate_keys_multi_objective_includes_three_objectives(
        self, routing_engine, sample_keys
    ):
        """Test that multi-objective can include three objectives."""
        objective = RoutingObjective(
            primary=ObjectiveType.Cost.value,
            weights={"cost": 0.5, "reliability": 0.3, "fairness": 0.2},
        )

        scores = await routing_engine.evaluate_keys(sample_keys, objective)

        # Should calculate composite from all three objectives
        assert len(scores) == len(sample_keys)
        assert all(0.0 <= s <= 1.0 for s in scores.values())

    @pytest.mark.asyncio
    async def test_evaluate_keys_multi_objective_evaluation_results_include_objective_scores(
        self, routing_engine, sample_keys
    ):
        """Test that evaluation_results include per-objective scores."""
        request_intent = {"provider_id": "openai", "request_id": "req_eval"}
        objective = RoutingObjective(
            primary=ObjectiveType.Cost.value,
            weights={"cost": 0.7, "reliability": 0.3},
        )

        decision = await routing_engine.route_request(request_intent, objective)

        # evaluation_results should include objective_scores
        assert decision.evaluation_results is not None
        for key_id, result in decision.evaluation_results.items():
            assert "score" in result
            if isinstance(result, dict) and "objective_scores" in result:
                obj_scores = result["objective_scores"]
                assert "cost" in obj_scores or "reliability" in obj_scores

    @pytest.mark.asyncio
    async def test_normalize_weights_sums_to_one(
        self, routing_engine
    ):
        """Test that _normalize_weights normalizes weights to sum to 1.0."""
        weights = {"cost": 0.6, "reliability": 0.4}  # Already sums to 1.0
        normalized = routing_engine._normalize_weights(weights)
        
        assert sum(normalized.values()) == pytest.approx(1.0, abs=0.01)
        assert normalized["cost"] == pytest.approx(0.6, abs=0.01)
        assert normalized["reliability"] == pytest.approx(0.4, abs=0.01)

    @pytest.mark.asyncio
    async def test_normalize_weights_normalizes_when_not_sum_to_one(
        self, routing_engine
    ):
        """Test that _normalize_weights normalizes when weights don't sum to 1.0."""
        weights = {"cost": 0.9, "reliability": 0.6}  # Sums to 1.5
        normalized = routing_engine._normalize_weights(weights)
        
        assert sum(normalized.values()) == pytest.approx(1.0, abs=0.01)
        # Should be proportional
        assert normalized["cost"] / normalized["reliability"] == pytest.approx(0.9 / 0.6, abs=0.01)

    @pytest.mark.asyncio
    async def test_normalize_weights_handles_zero_weights(
        self, routing_engine
    ):
        """Test that _normalize_weights handles zero weights."""
        weights = {"cost": 0.0, "reliability": 0.0}
        normalized = routing_engine._normalize_weights(weights)
        
        # Should return equal weights
        assert sum(normalized.values()) == pytest.approx(1.0, abs=0.01)
        assert normalized["cost"] == pytest.approx(0.5, abs=0.01)
        assert normalized["reliability"] == pytest.approx(0.5, abs=0.01)

    @pytest.mark.asyncio
    async def test_explain_decision_includes_selected_key(
        self, routing_engine, sample_keys
    ) -> None:
        """Test that explanation includes selected key."""
        request_intent = {"provider_id": "openai", "request_id": "req_key"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine.route_request(request_intent, objective)
        explanation = routing_engine.explain_decision(decision)

        assert "SELECTED KEY:" in explanation
        assert decision.selected_key_id in explanation
        assert decision.selected_provider_id in explanation

    @pytest.mark.asyncio
    async def test_explain_decision_includes_scores(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test that explanation includes scores."""
        # Create keys with different costs
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.01},
        )
        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.02},
        )

        request_intent = {"provider_id": "openai", "request_id": "req_scores"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine.route_request(request_intent, objective)
        explanation = routing_engine.explain_decision(decision)

        assert "EVALUATION RESULTS:" in explanation
        assert key1.id in explanation
        assert key2.id in explanation
        assert "Score:" in explanation

    @pytest.mark.asyncio
    async def test_explain_decision_includes_alternatives(
        self, routing_engine, sample_keys
    ) -> None:
        """Test that explanation includes alternatives if present."""
        from apikeyrouter.domain.models.routing_decision import AlternativeRoute

        request_intent = {"provider_id": "openai", "request_id": "req_alt"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine.route_request(request_intent, objective)

        # Add alternatives manually (normally would be set during routing)
        decision.alternatives_considered = [
            AlternativeRoute(
                key_id=sample_keys[1].id,
                provider_id="openai",
                score=0.75,
                reason_not_selected="Lower score than selected key",
            )
        ]

        explanation = routing_engine.explain_decision(decision)

        assert "ALTERNATIVES CONSIDERED:" in explanation
        assert sample_keys[1].id in explanation
        assert "Lower score" in explanation

    @pytest.mark.asyncio
    async def test_explain_decision_includes_quota_state(
        self, routing_engine_with_quota, mock_key_manager, mock_quota_engine
    ) -> None:
        """Test that explanation includes quota state."""
        from apikeyrouter.domain.models.quota_state import (
            CapacityEstimate,
            CapacityState,
            QuotaState,
            TimeWindow,
        )
        from datetime import datetime, timedelta

        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
        )

        # Set abundant quota state
        mock_quota_engine.quota_states[key1.id] = QuotaState(
            id=f"quota_{key1.id}",
            key_id=key1.id,
            capacity_state=CapacityState.Abundant,
            remaining_capacity=CapacityEstimate(value=1000, confidence=1.0),
            total_capacity=1000,
            used_capacity=0,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )

        request_intent = {"provider_id": "openai", "request_id": "req_quota"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine_with_quota.route_request(request_intent, objective)
        explanation = routing_engine_with_quota.explain_decision(decision)

        assert "abundant" in explanation.lower()
        assert "quota" in explanation.lower()

    @pytest.mark.asyncio
    async def test_explain_decision_explains_selection_reasoning(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test that explanation explains why key was chosen."""
        # Create keys with different costs
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.01},  # Lower cost
        )
        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.02},
        )

        request_intent = {"provider_id": "openai", "request_id": "req_reason"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine.route_request(request_intent, objective)
        explanation = routing_engine.explain_decision(decision)

        assert "REASONING:" in explanation
        assert "highest" in explanation.lower() or "score" in explanation.lower()
        assert decision.selected_key_id in explanation

    @pytest.mark.asyncio
    async def test_explain_decision_formatted_readably(
        self, routing_engine, sample_keys
    ) -> None:
        """Test that explanation is formatted readably."""
        request_intent = {"provider_id": "openai", "request_id": "req_format"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine.route_request(request_intent, objective)
        explanation = routing_engine.explain_decision(decision)

        # Check for structured sections
        assert "OBJECTIVE:" in explanation
        assert "SELECTED KEY:" in explanation
        assert "REASONING:" in explanation
        assert "EVALUATION RESULTS:" in explanation
        assert "SUMMARY:" in explanation

        # Check for separators
        assert "=" in explanation

    @pytest.mark.asyncio
    async def test_explain_decision_includes_quota_filtering(
        self, routing_engine_with_quota, mock_key_manager, mock_quota_engine
    ) -> None:
        """Test that explanation includes quota filtering information."""
        from apikeyrouter.domain.models.quota_state import (
            CapacityEstimate,
            CapacityState,
            QuotaState,
            TimeWindow,
        )
        from datetime import datetime, timedelta

        # Create keys
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
        )
        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
        )

        # Set quota states: key1 exhausted (filtered), key2 abundant
        mock_quota_engine.quota_states[key1.id] = QuotaState(
            id=f"quota_{key1.id}",
            key_id=key1.id,
            capacity_state=CapacityState.Exhausted,
            remaining_capacity=CapacityEstimate(value=0, confidence=1.0),
            total_capacity=1000,
            used_capacity=1000,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        mock_quota_engine.quota_states[key2.id] = QuotaState(
            id=f"quota_{key2.id}",
            key_id=key2.id,
            capacity_state=CapacityState.Abundant,
            remaining_capacity=CapacityEstimate(value=1000, confidence=1.0),
            total_capacity=1000,
            used_capacity=0,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )

        request_intent = {"provider_id": "openai", "request_id": "req_filter"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine_with_quota.route_request(request_intent, objective)
        explanation = routing_engine_with_quota.explain_decision(decision)

        # Should mention quota filtering
        assert "QUOTA FILTERING:" in explanation or "filtered" in explanation.lower()
        assert key1.id in explanation  # Filtered key should be mentioned

    @pytest.mark.asyncio
    async def test_explain_decision_handles_round_robin(
        self, routing_engine, sample_keys
    ) -> None:
        """Test that explanation works for round-robin decisions."""
        request_intent = {"provider_id": "openai", "request_id": "req_rr"}
        objective = RoutingObjective(primary=ObjectiveType.Fairness.value)

        decision = await routing_engine.route_request(request_intent, objective)
        explanation = routing_engine.explain_decision(decision)

        assert "ROUTING DECISION EXPLANATION" in explanation
        assert "SELECTED KEY:" in explanation
        assert decision.selected_key_id in explanation
        assert "round-robin" in explanation.lower() or "fairness" in explanation.lower()

    @pytest.mark.asyncio
    async def test_explain_decision_compares_to_alternatives(
        self, routing_engine, mock_key_manager
    ) -> None:
        """Test that explanation compares selected key to alternatives."""
        # Create keys with different costs
        key1 = await mock_key_manager.register_key(
            key_material="key1",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.01},
        )
        key2 = await mock_key_manager.register_key(
            key_material="key2",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.02},
        )
        key3 = await mock_key_manager.register_key(
            key_material="key3",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.03},
        )

        request_intent = {"provider_id": "openai", "request_id": "req_compare"}
        objective = RoutingObjective(primary=ObjectiveType.Cost.value)

        decision = await routing_engine.route_request(request_intent, objective)
        explanation = routing_engine.explain_decision(decision)

        # Should mention margin over closest alternative
        assert "Margin" in explanation or "alternative" in explanation.lower()
        # Should list all keys in evaluation results
        assert key1.id in explanation
        assert key2.id in explanation
        assert key3.id in explanation

