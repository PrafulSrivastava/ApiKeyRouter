"""Integration tests for cost control and budget enforcement."""

from datetime import datetime
from decimal import Decimal

import pytest

from apikeyrouter.domain.components.cost_controller import CostController
from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.budget import BudgetScope, EnforcementMode
from apikeyrouter.domain.models.quota_state import TimeWindow
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
    """Mock ProviderAdapter for cost control testing."""

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


@pytest.fixture
async def router_with_cost_controller(api_key_router, mock_adapter):
    """Create router with CostController integrated."""

    # Register provider
    await api_key_router.register_provider("openai", mock_adapter)

    # Create CostController
    cost_controller = CostController(
        state_store=api_key_router.state_store,
        observability_manager=api_key_router.observability_manager,
        providers={"openai": mock_adapter},
    )

    # Inject CostController into RoutingEngine
    # Note: This requires accessing private attributes, which is acceptable for integration tests
    api_key_router._routing_engine._cost_controller = cost_controller

    return api_key_router, cost_controller


class TestCostControlAndBudgetEnforcement:
    """Tests for cost control and budget enforcement."""

    @pytest.mark.asyncio
    async def test_budget_check_before_execution(
        self, router_with_cost_controller, mock_adapter
    ):
        """Test budget check before execution."""
        router, cost_controller = router_with_cost_controller

        # Register key
        key = await router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )

        # Create budget
        budget = await cost_controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Soft,
        )
        # Set initial spend to 50.00
        await cost_controller.update_spending(budget.id, Decimal("50.00"))

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Check budget before execution
        cost_estimate = await cost_controller.estimate_request_cost(
            request_intent=request_intent,
            provider_id="openai",
            key_id=key.id,
        )
        budget_result = await cost_controller.check_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
            provider_id="openai",
            key_id=key.id,
        )

        # Verify budget check
        assert budget_result.allowed is True
        assert budget_result.remaining_budget < Decimal("100.00")
        assert budget_result.would_exceed is False

    @pytest.mark.asyncio
    async def test_hard_enforcement_rejects_requests(
        self, router_with_cost_controller, mock_adapter
    ):
        """Test hard enforcement rejects requests."""
        router, cost_controller = router_with_cost_controller

        # Register key
        await router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )

        # Create budget with hard enforcement and low limit
        budget = await cost_controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("0.0001"),  # Very low limit
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Hard,
        )
        # Set initial spend to simulate already at limit
        budget.current_spend = Decimal("0.0001")
        await cost_controller.update_spending(budget.id, Decimal("0.0001"))

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request - should be rejected due to hard enforcement
        from apikeyrouter.domain.components.routing_engine import NoEligibleKeysError

        with pytest.raises(NoEligibleKeysError):
            await router.route(request_intent)

    @pytest.mark.asyncio
    async def test_soft_enforcement_warns_but_allows(
        self, router_with_cost_controller, mock_adapter
    ):
        """Test soft enforcement warns but allows."""
        router, cost_controller = router_with_cost_controller

        # Register key
        key = await router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )

        # Create budget with soft enforcement and low limit
        budget = await cost_controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("0.0001"),  # Very low limit
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Soft,  # Soft enforcement
        )
        # Set initial spend to simulate already at limit
        budget.current_spend = Decimal("0.0001")
        await cost_controller.update_spending(budget.id, Decimal("0.0001"))

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request - should succeed with soft enforcement (but score penalized)
        response = await router.route(request_intent)

        # Verify response succeeded
        assert response is not None
        assert response.key_used == key.id

    @pytest.mark.asyncio
    async def test_cost_reconciliation(
        self, router_with_cost_controller, mock_adapter
    ):
        """Test cost reconciliation."""
        router, cost_controller = router_with_cost_controller

        # Register key
        key = await router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )

        # Create budget
        budget = await cost_controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Soft,
        )

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Estimate cost first (this records it for reconciliation)
        cost_estimate = await cost_controller.estimate_request_cost(
            request_intent=request_intent,
            provider_id="openai",
            key_id=key.id,
        )

        # Record estimated cost for reconciliation
        await cost_controller.record_estimated_cost(
            request_id="test-request-1",
            cost_estimate=cost_estimate,
            provider_id="openai",
            model="gpt-4",
            key_id=key.id,
        )

        # Route request
        response = await router.route(request_intent)

        # Reconcile cost using record_actual_cost
        actual_cost = response.cost.amount if response.cost else Decimal("0.001")
        reconciliation = await cost_controller.record_actual_cost(
            request_id="test-request-1",
            actual_cost=actual_cost,
            provider_id="openai",
            model="gpt-4",
            key_id=key.id,
        )

        # Verify reconciliation was created
        assert reconciliation is not None
        assert reconciliation.estimated_cost == cost_estimate.amount
        assert reconciliation.actual_cost == actual_cost

        # Verify budget was updated (spending should have increased)
        updated_budget = await cost_controller.get_budget(budget.id)
        assert updated_budget is not None
        # Budget spending should have increased due to the request
        assert updated_budget.current_spend >= budget.current_spend

    @pytest.mark.asyncio
    async def test_per_provider_budget_enforcement(
        self, router_with_cost_controller, mock_adapter
    ):
        """Test per-provider budget enforcement."""
        router, cost_controller = router_with_cost_controller

        # Register key
        await router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )

        # Create per-provider budget with hard enforcement
        budget = await cost_controller.create_budget(
            scope=BudgetScope.PerProvider,
            scope_id="openai",
            limit=Decimal("0.0001"),  # Very low limit
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Hard,
        )
        # Set initial spend to simulate already at limit
        budget.current_spend = Decimal("0.0001")
        await cost_controller.update_spending(budget.id, Decimal("0.0001"))

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request - should be rejected
        from apikeyrouter.domain.components.routing_engine import NoEligibleKeysError

        with pytest.raises(NoEligibleKeysError):
            await router.route(request_intent)

    @pytest.mark.asyncio
    async def test_per_key_budget_enforcement(
        self, router_with_cost_controller, mock_adapter
    ):
        """Test per-key budget enforcement."""
        router, cost_controller = router_with_cost_controller

        # Register multiple keys
        key1 = await router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )
        key2 = await router.register_key(
            key_material="sk-test-key-2", provider_id="openai"
        )

        # Create per-key budget for key1 with hard enforcement
        budget = await cost_controller.create_budget(
            scope=BudgetScope.PerKey,
            scope_id=key1.id,
            limit=Decimal("0.0001"),  # Very low limit
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Hard,
        )
        # Set initial spend to simulate already at limit
        budget.current_spend = Decimal("0.0001")
        await cost_controller.update_spending(budget.id, Decimal("0.0001"))

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request - should use key2 (key1 filtered out)
        response = await router.route(request_intent)

        # Verify key2 was used (not key1)
        assert response.key_used == key2.id

