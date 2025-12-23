"""Integration tests for successful request routing workflow."""

from datetime import datetime
from decimal import Decimal

import pytest

from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.request_intent import Message, RequestIntent
from apikeyrouter.domain.models.routing_decision import ObjectiveType, RoutingObjective
from apikeyrouter.domain.models.system_response import ResponseMetadata, SystemResponse, TokenUsage
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore
from apikeyrouter.router import ApiKeyRouter


@pytest.fixture
async def api_key_router():
    """Create ApiKeyRouter instance for testing."""
    state_store = InMemoryStateStore(max_decisions=1000, max_transitions=1000)
    return ApiKeyRouter(state_store=state_store)


class MockProviderAdapter(ProviderAdapter):
    """Mock ProviderAdapter for integration testing."""

    def __init__(self, provider_id: str = "openai") -> None:
        """Initialize mock adapter."""
        self.provider_id = provider_id

    async def execute_request(self, intent, key):
        """Execute request - mock implementation."""
        from apikeyrouter.domain.models.cost_estimate import CostEstimate

        return SystemResponse(
            content="Mocked response content",
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


class TestSuccessfulRequestRouting:
    """Tests for successful request routing workflow."""

    @pytest.mark.asyncio
    async def test_full_request_flow_register_keys_route_request_verify_response(
        self, api_key_router, mock_adapter
    ):
        """Test full request flow: register keys → route request → verify response."""
        # Register provider
        await api_key_router.register_provider("openai", mock_adapter)

        # Register keys
        key1 = await api_key_router.register_key(
            key_material="sk-test-key-1",
            provider_id="openai",
            metadata={"account_tier": "pro"},
        )
        key2 = await api_key_router.register_key(
            key_material="sk-test-key-2",
            provider_id="openai",
            metadata={"account_tier": "basic"},
        )

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
            parameters={"provider_id": "openai"},
        )

        # Route request
        response = await api_key_router.route(request_intent, objective="fairness")

        # Verify response
        assert response is not None
        assert response.content == "Mocked response content"
        assert response.key_used in [key1.id, key2.id]
        assert response.metadata.model_used == "gpt-4"
        assert response.metadata.tokens_used is not None
        assert response.metadata.tokens_used.total_tokens == 15

    @pytest.mark.asyncio
    async def test_routing_decision_made_correctly(self, api_key_router, mock_adapter):
        """Test routing decision made correctly."""
        # Register provider and keys
        await api_key_router.register_provider("openai", mock_adapter)
        key1 = await api_key_router.register_key(key_material="sk-test-key-1", provider_id="openai")

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request
        response = await api_key_router.route(
            request_intent, objective=RoutingObjective(primary=ObjectiveType.Cost.value)
        )

        # Verify routing decision was made
        assert response is not None
        assert response.key_used == key1.id
        assert response.request_id is not None
        assert response.metadata.correlation_id is not None

    @pytest.mark.asyncio
    async def test_quota_state_updated_after_request(self, api_key_router, mock_adapter):
        """Test quota state updated after request."""
        # Register provider and key
        await api_key_router.register_provider("openai", mock_adapter)
        key = await api_key_router.register_key(key_material="sk-test-key-1", provider_id="openai")

        # Get initial quota state
        initial_quota = await api_key_router.quota_awareness_engine.get_quota_state(key.id)
        initial_used = initial_quota.used_capacity

        # Create and route request
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )
        await api_key_router.route(request_intent)

        # Verify quota state was updated
        updated_quota = await api_key_router.quota_awareness_engine.get_quota_state(key.id)
        assert updated_quota.used_capacity >= initial_used
        # Should have consumed tokens (15 total tokens from mock response)
        assert updated_quota.used_capacity == initial_used + 15

    @pytest.mark.asyncio
    async def test_cost_recorded(self, api_key_router, mock_adapter):
        """Test cost recorded."""
        # Register provider and key
        await api_key_router.register_provider("openai", mock_adapter)
        await api_key_router.register_key(key_material="sk-test-key-1", provider_id="openai")

        # Create and route request
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )
        response = await api_key_router.route(request_intent)

        # Verify cost is recorded in response
        assert response.cost is not None
        assert response.cost.amount == Decimal("0.001")

    @pytest.mark.asyncio
    async def test_multiple_keys_routing_distribution(self, api_key_router, mock_adapter):
        """Test that routing distributes across multiple keys."""
        # Register provider and multiple keys
        await api_key_router.register_provider("openai", mock_adapter)
        keys = []
        for i in range(3):
            key = await api_key_router.register_key(
                key_material=f"sk-test-key-{i}", provider_id="openai"
            )
            keys.append(key)

        # Route multiple requests
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        used_keys = set()
        for _ in range(5):
            response = await api_key_router.route(request_intent, objective="fairness")
            used_keys.add(response.key_used)

        # With fairness objective, should distribute across keys
        assert len(used_keys) > 1, "Should use multiple keys with fairness objective"

    @pytest.mark.asyncio
    async def test_routing_with_different_objectives(self, api_key_router, mock_adapter):
        """Test routing with different objectives."""
        # Register provider and keys with different metadata
        await api_key_router.register_provider("openai", mock_adapter)
        key1 = await api_key_router.register_key(
            key_material="sk-test-key-1",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.01},
        )
        key2 = await api_key_router.register_key(
            key_material="sk-test-key-2",
            provider_id="openai",
            metadata={"estimated_cost_per_request": 0.02},
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Test cost objective
        response_cost = await api_key_router.route(request_intent, objective="cost")
        assert response_cost.key_used in [key1.id, key2.id]

        # Test reliability objective
        response_reliability = await api_key_router.route(request_intent, objective="reliability")
        assert response_reliability.key_used in [key1.id, key2.id]

        # Test fairness objective
        response_fairness = await api_key_router.route(request_intent, objective="fairness")
        assert response_fairness.key_used in [key1.id, key2.id]
