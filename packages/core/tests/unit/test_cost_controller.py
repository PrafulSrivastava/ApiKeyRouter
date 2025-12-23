"""Tests for CostController component."""

from decimal import Decimal

import pytest

from apikeyrouter.domain.components.cost_controller import BudgetExceededError, CostController
from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.interfaces.state_store import StateStore
from apikeyrouter.domain.models.budget import Budget, BudgetScope, EnforcementMode
from apikeyrouter.domain.models.cost_estimate import CostEstimate
from apikeyrouter.domain.models.quota_state import TimeWindow
from apikeyrouter.domain.models.request_intent import Message, RequestIntent
from apikeyrouter.domain.models.system_error import ErrorCategory, SystemError


class MockStateStore(StateStore):
    """Mock StateStore for testing."""

    def __init__(self) -> None:
        """Initialize mock store."""
        self._budgets: dict[str, Budget] = {}

    async def save_key(self, key) -> None:
        """Save key to mock store."""
        pass

    async def get_key(self, key_id: str):
        """Get key from mock store."""
        return None

    async def list_keys(self, provider_id: str | None = None) -> list:
        """List keys from mock store."""
        return []

    async def save_quota_state(self, state) -> None:
        """Save quota state to mock store."""
        pass

    async def get_quota_state(self, key_id: str):
        """Get quota state from mock store."""
        return None

    async def save_routing_decision(self, decision) -> None:
        """Save routing decision to mock store."""
        pass

    async def save_state_transition(self, transition) -> None:
        """Save state transition to mock store."""
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
        self.events.append(
            {
                "event_type": event_type,
                "payload": payload,
                "metadata": metadata or {},
            }
        )

    async def log(
        self,
        level: str,
        message: str,
        context: dict | None = None,
    ) -> None:
        """Log message to mock store."""
        self.logs.append(
            {
                "level": level,
                "message": message,
                "context": context or {},
            }
        )


class MockProviderAdapter(ProviderAdapter):
    """Mock ProviderAdapter for testing."""

    def __init__(self, provider_id: str = "openai") -> None:
        """Initialize mock adapter."""
        self.provider_id = provider_id
        self.estimate_cost_result: CostEstimate | None = None
        self.estimate_cost_error: Exception | None = None

    async def execute_request(self, intent, key):
        """Execute request (not used in cost estimation tests)."""
        raise NotImplementedError

    def normalize_response(self, provider_response):
        """Normalize response (not used in cost estimation tests)."""
        raise NotImplementedError

    def map_error(self, provider_error: Exception):
        """Map error (not used in cost estimation tests)."""
        raise NotImplementedError

    def get_capabilities(self):
        """Get capabilities (not used in cost estimation tests)."""
        raise NotImplementedError

    async def estimate_cost(self, request_intent: RequestIntent) -> CostEstimate:
        """Estimate cost for request."""
        if self.estimate_cost_error:
            raise self.estimate_cost_error
        if self.estimate_cost_result:
            return self.estimate_cost_result

        # Default cost estimate
        return CostEstimate(
            amount=Decimal("0.0025"),
            currency="USD",
            confidence=0.8,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

    async def get_health(self):
        """Get health (not used in cost estimation tests)."""
        raise NotImplementedError


class TestCostControllerInitialization:
    """Tests for CostController initialization."""

    @pytest.mark.asyncio
    async def test_initializes_with_dependencies(self) -> None:
        """Test that CostController initializes with required dependencies."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        assert controller._state_store is state_store
        assert controller._observability is observability
        assert controller._providers == {}

    @pytest.mark.asyncio
    async def test_initializes_with_providers(self) -> None:
        """Test that CostController initializes with providers dict."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()
        adapter = MockProviderAdapter()
        providers = {"openai": adapter}

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
            providers=providers,
        )

        assert controller._providers == providers
        assert controller._providers["openai"] is adapter


