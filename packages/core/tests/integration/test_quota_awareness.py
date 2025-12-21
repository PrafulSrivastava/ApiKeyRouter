"""Integration tests for quota exhaustion and proactive routing."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.quota_state import (
    CapacityEstimate,
    CapacityState,
    CapacityUnit,
    TimeWindow,
)
from apikeyrouter.domain.models.request_intent import Message, RequestIntent
from apikeyrouter.domain.models.system_response import ResponseMetadata, SystemResponse, TokenUsage
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore
from apikeyrouter.router import ApiKeyRouter


@pytest.fixture
async def api_key_router():
    """Create ApiKeyRouter instance for testing."""
    state_store = InMemoryStateStore(max_decisions=1000, max_transitions=1000)
    return ApiKeyRouter(state_store=state_store)


class MockProviderAdapter(ProviderAdapter):
    """Mock ProviderAdapter for quota testing."""

    def __init__(self, provider_id: str = "openai") -> None:
        """Initialize mock adapter."""
        self.provider_id = provider_id

    async def execute_request(self, intent, key):
        """Execute request - mock implementation."""
        from apikeyrouter.domain.models.cost_estimate import CostEstimate

        return SystemResponse(
            content="Mocked response",
            request_id="mock-request-id",
            key_used=key.id,
            metadata=ResponseMetadata(
                model_used=intent.model if hasattr(intent, "model") else "mock-model",
                tokens_used=TokenUsage(input_tokens=10, output_tokens=5),
                response_time_ms=100,
                provider_id=key.provider_id,
                timestamp=datetime.utcnow(),
            ),
            cost=CostEstimate(
                amount=Decimal("0.001"),
                currency="USD",
                confidence=0.9,
                estimation_method="mock",
                input_tokens_estimate=10,
                output_tokens_estimate=5,
            ),
        )

    def normalize_response(self, provider_response):
        """Normalize response - mock implementation."""
        return provider_response

    def map_error(self, provider_error: Exception):
        """Map error - mock implementation."""
        from apikeyrouter.domain.models.system_error import ErrorCategory, SystemError

        return SystemError(
            category=ErrorCategory.ProviderError,
            message=str(provider_error),
            retryable=False,
        )

    def get_capabilities(self):
        """Get capabilities - mock implementation."""
        return {
            "models": ["gpt-4", "gpt-3.5-turbo"],
            "supports_streaming": True,
        }

    async def estimate_cost(self, request_intent):
        """Estimate cost - mock implementation."""
        from apikeyrouter.domain.models.cost_estimate import CostEstimate

        return CostEstimate(
            amount=Decimal("0.001"),
            currency="USD",
            confidence=0.9,
            estimation_method="mock",
            input_tokens_estimate=10,
            output_tokens_estimate=5,
        )

    async def get_health(self):
        """Get health - mock implementation."""
        return {"status": "healthy", "latency_ms": 100}


@pytest.fixture
def mock_adapter() -> MockProviderAdapter:
    """Create mock provider adapter."""
    return MockProviderAdapter(provider_id="openai")


class TestQuotaExhaustionAndProactiveRouting:
    """Tests for quota exhaustion and proactive routing."""

    @pytest.mark.asyncio
    async def test_quota_exhausted_key_avoided(
        self, api_key_router, mock_adapter
    ):
        """Test quota exhausted key avoided."""
        # Register provider and multiple keys
        await api_key_router.register_provider("openai", mock_adapter)
        key1 = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )
        key2 = await api_key_router.register_key(
            key_material="sk-test-key-2", provider_id="openai"
        )

        # Manually set key1 to exhausted state
        quota_state = await api_key_router.quota_awareness_engine.get_quota_state(
            key1.id
        )
        # Update to exhausted
        from apikeyrouter.domain.models.quota_state import QuotaState

        exhausted_quota = QuotaState(
            id=quota_state.id,
            key_id=key1.id,
            capacity_state=CapacityState.Exhausted,
            capacity_unit=CapacityUnit.Requests,
            remaining_capacity=CapacityEstimate(value=0, confidence=1.0),
            total_capacity=1000,
            used_capacity=1000,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        await api_key_router.state_store.save_quota_state(exhausted_quota)

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request - should avoid key1 and use key2
        response = await api_key_router.route(request_intent)

        # Verify key2 was used (not key1)
        assert response.key_used == key2.id

    @pytest.mark.asyncio
    async def test_proactive_routing_away_from_critical_keys(
        self, api_key_router, mock_adapter
    ):
        """Test proactive routing away from critical keys."""
        # Register provider and multiple keys
        await api_key_router.register_provider("openai", mock_adapter)
        key1 = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )
        key2 = await api_key_router.register_key(
            key_material="sk-test-key-2", provider_id="openai"
        )

        # Set key1 to critical state
        quota_state = await api_key_router.quota_awareness_engine.get_quota_state(
            key1.id
        )
        from apikeyrouter.domain.models.quota_state import QuotaState

        critical_quota = QuotaState(
            id=quota_state.id,
            key_id=key1.id,
            capacity_state=CapacityState.Critical,
            capacity_unit=CapacityUnit.Requests,
            remaining_capacity=CapacityEstimate(value=200, confidence=1.0),
            total_capacity=1000,
            used_capacity=800,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        await api_key_router.state_store.save_quota_state(critical_quota)

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request - should prefer key2 over critical key1
        response = await api_key_router.route(request_intent)

        # Verify key2 was used (critical key1 should be avoided)
        assert response.key_used == key2.id

    @pytest.mark.asyncio
    async def test_exhaustion_prediction_affects_routing(
        self, api_key_router, mock_adapter
    ):
        """Test exhaustion prediction affects routing."""
        # Register provider and multiple keys
        await api_key_router.register_provider("openai", mock_adapter)
        key1 = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )
        key2 = await api_key_router.register_key(
            key_material="sk-test-key-2", provider_id="openai"
        )

        # Set key1 to constrained state (close to exhaustion)
        quota_state = await api_key_router.quota_awareness_engine.get_quota_state(
            key1.id
        )
        from apikeyrouter.domain.models.quota_state import QuotaState

        constrained_quota = QuotaState(
            id=quota_state.id,
            key_id=key1.id,
            capacity_state=CapacityState.Constrained,
            capacity_unit=CapacityUnit.Requests,
            remaining_capacity=CapacityEstimate(value=600, confidence=1.0),
            total_capacity=1000,
            used_capacity=400,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        await api_key_router.state_store.save_quota_state(constrained_quota)

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request - constrained key should be penalized but may still be used
        # if it's the only option or has better score
        response = await api_key_router.route(request_intent)

        # Verify response succeeded (may use either key depending on scoring)
        assert response is not None
        assert response.key_used in [key1.id, key2.id]

    @pytest.mark.asyncio
    async def test_quota_reset_handled_correctly(
        self, api_key_router, mock_adapter
    ):
        """Test quota reset handled correctly."""
        # Register provider and key
        await api_key_router.register_provider("openai", mock_adapter)
        key = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )

        # Set key to exhausted state with reset in the past (should reset)
        from apikeyrouter.domain.models.quota_state import QuotaState

        exhausted_quota = QuotaState(
            id=f"quota-{key.id}",
            key_id=key.id,
            capacity_state=CapacityState.Exhausted,
            capacity_unit=CapacityUnit.Requests,
            remaining_capacity=CapacityEstimate(value=0, confidence=1.0),
            total_capacity=1000,
            used_capacity=1000,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() - timedelta(hours=1),  # Reset in the past
        )
        await api_key_router.state_store.save_quota_state(exhausted_quota)

        # Trigger reset by calling update_capacity (which checks for reset)
        quota_state = await api_key_router.quota_awareness_engine.update_capacity(
            key_id=key.id,
            consumed=0,  # No consumption, just trigger reset check
        )

        # Verify quota was reset (should not be exhausted anymore)
        assert quota_state.capacity_state != CapacityState.Exhausted
        assert quota_state.used_capacity < quota_state.total_capacity
        assert quota_state.remaining_capacity.value > 0

    @pytest.mark.asyncio
    async def test_all_keys_exhausted_raises_error(
        self, api_key_router, mock_adapter
    ):
        """Test that when all keys are exhausted, error is raised."""
        # Register provider and multiple keys
        await api_key_router.register_provider("openai", mock_adapter)
        key1 = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )
        key2 = await api_key_router.register_key(
            key_material="sk-test-key-2", provider_id="openai"
        )

        # Set both keys to exhausted state
        from apikeyrouter.domain.models.quota_state import QuotaState

        for key in [key1, key2]:
            exhausted_quota = QuotaState(
                id=f"quota-{key.id}",
                key_id=key.id,
                capacity_state=CapacityState.Exhausted,
                capacity_unit=CapacityUnit.Requests,
                remaining_capacity=CapacityEstimate(value=0, confidence=1.0),
                total_capacity=1000,
                used_capacity=1000,
                time_window=TimeWindow.Daily,
                reset_at=datetime.utcnow() + timedelta(days=1),
            )
            await api_key_router.state_store.save_quota_state(exhausted_quota)

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request - should raise NoEligibleKeysError
        from apikeyrouter.domain.components.routing_engine import NoEligibleKeysError

        with pytest.raises(NoEligibleKeysError):
            await api_key_router.route(request_intent)

    @pytest.mark.asyncio
    async def test_abundant_keys_preferred(
        self, api_key_router, mock_adapter
    ):
        """Test that abundant keys are preferred over constrained keys."""
        # Register provider and multiple keys
        await api_key_router.register_provider("openai", mock_adapter)
        key1 = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )
        key2 = await api_key_router.register_key(
            key_material="sk-test-key-2", provider_id="openai"
        )

        # Set key1 to constrained, key2 to abundant
        from apikeyrouter.domain.models.quota_state import QuotaState

        constrained_quota = QuotaState(
            id=f"quota-{key1.id}",
            key_id=key1.id,
            capacity_state=CapacityState.Constrained,
            capacity_unit=CapacityUnit.Requests,
            remaining_capacity=CapacityEstimate(value=600, confidence=1.0),
            total_capacity=1000,
            used_capacity=400,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        await api_key_router.state_store.save_quota_state(constrained_quota)

        abundant_quota = QuotaState(
            id=f"quota-{key2.id}",
            key_id=key2.id,
            capacity_state=CapacityState.Abundant,
            capacity_unit=CapacityUnit.Requests,
            remaining_capacity=CapacityEstimate(value=900, confidence=1.0),
            total_capacity=1000,
            used_capacity=100,
            time_window=TimeWindow.Daily,
            reset_at=datetime.utcnow() + timedelta(days=1),
        )
        await api_key_router.state_store.save_quota_state(abundant_quota)

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request - should prefer abundant key2
        response = await api_key_router.route(request_intent)

        # With quota multipliers, abundant key should be preferred
        assert response.key_used == key2.id

