"""Tests for FairnessStrategy."""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from apikeyrouter.domain.components.routing_strategies.fairness import (
    FairnessStrategy,
)
from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.domain.models.quota_state import (
    CapacityEstimate,
    CapacityState,
    QuotaState,
    TimeWindow,
)
from apikeyrouter.domain.models.request_intent import Message, RequestIntent


class MockObservabilityManager(ObservabilityManager):
    """Mock ObservabilityManager for testing."""

    def __init__(self) -> None:
        """Initialize mock observability manager."""
        self.logs: list[dict] = []

    async def emit_event(
        self, event_type: str, payload: dict, metadata: dict | None = None
    ) -> None:
        """Emit event to mock store."""
        pass

    async def log(self, level: str, message: str, context: dict | None = None) -> None:
        """Log to mock store."""
        self.logs.append({"level": level, "message": message, "context": context or {}})


@pytest.fixture
def mock_observability() -> MockObservabilityManager:
    """Create mock observability manager."""
    return MockObservabilityManager()


@pytest.fixture
def mock_quota_engine():
    """Create mock quota awareness engine."""
    from datetime import datetime, timedelta

    from apikeyrouter.domain.components.quota_awareness_engine import (
        QuotaAwarenessEngine,
    )

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
def fairness_strategy(mock_observability, mock_quota_engine) -> FairnessStrategy:
    """Create FairnessStrategy instance."""
    return FairnessStrategy(
        observability_manager=mock_observability,
        quota_awareness_engine=mock_quota_engine,
    )


@pytest.fixture
def sample_request_intent() -> RequestIntent:
    """Create sample request intent."""
    return RequestIntent(
        model="gpt-4",
        messages=[Message(role="user", content="Hello!")],
        parameters={"max_tokens": 100},
    )


@pytest_asyncio.fixture
async def sample_keys() -> list[APIKey]:
    """Create sample keys for testing."""
    return [
        APIKey(
            id="key1",
            provider_id="openai",
            key_material="test_key_material_1",
            state=KeyState.Available,
            usage_count=10,
            failure_count=0,
        ),
        APIKey(
            id="key2",
            provider_id="openai",
            key_material="test_key_material_2",
            state=KeyState.Available,
            usage_count=20,
            failure_count=0,
        ),
        APIKey(
            id="key3",
            provider_id="openai",
            key_material="test_key_material_3",
            state=KeyState.Available,
            usage_count=30,
            failure_count=0,
        ),
    ]


@pytest.mark.asyncio
async def test_score_keys_less_used_higher_score(
    fairness_strategy, sample_keys, sample_request_intent
):
    """Test that less used keys get higher scores."""
    scores = await fairness_strategy.score_keys(sample_keys, sample_request_intent)

    # key1 has lowest usage (10), should have highest score
    # key3 has highest usage (30), should have lowest score
    assert scores["key1"] > scores["key2"]
    assert scores["key2"] > scores["key3"]
    assert scores["key1"] == 1.0  # Least used = highest score (normalized)


@pytest.mark.asyncio
async def test_score_keys_equal_usage_equal_scores(fairness_strategy, sample_request_intent):
    """Test that keys with equal usage get equal scores."""
    keys = [
        APIKey(
            id="key1",
            provider_id="openai",
            key_material="sk-test-key-1",
            state=KeyState.Available,
            usage_count=10,
        ),
        APIKey(
            id="key2",
            provider_id="openai",
            key_material="sk-test-key-2",
            state=KeyState.Available,
            usage_count=10,
        ),
    ]

    scores = await fairness_strategy.score_keys(keys, sample_request_intent)

    # All scores should be equal (enables round-robin)
    assert scores["key1"] == scores["key2"]
    assert scores["key1"] == 1.0


@pytest.mark.asyncio
async def test_score_keys_normalizes_scores(fairness_strategy, sample_keys, sample_request_intent):
    """Test that scores are normalized to 0.0-1.0 range."""
    scores = await fairness_strategy.score_keys(sample_keys, sample_request_intent)

    # All scores should be in valid range
    for key_id, score in scores.items():
        assert 0.0 <= score <= 1.0, f"Score for {key_id} is {score}, not in [0.0, 1.0]"


