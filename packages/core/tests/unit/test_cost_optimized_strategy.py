"""Tests for CostOptimizedStrategy."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from apikeyrouter.domain.components.routing_strategies.cost_optimized import (
    CostOptimizedStrategy,
)
from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.domain.models.cost_estimate import CostEstimate
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


class MockProviderAdapter(ProviderAdapter):
    """Mock ProviderAdapter for testing."""

    def __init__(self, cost_estimate: CostEstimate | None = None) -> None:
        """Initialize mock adapter."""
        self.cost_estimate = cost_estimate or CostEstimate(
            amount=Decimal("0.01"),
            currency="USD",
            confidence=0.8,
            estimation_method="mock",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

    async def execute_request(self, intent, key):
        """Mock execute_request."""
        pass

    def normalize_response(self, provider_response):
        """Mock normalize_response."""
        pass

    def map_error(self, provider_error):
        """Mock map_error."""
        pass

    def get_capabilities(self):
        """Mock get_capabilities."""
        pass

    async def estimate_cost(self, request_intent):
        """Mock estimate_cost."""
        return self.cost_estimate

    async def get_health(self):
        """Mock get_health."""
        pass


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
def cost_strategy(mock_observability, mock_quota_engine) -> CostOptimizedStrategy:
    """Create CostOptimizedStrategy instance."""
    return CostOptimizedStrategy(
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
    import os

    from cryptography.fernet import Fernet

    # Ensure encryption key is set for this fixture
    if "API_KEY_ENCRYPTION_KEY" not in os.environ:
        key = Fernet.generate_key()
        os.environ["API_KEY_ENCRYPTION_KEY"] = key.decode()

    from apikeyrouter.domain.models.api_key import APIKey

    return [
        APIKey(
            id="key1",
            provider_id="openai",
            key_material="test_key_material_1",
            state=KeyState.Available,
            metadata={"estimated_cost_per_request": 0.01},
        ),
        APIKey(
            id="key2",
            provider_id="openai",
            key_material="test_key_material_2",
            state=KeyState.Available,
            metadata={"estimated_cost_per_request": 0.02},
        ),
        APIKey(
            id="key3",
            provider_id="openai",
            key_material="test_key_material_3",
            state=KeyState.Available,
            metadata={"estimated_cost_per_request": 0.03},
        ),
    ]


@pytest.mark.asyncio
async def test_score_keys_by_cost_lower_cost_higher_score(
    cost_strategy, sample_keys, sample_request_intent
):
    """Test that lower cost results in higher score."""
    scores = await cost_strategy.score_keys(sample_keys, sample_request_intent)

    # key1 has lowest cost (0.01), should have highest score
    # key3 has highest cost (0.03), should have lowest score
    assert scores["key1"] > scores["key2"]
    assert scores["key2"] > scores["key3"]
    assert scores["key1"] == 1.0  # Lowest cost = highest score (normalized)


@pytest.mark.asyncio
async def test_score_keys_uses_provider_adapter_when_available(
    cost_strategy, sample_keys, sample_request_intent
):
    """Test that strategy uses ProviderAdapter estimate_cost when available."""
    # Create adapters with different costs
    providers = {
        "openai": MockProviderAdapter(
            cost_estimate=CostEstimate(
                amount=Decimal("0.005"),
                currency="USD",
                confidence=0.8,
                estimation_method="test",
                input_tokens_estimate=100,
                output_tokens_estimate=50,
            )
        )
    }

    scores = await cost_strategy.score_keys(sample_keys, sample_request_intent, providers=providers)

    # All keys should use the adapter's cost estimate (0.005)
    # So all should have equal scores
    assert all(score == 1.0 for score in scores.values())


@pytest.mark.asyncio
async def test_score_keys_fallback_to_metadata(cost_strategy, sample_keys, sample_request_intent):
    """Test that strategy falls back to metadata when adapter unavailable."""
    # No providers provided, should use metadata
    scores = await cost_strategy.score_keys(sample_keys, sample_request_intent)

    # Should use metadata costs
    assert scores["key1"] > scores["key2"]
    assert scores["key2"] > scores["key3"]


@pytest.mark.asyncio
async def test_score_keys_normalizes_scores(cost_strategy, sample_keys, sample_request_intent):
    """Test that scores are normalized to 0.0-1.0 range."""
    scores = await cost_strategy.score_keys(sample_keys, sample_request_intent)

    # All scores should be in valid range
    for key_id, score in scores.items():
        assert 0.0 <= score <= 1.0, f"Score for {key_id} is {score}, not in [0.0, 1.0]"


@pytest.mark.asyncio
async def test_filter_by_quota_state_filters_exhausted(
    cost_strategy, sample_keys, mock_quota_engine
):
    """Test that exhausted keys are filtered out."""
    from datetime import datetime, timedelta

    # Set up quota states: key1 exhausted, key2 abundant, key3 constrained
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
        "key3": QuotaState(
            id="quota_key3",
            key_id="key3",
            capacity_state=CapacityState.Constrained,
            remaining_capacity=CapacityEstimate(value=500, confidence=1.0),
            total_capacity=1000,
            used_capacity=500,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        ),
    }

    filtered_keys, quota_states, filtered_out = await cost_strategy.filter_by_quota_state(
        sample_keys
    )

    # key1 should be filtered out (exhausted)
    assert len(filtered_keys) == 2
    assert "key1" not in [k.id for k in filtered_keys]
    assert "key2" in [k.id for k in filtered_keys]
    assert "key3" in [k.id for k in filtered_keys]
    assert len(filtered_out) == 1
    assert filtered_out[0].id == "key1"


@pytest.mark.asyncio
async def test_apply_quota_multipliers_boosts_abundant(cost_strategy, sample_keys):
    """Test that abundant keys get score boost."""
    from datetime import datetime, timedelta

    scores = {"key1": 0.5, "key2": 0.5, "key3": 0.5}

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
        "key3": QuotaState(
            id="quota_key3",
            key_id="key3",
            capacity_state=CapacityState.Critical,
            remaining_capacity=CapacityEstimate(value=200, confidence=1.0),
            total_capacity=1000,
            used_capacity=800,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        ),
    }

    adjusted_scores = await cost_strategy.apply_quota_multipliers(scores, quota_states)

    # key1 (abundant) should have higher score (boosted by 20%)
    assert adjusted_scores["key1"] > scores["key1"]
    assert adjusted_scores["key1"] == pytest.approx(0.5 * 1.2, abs=0.01)

    # key2 (constrained) should have lower score (penalized by 15%)
    assert adjusted_scores["key2"] < scores["key2"]
    assert adjusted_scores["key2"] == pytest.approx(0.5 * 0.85, abs=0.01)

    # key3 (critical) should have lower score (penalized by 30%)
    assert adjusted_scores["key3"] < scores["key3"]
    assert adjusted_scores["key3"] == pytest.approx(0.5 * 0.70, abs=0.01)


@pytest.mark.asyncio
async def test_select_key_selects_highest_score(cost_strategy, sample_keys):
    """Test that select_key selects key with highest score."""
    scores = {"key1": 0.9, "key2": 0.5, "key3": 0.1}

    selected_key_id, score = cost_strategy.select_key(scores, sample_keys)

    assert selected_key_id == "key1"
    assert score == 0.9


@pytest.mark.asyncio
async def test_select_key_handles_ties(cost_strategy, sample_keys):
    """Test that select_key handles ties deterministically."""
    scores = {"key1": 0.5, "key2": 0.5, "key3": 0.1}

    selected_key_id, score = cost_strategy.select_key(scores, sample_keys)

    # Should select first key with max score (deterministic)
    assert selected_key_id in ["key1", "key2"]
    assert score == 0.5


@pytest.mark.asyncio
async def test_generate_explanation_includes_cost(cost_strategy, sample_request_intent):
    """Test that explanation includes cost information."""
    from datetime import datetime, timedelta

    cost_estimate = CostEstimate(
        amount=Decimal("0.01"),
        currency="USD",
        confidence=0.8,
        estimation_method="test",
        input_tokens_estimate=100,
        output_tokens_estimate=50,
    )

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

    explanation = cost_strategy.generate_explanation(
        selected_key_id="key1",
        cost_estimate=cost_estimate,
        quota_state=quota_state,
        eligible_count=3,
        filtered_count=0,
    )

    assert "key1" in explanation
    assert "0.01" in explanation or "$0.01" in explanation
    assert "abundant" in explanation.lower()
    assert "3 eligible keys" in explanation


@pytest.mark.asyncio
async def test_generate_explanation_includes_alternatives(cost_strategy, sample_request_intent):
    """Test that explanation includes cost comparison with alternatives."""

    cost_estimate = CostEstimate(
        amount=Decimal("0.01"),
        currency="USD",
        confidence=0.8,
        estimation_method="test",
        input_tokens_estimate=100,
        output_tokens_estimate=50,
    )

    alternative_costs = {
        "key1": Decimal("0.01"),
        "key2": Decimal("0.02"),
        "key3": Decimal("0.03"),
    }

    explanation = cost_strategy.generate_explanation(
        selected_key_id="key1",
        cost_estimate=cost_estimate,
        quota_state=None,
        eligible_count=3,
        filtered_count=0,
        alternative_costs=alternative_costs,
    )

    assert "saves" in explanation.lower() or "vs next cheapest" in explanation.lower()


@pytest.mark.asyncio
async def test_score_keys_empty_list_returns_empty_dict(cost_strategy, sample_request_intent):
    """Test that scoring empty list returns empty dict."""
    scores = await cost_strategy.score_keys([], sample_request_intent)
    assert scores == {}


@pytest.mark.asyncio
async def test_score_keys_equal_costs_returns_equal_scores(
    cost_strategy, sample_keys, sample_request_intent
):
    """Test that keys with equal costs get equal scores."""
    # Set all keys to same cost in metadata
    for key in sample_keys:
        key.metadata["estimated_cost_per_request"] = 0.01

    scores = await cost_strategy.score_keys(sample_keys, sample_request_intent)

    # All scores should be equal (1.0)
    assert all(score == 1.0 for score in scores.values())


@pytest.mark.asyncio
async def test_filter_by_quota_state_no_quota_engine_returns_all(mock_observability, sample_keys):
    """Test that filter_by_quota_state returns all keys when no quota engine."""
    strategy = CostOptimizedStrategy(
        observability_manager=mock_observability,
        quota_awareness_engine=None,
    )

    filtered_keys, quota_states, filtered_out = await strategy.filter_by_quota_state(sample_keys)

    assert len(filtered_keys) == len(sample_keys)
    assert quota_states == {}
    assert filtered_out == []
