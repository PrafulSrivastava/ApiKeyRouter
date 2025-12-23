"""Tests for hard budget enforcement."""

from decimal import Decimal

import pytest

from apikeyrouter.domain.components.cost_controller import BudgetExceededError, CostController
from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.interfaces.state_store import StateStore
from apikeyrouter.domain.models.budget import BudgetScope, EnforcementMode
from apikeyrouter.domain.models.cost_estimate import CostEstimate
from apikeyrouter.domain.models.quota_state import TimeWindow
from apikeyrouter.domain.models.request_intent import Message, RequestIntent


class MockStateStore(StateStore):
    """Mock StateStore for testing."""

    def __init__(self) -> None:
        """Initialize mock store."""
        pass

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


class TestCostControllerHardEnforcement:
    """Tests for hard budget enforcement."""

    @pytest.mark.asyncio
    async def test_enforce_budget_allows_when_sufficient(self) -> None:
        """Test that enforce_budget allows request when budget is sufficient."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create budget with hard enforcement
        await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Hard,
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

        # Enforce budget (should allow)
        result = await controller.enforce_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
        )

        assert result.allowed is True
        assert result.would_exceed is False

    @pytest.mark.asyncio
    async def test_enforce_budget_rejects_hard_enforcement(self) -> None:
        """Test that enforce_budget rejects request when hard enforcement budget exceeded."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create budget with hard enforcement and spend some
        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Hard,
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

        # Enforce budget (should raise BudgetExceededError)
        with pytest.raises(BudgetExceededError) as exc_info:
            await controller.enforce_budget(
                request_intent=request_intent,
                cost_estimate=cost_estimate,
            )

        error = exc_info.value
        assert "Budget exceeded" in error.message
        assert error.remaining_budget == Decimal("20.00")
        assert budget.id in error.violated_budgets
        assert error.cost_estimate == Decimal("25.00")
        assert error.budget_limit == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_enforce_budget_allows_soft_enforcement(self) -> None:
        """Test that enforce_budget allows request when soft enforcement budget exceeded."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create budget with soft enforcement and spend some
        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Soft,
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

        # Enforce budget (should allow with soft enforcement)
        result = await controller.enforce_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
        )

        # Should return result but not raise error (soft enforcement)
        assert result.allowed is False
        assert result.would_exceed is True

    @pytest.mark.asyncio
    async def test_enforce_budget_error_message_clear(self) -> None:
        """Test that BudgetExceededError has clear error message."""
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
            enforcement_mode=EnforcementMode.Hard,
        )
        await controller.update_spending(budget.id, Decimal("80.00"))

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

        with pytest.raises(BudgetExceededError) as exc_info:
            await controller.enforce_budget(
                request_intent=request_intent,
                cost_estimate=cost_estimate,
            )

        error = exc_info.value
        # Verify error message contains key information
        assert "$25.00" in error.message
        assert "$100.00" in error.message
        assert "would exceed limit" in error.message.lower()

    @pytest.mark.asyncio
    async def test_enforce_budget_logs_violation_event(self) -> None:
        """Test that budget violation event is logged."""
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
            enforcement_mode=EnforcementMode.Hard,
        )
        await controller.update_spending(budget.id, Decimal("80.00"))

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

        with pytest.raises(BudgetExceededError):
            await controller.enforce_budget(
                request_intent=request_intent,
                cost_estimate=cost_estimate,
            )

        # Verify budget_violation event was emitted
        violation_events = [
            e for e in observability.events if e["event_type"] == "budget_violation"
        ]
        assert len(violation_events) == 1
        event = violation_events[0]
        assert event["payload"]["enforcement_mode"] == "hard"
        assert event["payload"]["cost_estimate"] == 25.0
        assert budget.id in event["payload"]["violated_budgets"]

        # Verify error was logged
        error_logs = [log for log in observability.logs if log["level"] == "ERROR"]
        assert len(error_logs) == 1
        assert "Budget violation" in error_logs[0]["message"]

    @pytest.mark.asyncio
    async def test_enforce_budget_multiple_budgets_hard_enforcement(self) -> None:
        """Test enforce_budget with multiple budgets where one has hard enforcement."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create soft enforcement budget
        soft_budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("200.00"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Soft,
        )
        await controller.update_spending(soft_budget.id, Decimal("190.00"))

        # Create hard enforcement budget
        hard_budget = await controller.create_budget(
            scope=BudgetScope.PerProvider,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
            scope_id="openai",
            enforcement_mode=EnforcementMode.Hard,
        )
        await controller.update_spending(hard_budget.id, Decimal("80.00"))

        cost_estimate = CostEstimate(
            amount=Decimal("25.00"),  # Would exceed hard budget
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

        # Should raise error because hard budget would be exceeded
        with pytest.raises(BudgetExceededError) as exc_info:
            await controller.enforce_budget(
                request_intent=request_intent,
                cost_estimate=cost_estimate,
                provider_id="openai",
            )

        error = exc_info.value
        assert hard_budget.id in error.violated_budgets

    @pytest.mark.asyncio
    async def test_enforce_budget_no_hard_enforcement_allows(self) -> None:
        """Test that enforce_budget allows when only soft enforcement budgets exceeded."""
        state_store = MockStateStore()
        observability = MockObservabilityManager()

        controller = CostController(
            state_store=state_store,
            observability_manager=observability,
        )

        # Create only soft enforcement budget
        budget = await controller.create_budget(
            scope=BudgetScope.Global,
            limit=Decimal("100.00"),
            period=TimeWindow.Daily,
            enforcement_mode=EnforcementMode.Soft,
        )
        await controller.update_spending(budget.id, Decimal("80.00"))

        cost_estimate = CostEstimate(
            amount=Decimal("25.00"),  # Would exceed budget
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

        # Should not raise error (soft enforcement)
        result = await controller.enforce_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
        )

        assert result.allowed is False
        assert result.would_exceed is True

    @pytest.mark.asyncio
    async def test_enforce_budget_includes_budget_details_in_error(self) -> None:
        """Test that BudgetExceededError includes all budget details."""
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
            enforcement_mode=EnforcementMode.Hard,
        )
        await controller.update_spending(budget.id, Decimal("75.00"))

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

        with pytest.raises(BudgetExceededError) as exc_info:
            await controller.enforce_budget(
                request_intent=request_intent,
                cost_estimate=cost_estimate,
            )

        error = exc_info.value
        # Verify all error attributes are set
        assert error.remaining_budget == Decimal("25.00")
        assert len(error.violated_budgets) == 1
        assert error.cost_estimate == Decimal("30.00")
        assert error.budget_limit == Decimal("100.00")
        assert error.message is not None