@pytest.mark.asyncio
async def test_calculate_relative_usage(fairness_strategy, sample_keys):
    """Test that relative usage is calculated correctly."""
    relative_usage = fairness_strategy._calculate_relative_usage(sample_keys)

    # Total usage = 10 + 20 + 30 = 60
    assert relative_usage["key1"] == pytest.approx(10 / 60, abs=0.01)
    assert relative_usage["key2"] == pytest.approx(20 / 60, abs=0.01)
    assert relative_usage["key3"] == pytest.approx(30 / 60, abs=0.01)


@pytest.mark.asyncio
async def test_calculate_relative_usage_zero_usage(
    fairness_strategy,
):
    """Test that zero usage returns equal relative usage."""
    keys = [
        APIKey(
            id="key1",
            provider_id="openai",
            key_material="sk-test-key-1",
            state=KeyState.Available,
            usage_count=0,
        ),
        APIKey(
            id="key2",
            provider_id="openai",
            key_material="sk-test-key-2",
            state=KeyState.Available,
            usage_count=0,
        ),
    ]

    relative_usage = fairness_strategy._calculate_relative_usage(keys)

    # All should have 0.0 relative usage (no usage yet)
    assert relative_usage["key1"] == 0.0
    assert relative_usage["key2"] == 0.0


@pytest.mark.asyncio
async def test_filter_by_quota_state_filters_exhausted(
    fairness_strategy, sample_keys, mock_quota_engine
):
    """Test that exhausted keys are filtered out."""
    from datetime import datetime, timedelta

    # Set up quota states: key1 exhausted, key2 abundant
    mock_quota_engine.quota_states = {
        "key1": QuotaState(
            id="quota_key1",
            key_id="key1",
            capacity_state=CapacityState.Exhausted,
            remaining_capacity=CapacityEstimate(value=0, confidence=1.0),
            total_capacity=1000,
            used_capacity=1000,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        ),
        "key2": QuotaState(
            id="quota_key2",
            key_id="key2",
            capacity_state=CapacityState.Abundant,
            remaining_capacity=CapacityEstimate(value=1000, confidence=1.0),
            total_capacity=1000,
            used_capacity=0,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        ),
    }

    filtered_keys, quota_states, filtered_out = await fairness_strategy.filter_by_quota_state(
        sample_keys[:2]
    )

    # key1 should be filtered out (exhausted)
    assert len(filtered_keys) == 1
    assert "key1" not in [k.id for k in filtered_keys]
    assert "key2" in [k.id for k in filtered_keys]
    assert len(filtered_out) == 1
    assert filtered_out[0].id == "key1"


@pytest.mark.asyncio
async def test_select_key_selects_least_used(fairness_strategy, sample_keys):
    """Test that select_key selects key with highest score (least used)."""
    scores = {"key1": 1.0, "key2": 0.5, "key3": 0.1}

    selected_key_id, score = fairness_strategy.select_key(scores, sample_keys)

    assert selected_key_id == "key1"
    assert score == 1.0


@pytest.mark.asyncio
async def test_select_key_handles_ties_with_round_robin(fairness_strategy, sample_keys):
    """Test that select_key handles ties with round-robin."""
    scores = {"key1": 1.0, "key2": 1.0, "key3": 0.1}

    # First selection
    selected_key_id1, score1 = fairness_strategy.select_key(
        scores, sample_keys, last_selected_key_id=None
    )
    assert selected_key_id1 in ["key1", "key2"]
    assert score1 == 1.0

    # Second selection with round-robin
    selected_key_id2, score2 = fairness_strategy.select_key(
        scores, sample_keys, last_selected_key_id=selected_key_id1
    )
    assert selected_key_id2 in ["key1", "key2"]
    assert selected_key_id2 != selected_key_id1  # Should be different due to round-robin
    assert score2 == 1.0


