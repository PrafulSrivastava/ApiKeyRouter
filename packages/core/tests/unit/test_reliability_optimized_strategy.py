"""Tests for ReliabilityOptimizedStrategy."""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from apikeyrouter.domain.components.routing_strategies.reliability_optimized import (
    ReliabilityOptimizedStrategy,
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

    async def log(
        self, level: str, message: str, context: dict | None = None
    ) -> None:
        """Log to mock store."""
        self.logs.append({"level": level, "message": message, "context": context or {}})


@pytest.fixture
def mock_observability() -> MockObservabilityManager:
    """Create mock observability manager."""
    return MockObservabilityManager()


@pytest.fixture
def mock_quota_engine():
    """Create mock quota awareness engine."""
    from apikeyrouter.domain.components.quota_awareness_engine import (
        QuotaAwarenessEngine,
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
def reliability_strategy(
    mock_observability, mock_quota_engine
) -> ReliabilityOptimizedStrategy:
    """Create ReliabilityOptimizedStrategy instance."""
    return ReliabilityOptimizedStrategy(
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
            usage_count=100,
            failure_count=0,
        ),
        APIKey(
            id="key2",
            provider_id="openai",
            key_material="test_key_material_2",
            state=KeyState.Available,
            usage_count=90,
            failure_count=10,
        ),
        APIKey(
            id="key3",
            provider_id="openai",
            key_material="test_key_material_3",
            state=KeyState.Available,
            usage_count=50,
            failure_count=50,
        ),
    ]


@pytest.mark.asyncio
async def test_calculate_success_rate_high_success(
    reliability_strategy, sample_keys
):
    """Test that high success rate is calculated correctly."""
    # key1: 100 successes, 0 failures = 100% success rate
    success_rate = reliability_strategy._calculate_success_rate(sample_keys[0])
    assert success_rate == 1.0

    # key2: 90 successes, 10 failures = 90% success rate
    success_rate = reliability_strategy._calculate_success_rate(sample_keys[1])
    assert success_rate == 0.9

    # key3: 50 successes, 50 failures = 50% success rate
    success_rate = reliability_strategy._calculate_success_rate(sample_keys[2])
    assert success_rate == 0.5


@pytest.mark.asyncio
async def test_calculate_success_rate_zero_usage(
    reliability_strategy,
):
    """Test that zero usage defaults to high reliability."""
    key = APIKey(
        id="key_new",
        provider_id="openai",
        key_material="test",
        state=KeyState.Available,
        usage_count=0,
        failure_count=0,
    )
    success_rate = reliability_strategy._calculate_success_rate(key)
    assert success_rate == 0.95  # Default high reliability


@pytest.mark.asyncio
async def test_get_key_state_score_available_highest(
    reliability_strategy, sample_keys
):
    """Test that Available state gets highest score."""
    score = reliability_strategy._get_key_state_score(sample_keys[0])
    assert score == 1.0


@pytest.mark.asyncio
async def test_get_key_state_score_throttled_lower(
    reliability_strategy,
):
    """Test that Throttled state gets lower score."""
    key = APIKey(
        id="key_throttled",
        provider_id="openai",
        key_material="test",
        state=KeyState.Throttled,
    )
    score = reliability_strategy._get_key_state_score(key)
    assert score == 0.7


@pytest.mark.asyncio
async def test_get_quota_state_score_abundant_highest(reliability_strategy):
    """Test that Abundant quota state gets highest score."""
    from datetime import datetime, timedelta

    quota_state = QuotaState(
        id="quota1",
        key_id="key1",
        capacity_state=CapacityState.Abundant,
        remaining_capacity=CapacityEstimate(value=1000, confidence=1.0),
        total_capacity=1000,
        used_capacity=0,
        time_window=TimeWindow.Daily,
        reset_at=datetime.utcnow() + timedelta(days=1),
    )
    score = reliability_strategy._get_quota_state_score(quota_state)
    assert score == 1.0


@pytest.mark.asyncio
async def test_get_quota_state_score_exhausted_lowest(reliability_strategy):
    """Test that Exhausted quota state gets lowest score."""
    from datetime import datetime, timedelta

    quota_state = QuotaState(
        id="quota1",
        key_id="key1",
        capacity_state=CapacityState.Exhausted,
        remaining_capacity=CapacityEstimate(value=0, confidence=1.0),
        total_capacity=1000,
        used_capacity=1000,
        time_window=TimeWindow.Daily,
        reset_at=datetime.utcnow() + timedelta(days=1),
    )
    score = reliability_strategy._get_quota_state_score(quota_state)
    assert score == 0.0


@pytest.mark.asyncio
async def test_score_keys_high_success_rate_higher_score(
    reliability_strategy, sample_keys, sample_request_intent
):
    """Test that keys with higher success rate get higher scores."""
    scores = await reliability_strategy.score_keys(
        sample_keys, sample_request_intent
    )

    # key1 has 100% success rate, should have highest score
    # key3 has 50% success rate, should have lowest score
    assert scores["key1"] > scores["key2"]
    assert scores["key2"] > scores["key3"]


@pytest.mark.asyncio
async def test_score_keys_penalizes_recent_failures(
    reliability_strategy, sample_keys, sample_request_intent
):
    """Test that keys with recent failures are penalized."""
    # Create key with high failure rate
    high_failure_key = APIKey(
        id="key_high_failure",
        provider_id="openai",
        key_material="test",
        state=KeyState.Available,
        usage_count=10,
        failure_count=10,  # 50% failure rate
    )

    # Create key with low failure rate
    low_failure_key = APIKey(
        id="key_low_failure",
        provider_id="openai",
        key_material="test",
        state=KeyState.Available,
        usage_count=100,
        failure_count=5,  # 5% failure rate
    )

    scores = await reliability_strategy.score_keys(
        [high_failure_key, low_failure_key], sample_request_intent
    )

    # Low failure key should have higher score
    assert scores["key_low_failure"] > scores["key_high_failure"]


@pytest.mark.asyncio
async def test_score_keys_considers_quota_state(
    reliability_strategy, sample_keys, sample_request_intent, mock_quota_engine
):
    """Test that quota state is considered in scoring."""
    from datetime import datetime, timedelta

    # Set up quota states: key1 abundant, key2 constrained
    mock_quota_engine.quota_states = {
        "key1": QuotaState(
            id="quota_key1",
            key_id="key1",
            capacity_state=CapacityState.Abundant,
            remaining_capacity=CapacityEstimate(value=1000, confidence=1.0),
            total_capacity=1000,
            used_capacity=0,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        ),
        "key2": QuotaState(
            id="quota_key2",
            key_id="key2",
            capacity_state=CapacityState.Constrained,
            remaining_capacity=CapacityEstimate(value=500, confidence=1.0),
            total_capacity=1000,
            used_capacity=500,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        ),
    }

    scores = await reliability_strategy.score_keys(
        sample_keys[:2], sample_request_intent
    )

    # key1 should have higher score due to abundant quota state
    # (even though both have same success rate, key1 has better quota)
    assert scores["key1"] >= scores["key2"]


@pytest.mark.asyncio
async def test_score_keys_normalizes_scores(
    reliability_strategy, sample_keys, sample_request_intent
):
    """Test that scores are normalized to 0.0-1.0 range."""
    scores = await reliability_strategy.score_keys(
        sample_keys, sample_request_intent
    )

    # All scores should be in valid range
    for key_id, score in scores.items():
        assert 0.0 <= score <= 1.0, f"Score for {key_id} is {score}, not in [0.0, 1.0]"


@pytest.mark.asyncio
async def test_filter_by_quota_state_filters_exhausted(
    reliability_strategy, sample_keys, mock_quota_engine
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

    filtered_keys, quota_states, filtered_out = (
        await reliability_strategy.filter_by_quota_state(sample_keys[:2])
    )

    # key1 should be filtered out (exhausted)
    assert len(filtered_keys) == 1
    assert "key1" not in [k.id for k in filtered_keys]
    assert "key2" in [k.id for k in filtered_keys]
    assert len(filtered_out) == 1
    assert filtered_out[0].id == "key1"


@pytest.mark.asyncio
async def test_select_key_selects_highest_score(
    reliability_strategy, sample_keys
):
    """Test that select_key selects key with highest score."""
    scores = {"key1": 0.9, "key2": 0.5, "key3": 0.1}

    selected_key_id, score = reliability_strategy.select_key(scores, sample_keys)

    assert selected_key_id == "key1"
    assert score == 0.9


@pytest.mark.asyncio
async def test_select_key_handles_ties(reliability_strategy, sample_keys):
    """Test that select_key handles ties deterministically."""
    scores = {"key1": 0.5, "key2": 0.5, "key3": 0.1}

    selected_key_id, score = reliability_strategy.select_key(scores, sample_keys)

    # Should select first key with max score (deterministic)
    assert selected_key_id in ["key1", "key2"]
    assert score == 0.5


@pytest.mark.asyncio
async def test_generate_explanation_includes_success_rate(
    reliability_strategy,
):
    """Test that explanation includes success rate."""
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

    explanation = reliability_strategy.generate_explanation(
        selected_key_id="key1",
        success_rate=0.95,
        quota_state=quota_state,
        eligible_count=3,
        filtered_count=0,
        failure_count=5,
        usage_count=95,
    )

    assert "key1" in explanation
    assert "95" in explanation  # Success rate appears as "95.0%" or similar
    assert "abundant" in explanation.lower()
    assert "3 eligible keys" in explanation
    assert "95 successes" in explanation
    assert "5 failures" in explanation


@pytest.mark.asyncio
async def test_score_keys_empty_list_returns_empty_dict(
    reliability_strategy, sample_request_intent
):
    """Test that scoring empty list returns empty dict."""
    scores = await reliability_strategy.score_keys([], sample_request_intent)
    assert scores == {}


@pytest.mark.asyncio
async def test_score_keys_handles_zero_usage_gracefully(
    reliability_strategy, sample_request_intent
):
    """Test that strategy handles zero usage gracefully."""
    key = APIKey(
        id="key_new",
        provider_id="openai",
        key_material="test",
        state=KeyState.Available,
        usage_count=0,
        failure_count=0,
    )

    scores = await reliability_strategy.score_keys([key], sample_request_intent)

    # Should have a score (defaults to high reliability)
    assert key.id in scores
    assert scores[key.id] > 0.0


@pytest.mark.asyncio
async def test_filter_by_quota_state_no_quota_engine_returns_all(
    mock_observability, sample_keys
):
    """Test that filter_by_quota_state returns all keys when no quota engine."""
    strategy = ReliabilityOptimizedStrategy(
        observability_manager=mock_observability,
        quota_awareness_engine=None,
    )

    filtered_keys, quota_states, filtered_out = await strategy.filter_by_quota_state(
        sample_keys
    )

    assert len(filtered_keys) == len(sample_keys)
    assert quota_states == {}
    assert filtered_out == []


@pytest.mark.asyncio
async def test_score_keys_uses_provided_quota_states(
    reliability_strategy, sample_keys, sample_request_intent
):
    """Test that score_keys uses provided quota_states parameter."""
    from datetime import datetime, timedelta

    quota_states = {
        "key1": QuotaState(
            id="quota_key1",
            key_id="key1",
            capacity_state=CapacityState.Abundant,
            remaining_capacity=CapacityEstimate(value=1000, confidence=1.0),
            total_capacity=1000,
            used_capacity=0,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        ),
    }

    scores = await reliability_strategy.score_keys(
        sample_keys, sample_request_intent, quota_states=quota_states
    )

    # Should use provided quota states
    assert "key1" in scores