class TestCostControllerEstimateRequestCost:
    """Tests for estimate_request_cost method."""

    @pytest.mark.asyncio
    async def test_estimate_request_cost_success(self) -> None:
        """Test successful cost estimation."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()
        adapter = MockProviderAdapter()
        adapter.estimate_cost_result = CostEstimate(
            amount=Decimal("0.005"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=150,
            output_tokens_estimate=100,
        )

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
            providers={"openai": adapter},
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
            parameters={"max_tokens": 100},
        )

        estimate = await controller.estimate_request_cost(
            request_intent=request_intent,
            provider_id="openai",
            key_id="key1",
        )

        assert estimate.amount == Decimal("0.005")
        assert estimate.currency == "USD"
        assert estimate.confidence == 0.85
        assert estimate.input_tokens_estimate == 150
        assert estimate.output_tokens_estimate == 100

        # Verify event was emitted
        assert len(observability.events) == 1
        event = observability.events[0]
        assert event["event_type"] == "cost_estimated"
        assert event["payload"]["provider_id"] == "openai"
        assert event["payload"]["key_id"] == "key1"
        assert event["payload"]["model"] == "gpt-4"
        assert event["payload"]["estimated_cost"] == 0.005

    @pytest.mark.asyncio
    async def test_estimate_request_cost_missing_provider(self) -> None:
        """Test cost estimation fails when provider not found."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
            providers={},
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        with pytest.raises(ValueError, match="Provider adapter not found"):
            await controller.estimate_request_cost(
                request_intent=request_intent,
                provider_id="openai",
                key_id="key1",
            )

        # Verify error was logged
        assert len(observability.logs) == 1
        log = observability.logs[0]
        assert log["level"] == "ERROR"
        assert "Provider adapter not found" in log["message"]

    @pytest.mark.asyncio
    async def test_estimate_request_cost_adapter_error(self) -> None:
        """Test cost estimation handles adapter errors."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()
        adapter = MockProviderAdapter()
        adapter.estimate_cost_error = SystemError(
            category=ErrorCategory.ValidationError,
            message="Unknown model for cost estimation",
            provider_code="unknown_model",
            retryable=False,
        )

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
            providers={"openai": adapter},
        )

        request_intent = RequestIntent(
            model="unknown-model",
            messages=[Message(role="user", content="Hello!")],
        )

        with pytest.raises(SystemError) as exc_info:
            await controller.estimate_request_cost(
                request_intent=request_intent,
                provider_id="openai",
                key_id="key1",
            )

        assert exc_info.value.category == ErrorCategory.ValidationError
        assert "Unknown model for cost estimation" in exc_info.value.message

        # Verify error was logged
        assert len(observability.logs) == 1
        log = observability.logs[0]
        assert log["level"] == "ERROR"
        assert "Cost estimation failed" in log["message"]

    @pytest.mark.asyncio
    async def test_estimate_request_cost_generic_exception(self) -> None:
        """Test cost estimation converts generic exceptions to SystemError."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()
        adapter = MockProviderAdapter()
        adapter.estimate_cost_error = ValueError("Unexpected error")

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
            providers={"openai": adapter},
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        with pytest.raises(SystemError) as exc_info:
            await controller.estimate_request_cost(
                request_intent=request_intent,
                provider_id="openai",
                key_id="key1",
            )

        assert exc_info.value.category == ErrorCategory.ValidationError
        assert "Cost estimation failed" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_estimate_request_cost_different_models(self) -> None:
        """Test cost estimation with different models (variable pricing)."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        # Mock adapter for gpt-4 (higher cost)
        adapter_gpt4 = MockProviderAdapter()
        adapter_gpt4.estimate_cost_result = CostEstimate(
            amount=Decimal("0.03"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=1000,
            output_tokens_estimate=500,
        )

        # Mock adapter for gpt-3.5-turbo (lower cost)
        adapter_gpt35 = MockProviderAdapter()
        adapter_gpt35.estimate_cost_result = CostEstimate(
            amount=Decimal("0.002"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=1000,
            output_tokens_estimate=500,
        )

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
            providers={"openai": adapter_gpt4},
        )

        # Test gpt-4
        intent_gpt4 = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )
        estimate_gpt4 = await controller.estimate_request_cost(
            request_intent=intent_gpt4,
            provider_id="openai",
            key_id="key1",
        )
        assert estimate_gpt4.amount == Decimal("0.03")

        # Test gpt-3.5-turbo (switch adapter)
        controller._providers["openai"] = adapter_gpt35
        intent_gpt35 = RequestIntent(
            model="gpt-3.5-turbo",
            messages=[Message(role="user", content="Hello!")],
        )
        estimate_gpt35 = await controller.estimate_request_cost(
            request_intent=intent_gpt35,
            provider_id="openai",
            key_id="key1",
        )
        assert estimate_gpt35.amount == Decimal("0.002")

        # Verify both events were emitted
        assert len(observability.events) == 2
        assert observability.events[0]["payload"]["model"] == "gpt-4"
        assert observability.events[1]["payload"]["model"] == "gpt-3.5-turbo"

    @pytest.mark.asyncio
    async def test_estimate_request_cost_confidence_levels(self) -> None:
        """Test cost estimation returns proper confidence levels."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()
        adapter = MockProviderAdapter()

        # High confidence (with max_tokens)
        adapter.estimate_cost_result = CostEstimate(
            amount=Decimal("0.005"),
            currency="USD",
            confidence=0.85,  # High confidence when max_tokens specified
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
            providers={"openai": adapter},
        )

        # With max_tokens (higher confidence)
        intent_with_max = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
            parameters={"max_tokens": 100},
        )
        estimate_with_max = await controller.estimate_request_cost(
            request_intent=intent_with_max,
            provider_id="openai",
            key_id="key1",
        )
        assert estimate_with_max.confidence == 0.85

        # Without max_tokens (adapter should return lower confidence)
        adapter.estimate_cost_result = CostEstimate(
            amount=Decimal("0.005"),
            currency="USD",
            confidence=0.7,  # Medium confidence when max_tokens not specified
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=500,  # Default estimate
        )

        intent_without_max = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )
        estimate_without_max = await controller.estimate_request_cost(
            request_intent=intent_without_max,
            provider_id="openai",
            key_id="key1",
        )
        assert estimate_without_max.confidence == 0.7

    @pytest.mark.asyncio
    async def test_estimate_request_cost_emits_event_with_metadata(self) -> None:
        """Test that cost estimation emits event with proper metadata."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()
        adapter = MockProviderAdapter()
        adapter.estimate_cost_result = CostEstimate(
            amount=Decimal("0.005"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
            providers={"openai": adapter},
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )
        # Add request_id to intent if supported
        if hasattr(request_intent, "request_id"):
            request_intent.request_id = "req-123"

        await controller.estimate_request_cost(
            request_intent=request_intent,
            provider_id="openai",
            key_id="key1",
        )

        # Verify event structure
        assert len(observability.events) == 1
        event = observability.events[0]
        assert event["event_type"] == "cost_estimated"
        assert "provider_id" in event["payload"]
        assert "key_id" in event["payload"]
        assert "model" in event["payload"]
        assert "estimated_cost" in event["payload"]
        assert "currency" in event["payload"]
        assert "confidence" in event["payload"]
        assert "input_tokens_estimate" in event["payload"]
        assert "output_tokens_estimate" in event["payload"]
        assert "metadata" in event


class TestCostControllerBudgetManagement:
    """Tests for budget management methods."""

    @pytest.mark.asyncio
    async def test_create_budget_global(self) -> None:
        """Test creating a global budget."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )

        assert budget.scope == BudgetScope.Global
        assert budget.scope_id is None
        assert budget.limit_amount == Decimal("100.00")
        assert budget.current_spend == Decimal("0.00")
        assert budget.period == TimeWindow.Daily
        assert budget.enforcement_mode == EnforcementMode.Hard
        assert budget.remaining_budget == Decimal("100.00")
        assert not budget.is_exceeded

        # Verify event was emitted
        assert len(observability.events) == 1
        assert observability.events[0]["event_type"] == "budget_created"

    @pytest.mark.asyncio
    async def test_create_budget_per_provider(self) -> None:
        """Test creating a per-provider budget."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        budget = await controller.create_budget(
            scope=BudgetScope.PerProvider,
            limit=Decimal("50.00"),
            period=TimeWindow.Monthly,
            scope_id="openai",
            enforcement_mode=EnforcementMode.Soft,
        )

        assert budget.scope == BudgetScope.PerProvider
        assert budget.scope_id == "openai"
        assert budget.limit_amount == Decimal("50.00")
        assert budget.period == TimeWindow.Monthly
        assert budget.enforcement_mode == EnforcementMode.Soft

    @pytest.mark.asyncio
    async def test_create_budget_requires_scope_id(self) -> None:
        """Test that non-global budgets require scope_id."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        with pytest.raises(ValueError, match="scope_id is required"):
            await controller.create_budget(
                scope=BudgetScope.PerProvider,
                limit=Decimal("50.00"),
                period=TimeWindow.Daily,
            )

    @pytest.mark.asyncio
    async def test_update_spending(self) -> None:
        """Test updating spending for a budget."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create budget
        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )

        # Update spending
        updated_budget = await controller.update_spending(
            budget_id=budget.id,
            amount=Decimal("25.50"),
        )

        assert updated_budget.current_spend == Decimal("25.50")
        assert updated_budget.remaining_budget == Decimal("74.50")
        assert updated_budget.utilization_percentage == 25.5

        # Verify event was emitted
        assert len(observability.events) == 2
        assert observability.events[1]["event_type"] == "budget_spending_updated"
        assert observability.events[1]["payload"]["amount"] == 25.5

    @pytest.mark.asyncio
    async def test_update_spending_multiple_times(self) -> None:
        """Test updating spending multiple times."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )

        # Update spending multiple times
        budget = await controller.update_spending(budget.id, Decimal("10.00"))
        assert budget.current_spend == Decimal("10.00")

        budget = await controller.update_spending(budget.id, Decimal("20.00"))
        assert budget.current_spend == Decimal("30.00")

        budget = await controller.update_spending(budget.id, Decimal("15.00"))
        assert budget.current_spend == Decimal("45.00")
        assert budget.remaining_budget == Decimal("55.00")

    @pytest.mark.asyncio
    async def test_update_spending_negative_amount(self) -> None:
        """Test that negative spending amounts are rejected."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )

        with pytest.raises(ValueError, match="Spending amount cannot be negative"):
            await controller.update_spending(budget.id, Decimal("-10.00"))

    @pytest.mark.asyncio
    async def test_update_spending_budget_not_found(self) -> None:
        """Test updating spending for non-existent budget."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        with pytest.raises(ValueError, match="Budget not found"):
            await controller.update_spending("nonexistent", Decimal("10.00"))

    @pytest.mark.asyncio
    async def test_budget_exceeded(self) -> None:
        """Test budget exceeded detection."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )

        # Spend exactly the limit
        budget = await controller.update_spending(budget.id, Decimal("100.00"))
        assert budget.is_exceeded
        assert budget.remaining_budget == Decimal("0.00")

        # Verify warning was logged
        warning_logs = [log for log in observability.logs if log["level"] == "WARNING"]
        assert len(warning_logs) == 1
        assert "Budget exceeded" in warning_logs[0]["message"]

    @pytest.mark.asyncio
    async def test_get_budget(self) -> None:
        """Test getting budget by ID."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        created_budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )

        retrieved_budget = await controller.get_budget(created_budget.id)
        assert retrieved_budget is not None
        assert retrieved_budget.id == created_budget.id
        assert retrieved_budget.limit_amount == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_list_budgets(self) -> None:
        """Test listing budgets."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create multiple budgets
        budget1 = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )
        budget2 = await controller.create_budget(
            scope=BudgetScope.PerProvider,
            limit=Decimal("50.00"),
            period=TimeWindow.Monthly,
            scope_id="openai",
        )
        await controller.create_budget(
            scope=BudgetScope.PerProvider,
            limit=Decimal("30.00"),
            period=TimeWindow.Daily,
            scope_id="anthropic",
        )

        # List all budgets
        all_budgets = await controller.list_budgets()
        assert len(all_budgets) == 3

        # Filter by scope
        global_budgets = await controller.list_budgets(scope=BudgetScope.Global)
        assert len(global_budgets) == 1
        assert global_budgets[0].id == budget1.id

        # Filter by scope_id
        openai_budgets = await controller.list_budgets(scope_id="openai")
        assert len(openai_budgets) == 1
        assert openai_budgets[0].id == budget2.id

    @pytest.mark.asyncio
    async def test_budget_remaining_budget_calculation(self) -> None:
        """Test remaining budget calculation."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )

        assert budget.remaining_budget == Decimal("100.00")

        budget = await controller.update_spending(budget.id, Decimal("30.00"))
        assert budget.remaining_budget == Decimal("70.00")

        budget = await controller.update_spending(budget.id, Decimal("70.00"))
        assert budget.remaining_budget == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_budget_utilization_percentage(self) -> None:
        """Test budget utilization percentage calculation."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )

        assert budget.utilization_percentage == 0.0

        budget = await controller.update_spending(budget.id, Decimal("25.00"))
        assert budget.utilization_percentage == 25.0

        budget = await controller.update_spending(budget.id, Decimal("50.00"))
        assert budget.utilization_percentage == 75.0

        budget = await controller.update_spending(budget.id, Decimal("25.00"))
        assert budget.utilization_percentage == 100.0

    @pytest.mark.asyncio
    async def test_budget_reset_at_calculation_daily(self) -> None:
        """Test that daily budget reset_at is calculated correctly."""
        from datetime import datetime

        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create daily budget
        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )

        # Verify reset_at is set to next midnight
        assert budget.reset_at > datetime.utcnow()
        assert budget.reset_at.hour == 0
        assert budget.reset_at.minute == 0
        assert budget.reset_at.second == 0

    @pytest.mark.asyncio
    async def test_budget_reset_at_calculation_monthly(self) -> None:
        """Test that monthly budget reset_at is calculated correctly."""
        from datetime import datetime

        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create monthly budget
        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("1000.00"),
            period=TimeWindow.Monthly,
        )

        # Verify reset_at is set to first of next month
        assert budget.reset_at > datetime.utcnow()
        assert budget.reset_at.day == 1
        assert budget.reset_at.hour == 0
        assert budget.reset_at.minute == 0
        assert budget.reset_at.second == 0


class TestCostControllerBudgetCheck:
    """Tests for budget checking before execution."""

    @pytest.mark.asyncio
    async def test_check_budget_allows_when_sufficient(self) -> None:
        """Test that check_budget allows request when budget is sufficient."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create budget with sufficient funds
        await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )

        # Create cost estimate
        cost_estimate = CostEstimate(
            amount=Decimal("25.00"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        # Check budget
        result = await controller.check_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
        )

        assert result.allowed is True
        assert result.remaining_budget == Decimal("100.00")
        assert result.would_exceed is False
        assert len(result.violated_budgets) == 0

    @pytest.mark.asyncio
    async def test_check_budget_rejects_when_insufficient(self) -> None:
        """Test that check_budget rejects request when budget would be exceeded."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create budget and spend some
        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )
        await controller.update_spending(budget.id, Decimal("80.00"))

        # Create cost estimate that would exceed budget
        cost_estimate = CostEstimate(
            amount=Decimal("25.00"),  # Would make total 105.00, exceeding 100.00
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        # Check budget
        result = await controller.check_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
        )

        assert result.allowed is False
        assert result.would_exceed is True
        assert len(result.violated_budgets) == 1
        assert budget.id in result.violated_budgets

        # Verify warning was logged
        warning_logs = [log for log in observability.logs if log["level"] == "WARNING"]
        assert len(warning_logs) == 1
        assert "Budget check failed" in warning_logs[0]["message"]

    @pytest.mark.asyncio
    async def test_check_budget_calculates_remaining_correctly(self) -> None:
        """Test that remaining_budget is calculated correctly."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create budget and spend some
        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )
        await controller.update_spending(budget.id, Decimal("30.00"))

        cost_estimate = CostEstimate(
            amount=Decimal("20.00"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        result = await controller.check_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
        )

        # Remaining should be 100 - 30 = 70
        assert result.remaining_budget == Decimal("70.00")
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_check_budget_multiple_scopes_global_and_provider(self) -> None:
        """Test checking multiple budget scopes (global and per-provider)."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create global budget
        await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )

        # Create per-provider budget
        await controller.create_budget(
            scope=BudgetScope.PerProvider,
            limit=Decimal("50.00"),
            period=TimeWindow.Daily,
            scope_id="openai",
        )

        cost_estimate = CostEstimate(
            amount=Decimal("30.00"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        # Check with provider_id
        result = await controller.check_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
            provider_id="openai",
        )

        # Should allow (both budgets have sufficient funds)
        assert result.allowed is True
        # Remaining should be minimum of both: min(100, 50) = 50
        assert result.remaining_budget == Decimal("50.00")

    @pytest.mark.asyncio
    async def test_check_budget_multiple_scopes_all_must_allow(self) -> None:
        """Test that all budgets must allow (AND logic)."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create global budget with sufficient funds
        global_budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )

        # Create per-provider budget that would be exceeded
        provider_budget = await controller.create_budget(
            scope=BudgetScope.PerProvider,
            limit=Decimal("50.00"),
            period=TimeWindow.Daily,
            scope_id="openai",
        )
        await controller.update_spending(provider_budget.id, Decimal("45.00"))

        cost_estimate = CostEstimate(
            amount=Decimal("10.00"),  # Would exceed provider budget (45 + 10 = 55 > 50)
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        # Check with provider_id
        result = await controller.check_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
            provider_id="openai",
        )

        # Should reject because provider budget would be exceeded
        assert result.allowed is False
        assert result.would_exceed is True
        assert provider_budget.id in result.violated_budgets
        assert global_budget.id not in result.violated_budgets

    @pytest.mark.asyncio
    async def test_check_budget_per_key_scope(self) -> None:
        """Test checking per-key budget scope."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create per-key budget
        await controller.create_budget(
            scope=BudgetScope.PerKey,
            limit=Decimal("25.00"),
            period=TimeWindow.Daily,
            scope_id="key1",
        )

        cost_estimate = CostEstimate(
            amount=Decimal("10.00"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        # Check with key_id
        result = await controller.check_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
            key_id="key1",
        )

        assert result.allowed is True
        assert result.remaining_budget == Decimal("25.00")

    @pytest.mark.asyncio
    async def test_check_budget_no_budgets_allows(self) -> None:
        """Test that check_budget allows request when no budgets exist."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        cost_estimate = CostEstimate(
            amount=Decimal("100.00"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        # Check budget (no budgets exist)
        result = await controller.check_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
        )

        assert result.allowed is True
        assert result.remaining_budget == Decimal("999999.99")  # Large value
        assert result.would_exceed is False
        assert len(result.violated_budgets) == 0

    @pytest.mark.asyncio
    async def test_check_budget_violated_budgets_list(self) -> None:
        """Test that violated budgets are correctly identified."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create multiple budgets
        budget1 = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )
        await controller.update_spending(budget1.id, Decimal("95.00"))

        budget2 = await controller.create_budget(
            scope=BudgetScope.PerProvider,
            limit=Decimal("50.00"),
            period=TimeWindow.Daily,
            scope_id="openai",
        )
        await controller.update_spending(budget2.id, Decimal("45.00"))

        cost_estimate = CostEstimate(
            amount=Decimal("10.00"),  # Would exceed both budgets
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        result = await controller.check_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
            provider_id="openai",
        )

        assert result.allowed is False
        assert len(result.violated_budgets) == 2
        assert budget1.id in result.violated_budgets
        assert budget2.id in result.violated_budgets

    @pytest.mark.asyncio
    async def test_check_budget_emits_event(self) -> None:
        """Test that budget check emits observability event."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
        )

        cost_estimate = CostEstimate(
            amount=Decimal("25.00"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        await controller.check_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
            provider_id="openai",
            key_id="key1",
        )

        # Verify event was emitted
        budget_check_events = [
            e for e in observability.events if e["event_type"] == "budget_checked"
        ]
        assert len(budget_check_events) == 1
        event = budget_check_events[0]
        assert "allowed" in event["payload"]
        assert "cost_estimate" in event["payload"]
        assert "remaining_budget" in event["payload"]
        assert event["payload"]["provider_id"] == "openai"
        assert event["payload"]["key_id"] == "key1"


class TestCostControllerSoftEnforcement:
    """Tests for soft budget enforcement mode."""

    @pytest.mark.asyncio
    async def test_soft_enforcement_allows_request(self) -> None:
        """Test that soft enforcement allows requests exceeding budget."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create soft enforcement budget
        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Soft,
        )
        await controller.update_spending(budget.id, Decimal("95.00"))

        cost_estimate = CostEstimate(
            amount=Decimal("10.00"),  # Would exceed budget
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        # Should not raise exception (soft mode allows request)
        result = await controller.enforce_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
            provider_id="openai",
            key_id="key1",
        )

        # Request should be allowed
        assert result.would_exceed is True
        # But no exception raised

    @pytest.mark.asyncio
    async def test_soft_enforcement_emits_budget_warning_event(self) -> None:
        """Test that soft enforcement emits budget_warning event."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Soft,
        )
        await controller.update_spending(budget.id, Decimal("95.00"))

        cost_estimate = CostEstimate(
            amount=Decimal("10.00"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        await controller.enforce_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
            provider_id="openai",
            key_id="key1",
        )

        # Verify budget_warning event was emitted
        warning_events = [
            e for e in observability.events if e["event_type"] == "budget_warning"
        ]
        assert len(warning_events) == 1
        event = warning_events[0]
        assert event["payload"]["budget_id"] == budget.id
        assert event["payload"]["limit_amount"] == 100.0
        assert event["payload"]["cost_estimate"] == 10.0
        assert event["payload"]["warning_count"] == 1
        assert event["payload"]["provider_id"] == "openai"
        assert event["payload"]["key_id"] == "key1"

    @pytest.mark.asyncio
    async def test_soft_enforcement_logs_warning(self) -> None:
        """Test that soft enforcement logs warning message."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Soft,
        )
        await controller.update_spending(budget.id, Decimal("95.00"))

        cost_estimate = CostEstimate(
            amount=Decimal("10.00"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        await controller.enforce_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
            provider_id="openai",
            key_id="key1",
        )

        # Verify warning was logged
        warning_logs = [
            log
            for log in observability.logs
            if log["level"] == "WARNING" and "Budget warning" in log["message"]
        ]
        assert len(warning_logs) == 1
        log = warning_logs[0]
        assert "soft enforcement" in log["message"]
        assert budget.id in log["message"]
        assert "warning #1" in log["message"]

    @pytest.mark.asyncio
    async def test_soft_enforcement_tracks_warning_count(self) -> None:
        """Test that soft enforcement tracks warning count per budget."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Soft,
        )
        await controller.update_spending(budget.id, Decimal("95.00"))

        cost_estimate = CostEstimate(
            amount=Decimal("10.00"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        # First warning
        await controller.enforce_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
            provider_id="openai",
            key_id="key1",
        )

        # Get updated budget
        updated_budget = await controller.get_budget(budget.id)
        assert updated_budget is not None
        assert updated_budget.warning_count == 1

        # Second warning
        await controller.enforce_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
            provider_id="openai",
            key_id="key1",
        )

        # Warning count should increment
        updated_budget = await controller.get_budget(budget.id)
        assert updated_budget is not None
        assert updated_budget.warning_count == 2

    @pytest.mark.asyncio
    async def test_soft_enforcement_with_downgrade(self) -> None:
        """Test soft enforcement with request downgrade enabled."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()
        adapter = MockProviderAdapter(provider_id="openai")
        adapter.estimate_cost_result = CostEstimate(
            amount=Decimal("0.001"),  # Cheaper model cost
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
            providers={"openai": adapter},
        )

        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Soft,
        )
        await controller.update_spending(budget.id, Decimal("95.00"))

        cost_estimate = CostEstimate(
            amount=Decimal("10.00"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        # Enable downgrade
        await controller.enforce_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
            provider_id="openai",
            key_id="key1",
            enable_downgrade=True,
        )

        # Verify model was downgraded
        assert request_intent.model == "gpt-3.5-turbo"

        # Verify downgrade info in event
        warning_events = [
            e for e in observability.events if e["event_type"] == "budget_warning"
        ]
        assert len(warning_events) == 1
        event = warning_events[0]
        assert event["payload"]["downgrade_attempted"] is True
        assert event["payload"]["downgrade_successful"] is True
        assert event["payload"]["original_model"] == "gpt-4"
        assert event["payload"]["downgrade_model"] == "gpt-3.5-turbo"

    @pytest.mark.asyncio
    async def test_soft_enforcement_with_downgrade_failure(self) -> None:
        """Test soft enforcement when downgrade cost estimation fails."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()
        adapter = MockProviderAdapter(provider_id="openai")
        adapter.estimate_cost_error = ValueError("Cost estimation failed")

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
            providers={"openai": adapter},
        )

        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Soft,
        )
        await controller.update_spending(budget.id, Decimal("95.00"))

        cost_estimate = CostEstimate(
            amount=Decimal("10.00"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )
        original_model = request_intent.model

        # Enable downgrade (should fail but not raise exception)
        await controller.enforce_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
            provider_id="openai",
            key_id="key1",
            enable_downgrade=True,
        )

        # Model should be reverted to original
        assert request_intent.model == original_model

        # Verify downgrade failure in event
        warning_events = [
            e for e in observability.events if e["event_type"] == "budget_warning"
        ]
        assert len(warning_events) == 1
        event = warning_events[0]
        assert event["payload"]["downgrade_attempted"] is True
        assert event["payload"]["downgrade_successful"] is False

    @pytest.mark.asyncio
    async def test_soft_enforcement_mixed_with_hard_enforcement(self) -> None:
        """Test that hard enforcement takes precedence over soft enforcement."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create both hard and soft budgets
        hard_budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Hard,
        )
        await controller.update_spending(hard_budget.id, Decimal("95.00"))

        soft_budget = await controller.create_budget(
            scope=BudgetScope.PerProvider,
            limit=Decimal("50.00"),
            period=TimeWindow.Daily,
            scope_id="openai",
            enforcement_mode=EnforcementMode.Soft,
        )
        await controller.update_spending(soft_budget.id, Decimal("45.00"))

        cost_estimate = CostEstimate(
            amount=Decimal("10.00"),  # Would exceed both
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        # Should raise BudgetExceededError (hard enforcement takes precedence)
        with pytest.raises(BudgetExceededError):
            await controller.enforce_budget(
                request_intent=request_intent,
                cost_estimate=cost_estimate,
                provider_id="openai",
                key_id="key1",
            )

    @pytest.mark.asyncio
    async def test_soft_enforcement_warning_count_resets_with_budget(self) -> None:
        """Test that warning count resets when budget resets."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create budget with past reset time
        from datetime import datetime, timedelta

        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Soft,
        )
        # Manually set warning count and past reset time
        budget.warning_count = 5
        budget.reset_at = datetime.utcnow() - timedelta(days=1)
        await controller._save_budget_to_store(budget)
        controller._budgets[budget.id] = budget

        # Trigger budget check (should reset)
        cost_estimate = CostEstimate(
            amount=Decimal("1.00"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        await controller.check_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
        )

        # Warning count should be reset
        updated_budget = await controller.get_budget(budget.id)
        assert updated_budget is not None
        assert updated_budget.warning_count == 0


class TestCostControllerCostReconciliation:
    """Tests for cost reconciliation functionality."""

    @pytest.mark.asyncio
    async def test_record_estimated_cost(self) -> None:
        """Test that estimated cost is recorded for later reconciliation."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        cost_estimate = CostEstimate(
            amount=Decimal("0.015"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        await controller.record_estimated_cost(
            request_id="req-123",
            cost_estimate=cost_estimate,
            provider_id="openai",
            model="gpt-4",
            key_id="key1",
        )

        # Verify estimated cost is cached
        assert "req-123" in controller._estimated_costs
        assert controller._estimated_costs["req-123"]["cost_estimate"] == cost_estimate
        assert controller._estimated_costs["req-123"]["provider_id"] == "openai"
        assert controller._estimated_costs["req-123"]["model"] == "gpt-4"
        assert controller._estimated_costs["req-123"]["key_id"] == "key1"

        # Verify event was emitted
        events = [e for e in observability.events if e["event_type"] == "cost_estimate_recorded"]
        assert len(events) == 1
        assert events[0]["payload"]["request_id"] == "req-123"
        assert events[0]["payload"]["estimated_cost"] == 0.015

    @pytest.mark.asyncio
    async def test_record_actual_cost_creates_reconciliation(self) -> None:
        """Test that recording actual cost creates reconciliation."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Record estimated cost first
        cost_estimate = CostEstimate(
            amount=Decimal("0.015"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        await controller.record_estimated_cost(
            request_id="req-123",
            cost_estimate=cost_estimate,
            provider_id="openai",
            model="gpt-4",
            key_id="key1",
        )

        # Record actual cost
        reconciliation = await controller.record_actual_cost(
            request_id="req-123",
            actual_cost=Decimal("0.014"),
        )

        # Verify reconciliation was created
        assert reconciliation is not None
        assert reconciliation.request_id == "req-123"
        assert reconciliation.estimated_cost == Decimal("0.015")
        assert reconciliation.actual_cost == Decimal("0.014")
        assert reconciliation.error_amount == Decimal("-0.001")
        assert abs(reconciliation.error_percentage - (-6.67)) < 0.1  # Approximately -6.67%
        assert reconciliation.provider_id == "openai"
        assert reconciliation.model == "gpt-4"
        assert reconciliation.key_id == "key1"

        # Verify estimated cost was removed from cache
        assert "req-123" not in controller._estimated_costs

    @pytest.mark.asyncio
    async def test_record_actual_cost_calculates_errors(self) -> None:
        """Test that error calculations are correct."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Test case 1: Actual higher than estimated
        cost_estimate1 = CostEstimate(
            amount=Decimal("0.010"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        await controller.record_estimated_cost(
            request_id="req-1",
            cost_estimate=cost_estimate1,
        )

        reconciliation1 = await controller.record_actual_cost(
            request_id="req-1",
            actual_cost=Decimal("0.012"),
        )

        assert reconciliation1 is not None
        assert reconciliation1.error_amount == Decimal("0.002")  # 0.012 - 0.010
        assert abs(reconciliation1.error_percentage - 20.0) < 0.1  # (0.002 / 0.010) * 100

        # Test case 2: Actual lower than estimated
        cost_estimate2 = CostEstimate(
            amount=Decimal("0.020"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        await controller.record_estimated_cost(
            request_id="req-2",
            cost_estimate=cost_estimate2,
        )

        reconciliation2 = await controller.record_actual_cost(
            request_id="req-2",
            actual_cost=Decimal("0.018"),
        )

        assert reconciliation2 is not None
        assert reconciliation2.error_amount == Decimal("-0.002")  # 0.018 - 0.020
        assert abs(reconciliation2.error_percentage - (-10.0)) < 0.1  # (-0.002 / 0.020) * 100

    @pytest.mark.asyncio
    async def test_record_actual_cost_without_estimated_returns_none(self) -> None:
        """Test that recording actual cost without estimated cost returns None."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Try to record actual cost without estimated cost
        reconciliation = await controller.record_actual_cost(
            request_id="req-unknown",
            actual_cost=Decimal("0.014"),
        )

        # Should return None
        assert reconciliation is None

        # Should log warning
        warning_logs = [
            log
            for log in observability.logs
            if "Estimated cost not found" in log["message"]
        ]
        assert len(warning_logs) == 1

    @pytest.mark.asyncio
    async def test_record_actual_cost_emits_events(self) -> None:
        """Test that reconciliation emits observability events."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        cost_estimate = CostEstimate(
            amount=Decimal("0.015"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        await controller.record_estimated_cost(
            request_id="req-123",
            cost_estimate=cost_estimate,
            provider_id="openai",
            model="gpt-4",
        )

        await controller.record_actual_cost(
            request_id="req-123",
            actual_cost=Decimal("0.014"),
        )

        # Verify cost_reconciled event was emitted
        reconciled_events = [
            e for e in observability.events if e["event_type"] == "cost_reconciled"
        ]
        assert len(reconciled_events) == 1
        event = reconciled_events[0]
        assert event["payload"]["request_id"] == "req-123"
        assert event["payload"]["estimated_cost"] == 0.015
        assert event["payload"]["actual_cost"] == 0.014
        assert event["payload"]["error_amount"] == -0.001

        # Verify cost_model_analysis event was emitted
        analysis_events = [
            e for e in observability.events if e["event_type"] == "cost_model_analysis"
        ]
        assert len(analysis_events) == 1

    @pytest.mark.asyncio
    async def test_get_reconciliation_history(self) -> None:
        """Test that reconciliation history can be queried."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create multiple reconciliations
        for i in range(3):
            cost_estimate = CostEstimate(
                amount=Decimal(f"0.0{i+1}"),
                currency="USD",
                confidence=0.85,
                estimation_method="token_count_approximation",
                input_tokens_estimate=100,
                output_tokens_estimate=50,
            )

            await controller.record_estimated_cost(
                request_id=f"req-{i}",
                cost_estimate=cost_estimate,
                provider_id="openai",
                model="gpt-4",
            )

            await controller.record_actual_cost(
                request_id=f"req-{i}",
                actual_cost=Decimal(f"0.0{i+2}"),
            )

        # Get history (note: actual implementation would query StateStore)
        # For now, this tests the interface
        history = await controller.get_reconciliation_history()
        # In real implementation, this would return reconciliations from StateStore
        # For now, we just verify the method exists and doesn't raise errors
        assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_get_reconciliation_statistics(self) -> None:
        """Test that reconciliation statistics are calculated correctly."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create reconciliations with known values
        test_cases = [
            (Decimal("0.010"), Decimal("0.012")),  # +20% error
            (Decimal("0.020"), Decimal("0.018")),  # -10% error
            (Decimal("0.015"), Decimal("0.015")),  # 0% error
        ]

        for i, (estimated, actual) in enumerate(test_cases):
            cost_estimate = CostEstimate(
                amount=estimated,
                currency="USD",
                confidence=0.85,
                estimation_method="token_count_approximation",
                input_tokens_estimate=100,
                output_tokens_estimate=50,
            )

            await controller.record_estimated_cost(
                request_id=f"req-{i}",
                cost_estimate=cost_estimate,
                provider_id="openai",
                model="gpt-4",
            )

            await controller.record_actual_cost(
                request_id=f"req-{i}",
                actual_cost=actual,
            )

        # Get statistics
        stats = await controller.get_reconciliation_statistics()

        # Verify statistics structure
        assert "count" in stats
        assert "avg_error_amount" in stats
        assert "avg_error_percentage" in stats
        assert "avg_estimated_cost" in stats
        assert "avg_actual_cost" in stats

    @pytest.mark.asyncio
    async def test_reconciliation_with_provider_and_model_context(self) -> None:
        """Test that reconciliation preserves provider and model context."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        cost_estimate = CostEstimate(
            amount=Decimal("0.015"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        await controller.record_estimated_cost(
            request_id="req-123",
            cost_estimate=cost_estimate,
            provider_id="openai",
            model="gpt-4",
            key_id="key1",
        )

        # Record actual cost with different context (should use cached context)
        reconciliation = await controller.record_actual_cost(
            request_id="req-123",
            actual_cost=Decimal("0.014"),
            provider_id="anthropic",  # Different, but should use cached
            model="claude-3",  # Different, but should use cached
        )

        # Should use cached context from estimated cost
        assert reconciliation is not None
        assert reconciliation.provider_id == "openai"
        assert reconciliation.model == "gpt-4"
        assert reconciliation.key_id == "key1"

    @pytest.mark.asyncio
    async def test_reconciliation_error_percentage_edge_cases(self) -> None:
        """Test error percentage calculation for edge cases."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Test case: Zero estimated cost
        cost_estimate = CostEstimate(
            amount=Decimal("0.000"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        await controller.record_estimated_cost(
            request_id="req-zero-est",
            cost_estimate=cost_estimate,
        )

        reconciliation = await controller.record_actual_cost(
            request_id="req-zero-est",
            actual_cost=Decimal("0.001"),
        )

        assert reconciliation is not None
        # When estimated is 0 and actual > 0, error percentage should be 100%
        assert reconciliation.error_percentage == 100.0

        # Test case: Both zero
        cost_estimate2 = CostEstimate(
            amount=Decimal("0.000"),
            currency="USD",
            confidence=0.85,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )

        await controller.record_estimated_cost(
            request_id="req-both-zero",
            cost_estimate=cost_estimate2,
        )

        reconciliation2 = await controller.record_actual_cost(
            request_id="req-both-zero",
            actual_cost=Decimal("0.000"),
        )

        assert reconciliation2 is not None
        # When both are 0, error percentage should be 0%
        assert reconciliation2.error_percentage == 0.0