@pytest.mark.asyncio
async def test_generate_explanation_includes_usage(
    fairness_strategy,
):
    """Test that explanation includes usage information."""
    from datetime import datetime, timedelta

    quota_state = QuotaState(
        id="quota_key1",
        key_id="key1",
        capacity_state=CapacityState.Abundant,
        remaining_capacity=CapacityEstimate(value=1000, confidence=1.0),
        total_capacity=1000,
        used_capacity=0,
        time_window=TimeWindow.Daily,
        reset_at=datetime.utcnow() + timedelta(days=1),
    )

    explanation = fairness_strategy.generate_explanation(
        selected_key_id="key1",
        usage_count=10,
        relative_usage=0.25,
        quota_state=quota_state,
        eligible_count=3,
        filtered_count=0,
        total_usage=40,
    )

    assert "key1" in explanation
    assert "10 total requests" in explanation
    assert "25.0%" in explanation or "25%" in explanation
    assert "abundant" in explanation.lower()
    assert "3 eligible keys" in explanation
    assert "fair load distribution" in explanation.lower()


@pytest.mark.asyncio
async def test_score_keys_empty_list_returns_empty_dict(fairness_strategy, sample_request_intent):
    """Test that scoring empty list returns empty dict."""
    scores = await fairness_strategy.score_keys([], sample_request_intent)
    assert scores == {}


@pytest.mark.asyncio
async def test_filter_by_quota_state_no_quota_engine_returns_all(mock_observability, sample_keys):
    """Test that filter_by_quota_state returns all keys when no quota engine."""
    strategy = FairnessStrategy(
        observability_manager=mock_observability,
        quota_awareness_engine=None,
    )

    filtered_keys, quota_states, filtered_out = await strategy.filter_by_quota_state(sample_keys)

    assert len(filtered_keys) == len(sample_keys)
    assert quota_states == {}
    assert filtered_out == []


@pytest.mark.asyncio
async def test_score_keys_balances_load(fairness_strategy, sample_request_intent):
    """Test that strategy balances load across keys."""
    # Create keys with different usage
    keys = [
        APIKey(
            id="key1",
            provider_id="openai",
            key_material="sk-test-key-1",
            state=KeyState.Available,
            usage_count=5,
        ),
        APIKey(
            id="key2",
            provider_id="openai",
            key_material="sk-test-key-2",
            state=KeyState.Available,
            usage_count=15,
        ),
        APIKey(
            id="key3",
            provider_id="openai",
            key_material="sk-test-key-3",
            state=KeyState.Available,
            usage_count=25,
        ),
    ]

    scores = await fairness_strategy.score_keys(keys, sample_request_intent)

    # Least used key should have highest score
    assert scores["key1"] > scores["key2"]
    assert scores["key2"] > scores["key3"]


@pytest.mark.asyncio
async def test_select_key_prevents_starvation(
    fairness_strategy,
):
    """Test that round-robin prevents key starvation."""
    keys = [
        APIKey(
            id="key1",
            provider_id="openai",
            key_material="sk-test-key-1",
            state=KeyState.Available,
            usage_count=10,
        ),
        APIKey(
            id="key2",
            provider_id="openai",
            key_material="sk-test-key-2",
            state=KeyState.Available,
            usage_count=10,
        ),
        APIKey(
            id="key3",
            provider_id="openai",
            key_material="sk-test-key-3",
            state=KeyState.Available,
            usage_count=10,
        ),
    ]

    scores = {"key1": 1.0, "key2": 1.0, "key3": 1.0}

    # Simulate round-robin selection
    selected_keys = []
    last_key = None
    for _ in range(6):  # Select 6 times
        selected_key_id, _ = fairness_strategy.select_key(
            scores, keys, last_selected_key_id=last_key
        )
        selected_keys.append(selected_key_id)
        last_key = selected_key_id

    # All keys should be selected (no starvation)
    assert "key1" in selected_keys
    assert "key2" in selected_keys
    assert "key3" in selected_keys
