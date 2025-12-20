"""CostController component for proactive cost control and budget enforcement."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.interfaces.state_store import StateQuery, StateStore
from apikeyrouter.domain.models.budget import Budget, BudgetScope, EnforcementMode
from apikeyrouter.domain.models.budget_check_result import BudgetCheckResult
from apikeyrouter.domain.models.cost_estimate import CostEstimate
from apikeyrouter.domain.models.cost_reconciliation import CostReconciliation
from apikeyrouter.domain.models.quota_state import TimeWindow
from apikeyrouter.domain.models.request_intent import RequestIntent


class BudgetExceededError(Exception):
    """Raised when a request would exceed budget limit with hard enforcement.

    BudgetExceededError is raised when hard budget enforcement is enabled and
    a request would exceed one or more budget limits. The error includes details
    about which budgets were violated and the remaining budget amounts.

    Example:
        ```python
        raise BudgetExceededError(
            message="Budget exceeded: $25.00 would exceed limit of $100.00",
            remaining_budget=Decimal("75.00"),
            violated_budgets=["budget_global_123"],
            cost_estimate=Decimal("25.00"),
            budget_limit=Decimal("100.00")
        )
        ```
    """

    def __init__(
        self,
        message: str,
        remaining_budget: Decimal,
        violated_budgets: list[str],
        cost_estimate: Decimal,
        budget_limit: Decimal | None = None,
    ) -> None:
        """Initialize BudgetExceededError.

        Args:
            message: Human-readable error message.
            remaining_budget: Remaining budget amount before this request.
            violated_budgets: List of budget IDs that would be exceeded.
            cost_estimate: Estimated cost of the request.
            budget_limit: Budget limit amount (if single budget).
        """
        self.message = message
        self.remaining_budget = remaining_budget
        self.violated_budgets = violated_budgets
        self.cost_estimate = cost_estimate
        self.budget_limit = budget_limit
        super().__init__(self.message)

    def __repr__(self) -> str:
        """String representation of the error."""
        return (
            f"BudgetExceededError(message={self.message!r}, "
            f"violated_budgets={self.violated_budgets}, "
            f"remaining_budget={self.remaining_budget})"
        )

    def __str__(self) -> str:
        """Human-readable error message."""
        return self.message


class CostController:
    """Manages cost estimation and proactive budget enforcement.

    CostController provides pre-execution cost estimation to enable proactive
    cost control and budget enforcement before making API calls. It estimates
    costs based on request intent and provider pricing models.

    Example:
        ```python
        controller = CostController(
            state_store=state_store,
            observability_manager=observability_manager,
            providers={"openai": openai_adapter}
        )
        estimate = await controller.estimate_request_cost(
            request_intent=intent,
            provider_id="openai",
            key_id="key1"
        )
        if estimate.amount > budget_limit:
            # Reject request or use cheaper provider
            ...
        ```
    """

    def __init__(
        self,
        state_store: StateStore,
        observability_manager: ObservabilityManager,
        providers: dict[str, ProviderAdapter] | None = None,
    ) -> None:
        """Initialize CostController with dependencies.

        Args:
            state_store: StateStore for budget tracking and state persistence.
            observability_manager: ObservabilityManager for cost events and logging.
            providers: Optional dict mapping provider_id to ProviderAdapter for
                cost estimation. If not provided, cost estimation will fail.
        """
        self._state_store = state_store
        self._observability = observability_manager
        self._providers = providers or {}
        # Internal cache for budgets (keyed by budget_id)
        self._budgets: dict[str, Budget] = {}
        # Cache for estimated costs by request_id (for reconciliation)
        # Format: {request_id: {"cost_estimate": CostEstimate, "provider_id": str, "model": str, "key_id": str}}
        self._estimated_costs: dict[str, dict[str, Any]] = {}

    async def estimate_request_cost(
        self,
        request_intent: RequestIntent,
        provider_id: str,
        key_id: str,
    ) -> CostEstimate:
        """Estimate request cost before execution.

        Estimates the cost of a request based on the request intent and provider
        pricing model. This enables proactive cost control and budget enforcement
        before making the actual API call.

        Args:
            request_intent: Request intent containing model, messages, and parameters.
            provider_id: Provider identifier (e.g., "openai", "anthropic").
            key_id: API key identifier (for tracking and observability).

        Returns:
            CostEstimate: Cost estimate with amount, confidence, and token estimates.

        Raises:
            ValueError: If provider_id is not found in providers dict.
            SystemError: If cost estimation fails (e.g., unknown model, adapter error).
        """
        # Get ProviderAdapter for provider_id
        adapter = self._providers.get(provider_id)
        if adapter is None:
            await self._observability.log(
                level="ERROR",
                message=f"Provider adapter not found for provider_id: {provider_id}",
                context={"provider_id": provider_id, "key_id": key_id},
            )
            raise ValueError(f"Provider adapter not found for provider_id: {provider_id}")

        # Call adapter.estimate_cost to get cost estimate
        # The adapter handles token estimation and cost calculation internally
        try:
            cost_estimate = await adapter.estimate_cost(request_intent)
        except Exception as e:
            await self._observability.log(
                level="ERROR",
                message=f"Cost estimation failed: {str(e)}",
                context={
                    "provider_id": provider_id,
                    "key_id": key_id,
                    "model": request_intent.model,
                    "error": str(e),
                },
            )
            # Re-raise as SystemError if it's not already
            from apikeyrouter.domain.models.system_error import ErrorCategory, SystemError

            if isinstance(e, SystemError):
                raise
            raise SystemError(
                category=ErrorCategory.ValidationError,
                message=f"Cost estimation failed: {str(e)}",
                provider_code="cost_estimation_error",
                retryable=False,
            ) from e

        # Emit cost estimation event for observability
        await self._observability.emit_event(
            event_type="cost_estimated",
            payload={
                "provider_id": provider_id,
                "key_id": key_id,
                "model": request_intent.model,
                "estimated_cost": float(cost_estimate.amount),
                "currency": cost_estimate.currency,
                "confidence": cost_estimate.confidence,
                "input_tokens_estimate": cost_estimate.input_tokens_estimate,
                "output_tokens_estimate": cost_estimate.output_tokens_estimate,
            },
            metadata={"request_id": getattr(request_intent, "request_id", None)},
        )

        return cost_estimate

    async def create_budget(
        self,
        scope: BudgetScope,
        limit: Decimal,
        period: TimeWindow,
        scope_id: str | None = None,
        enforcement_mode: EnforcementMode = EnforcementMode.Hard,
    ) -> Budget:
        """Create a new budget.

        Creates a budget with the specified scope, limit, and period. The budget
        will track spending and reset according to the time window.

        Args:
            scope: Budget scope (global, per_provider, per_key, per_route).
            limit: Budget limit amount in USD.
            period: Budget reset period (daily, monthly).
            scope_id: Specific entity ID if scoped (provider_id, key_id, route_id).
            enforcement_mode: Enforcement mode (hard reject or soft warn).

        Returns:
            Budget: Created budget object.

        Raises:
            ValueError: If scope_id is required but not provided, or if limit is invalid.
        """
        # Validate scope_id for non-global scopes
        if scope != BudgetScope.Global and not scope_id:
            raise ValueError(f"scope_id is required for scope {scope.value}")

        # Generate budget ID
        budget_id = f"budget_{scope.value}_{uuid.uuid4().hex[:8]}"
        if scope_id:
            budget_id = f"{budget_id}_{scope_id}"

        # Calculate reset_at based on period
        current_time = datetime.utcnow()
        reset_at = period.calculate_next_reset(current_time)

        # Create budget
        budget = Budget(
            id=budget_id,
            scope=scope,
            scope_id=scope_id,
            limit_amount=limit,
            current_spend=Decimal("0.00"),
            period=period,
            enforcement_mode=enforcement_mode,
            reset_at=reset_at,
            created_at=current_time,
        )

        # Store budget in cache
        self._budgets[budget_id] = budget

        # Save to StateStore using query_state (for persistence)
        # Note: This is a workaround until StateStore has explicit budget methods
        await self._save_budget_to_store(budget)

        # Emit budget created event
        await self._observability.emit_event(
            event_type="budget_created",
            payload={
                "budget_id": budget_id,
                "scope": scope.value,
                "scope_id": scope_id,
                "limit_amount": float(limit),
                "period": period.value,
                "enforcement_mode": enforcement_mode.value,
            },
        )

        await self._observability.log(
            level="INFO",
            message=f"Budget created: {budget_id}",
            context={
                "budget_id": budget_id,
                "scope": scope.value,
                "limit_amount": float(limit),
            },
        )

        return budget

    async def update_spending(
        self,
        budget_id: str,
        amount: Decimal,
    ) -> Budget:
        """Update spending for a budget.

        Increments the current_spend by the specified amount and updates the
        budget in storage. Also checks if reset is needed based on time window.

        Args:
            budget_id: Budget identifier.
            amount: Amount to add to current spending (must be >= 0).

        Returns:
            Budget: Updated budget object.

        Raises:
            ValueError: If budget not found or amount is negative.
        """
        if amount < 0:
            raise ValueError("Spending amount cannot be negative")

        # Get budget from cache or load from store
        budget = await self._get_budget(budget_id)
        if budget is None:
            raise ValueError(f"Budget not found: {budget_id}")

        # Check if reset is needed
        budget = await self._check_and_reset_budget(budget)

        # Update spending
        budget.current_spend += amount

        # Update in cache
        self._budgets[budget_id] = budget

        # Save to StateStore
        await self._save_budget_to_store(budget)

        # Emit spending update event
        await self._observability.emit_event(
            event_type="budget_spending_updated",
            payload={
                "budget_id": budget_id,
                "amount": float(amount),
                "current_spend": float(budget.current_spend),
                "remaining_budget": float(budget.remaining_budget),
                "utilization_percentage": budget.utilization_percentage,
            },
        )

        # Log warning if budget exceeded
        if budget.is_exceeded:
            await self._observability.log(
                level="WARNING",
                message=f"Budget exceeded: {budget_id}",
                context={
                    "budget_id": budget_id,
                    "current_spend": float(budget.current_spend),
                    "limit_amount": float(budget.limit_amount),
                },
            )

        return budget

    async def get_budget(self, budget_id: str) -> Budget | None:
        """Get budget by ID.

        Args:
            budget_id: Budget identifier.

        Returns:
            Budget if found, None otherwise.
        """
        return await self._get_budget(budget_id)

    async def list_budgets(
        self,
        scope: BudgetScope | None = None,
        scope_id: str | None = None,
    ) -> list[Budget]:
        """List budgets, optionally filtered by scope.

        Args:
            scope: Optional scope filter.
            scope_id: Optional scope_id filter.

        Returns:
            List of matching budgets.
        """
        # Load budgets from store if cache is empty
        if not self._budgets:
            await self._load_budgets_from_store()

        budgets = list(self._budgets.values())

        # Apply filters
        if scope is not None:
            budgets = [b for b in budgets if b.scope == scope]
        if scope_id is not None:
            budgets = [b for b in budgets if b.scope_id == scope_id]

        return budgets

    async def _get_budget(self, budget_id: str) -> Budget | None:
        """Internal method to get budget from cache or store."""
        # Check cache first
        if budget_id in self._budgets:
            budget = self._budgets[budget_id]
            # Check if reset is needed
            budget = await self._check_and_reset_budget(budget)
            return budget

        # Load from store
        await self._load_budgets_from_store()
        return self._budgets.get(budget_id)

    async def _check_and_reset_budget(self, budget: Budget) -> Budget:
        """Check if budget needs reset and reset if necessary.

        Args:
            budget: Budget to check.

        Returns:
            Updated budget (reset if needed).
        """
        current_time = datetime.utcnow()

        # Check if reset is needed
        if current_time >= budget.reset_at:
            # Reset spending and warning count
            budget.current_spend = Decimal("0.00")
            budget.warning_count = 0

            # Calculate next reset time
            budget.reset_at = budget.period.calculate_next_reset(current_time)

            # Update in cache
            self._budgets[budget.id] = budget

            # Save to store
            await self._save_budget_to_store(budget)

            # Emit reset event
            await self._observability.emit_event(
                event_type="budget_reset",
                payload={
                    "budget_id": budget.id,
                    "scope": budget.scope.value,
                    "period": budget.period.value,
                    "reset_at": budget.reset_at.isoformat(),
                },
            )

            await self._observability.log(
                level="INFO",
                message=f"Budget reset: {budget.id}",
                context={
                    "budget_id": budget.id,
                    "period": budget.period.value,
                },
            )

        return budget

    async def _save_budget_to_store(self, budget: Budget) -> None:
        """Save budget to StateStore using query_state.

        This is a workaround until StateStore has explicit budget methods.
        For now, we'll use query_state to store budgets.
        """
        # Note: StateStore.query_state is for querying, not saving.
        # This is a placeholder implementation. In a real implementation,
        # StateStore would have save_budget/get_budget methods.
        # For now, we rely on the in-memory cache.
        pass

    async def _load_budgets_from_store(self) -> None:
        """Load budgets from StateStore using query_state.

        This is a workaround until StateStore has explicit budget methods.
        """
        # Query budgets from store
        query = StateQuery(entity_type="Budget")
        results = await self._state_store.query_state(query)

        # Load budgets into cache
        for result in results:
            if isinstance(result, Budget):
                self._budgets[result.id] = result
                # Check and reset if needed
                self._budgets[result.id] = await self._check_and_reset_budget(result)

    async def check_budget(
        self,
        request_intent: RequestIntent,
        cost_estimate: CostEstimate,
        provider_id: str | None = None,
        key_id: str | None = None,
    ) -> BudgetCheckResult:
        """Check if request would exceed budget before execution.

        Checks all applicable budgets (global, per-provider, per-key) to determine
        if the request is allowed. All budgets must allow the request (AND logic).
        If any budget would be exceeded, the request is not allowed.

        Args:
            request_intent: Request intent (for context, not used directly).
            cost_estimate: Estimated cost of the request.
            provider_id: Optional provider identifier for per-provider budget check.
            key_id: Optional key identifier for per-key budget check.

        Returns:
            BudgetCheckResult: Result indicating if request is allowed, remaining
                budget, and any violated budgets.
        """
        # Get applicable budgets
        applicable_budgets: list[Budget] = []

        # Always check global budget
        global_budgets = await self.list_budgets(scope=BudgetScope.Global)
        applicable_budgets.extend(global_budgets)

        # Check per-provider budget if provider_id provided
        if provider_id:
            provider_budgets = await self.list_budgets(
                scope=BudgetScope.PerProvider, scope_id=provider_id
            )
            applicable_budgets.extend(provider_budgets)

        # Check per-key budget if key_id provided
        if key_id:
            key_budgets = await self.list_budgets(scope=BudgetScope.PerKey, scope_id=key_id)
            applicable_budgets.extend(key_budgets)

        # If no budgets found, allow request (no constraints)
        if not applicable_budgets:
            return BudgetCheckResult(
                allowed=True,
                remaining_budget=Decimal("999999.99"),  # Large value indicating no limit
                would_exceed=False,
                violated_budgets=[],
            )

        # Check each budget
        violated_budgets: list[str] = []
        remaining_budgets: list[Decimal] = []
        all_allowed = True

        for budget in applicable_budgets:
            # Check and reset if needed
            budget = await self._check_and_reset_budget(budget)

            # Calculate remaining budget after this request
            remaining_after_request = budget.remaining_budget - cost_estimate.amount

            # Check if request would exceed budget
            would_exceed_this_budget = remaining_after_request < 0

            if would_exceed_this_budget:
                violated_budgets.append(budget.id)
                all_allowed = False

            # Track remaining budget (before request)
            remaining_budgets.append(budget.remaining_budget)

        # Calculate minimum remaining budget across all applicable budgets
        min_remaining = min(remaining_budgets) if remaining_budgets else Decimal("0.00")

        # Determine primary budget_id (first budget if single, None if multiple)
        primary_budget_id = applicable_budgets[0].id if len(applicable_budgets) == 1 else None

        # Emit budget check event
        await self._observability.emit_event(
            event_type="budget_checked",
            payload={
                "allowed": all_allowed,
                "cost_estimate": float(cost_estimate.amount),
                "remaining_budget": float(min_remaining),
                "would_exceed": len(violated_budgets) > 0,
                "violated_budgets": violated_budgets,
                "provider_id": provider_id,
                "key_id": key_id,
            },
        )

        # Log if budget would be exceeded
        if not all_allowed:
            await self._observability.log(
                level="WARNING",
                message=f"Budget check failed: {len(violated_budgets)} budget(s) would be exceeded",
                context={
                    "violated_budgets": violated_budgets,
                    "cost_estimate": float(cost_estimate.amount),
                    "provider_id": provider_id,
                    "key_id": key_id,
                },
            )

        return BudgetCheckResult(
            allowed=all_allowed,
            remaining_budget=min_remaining,
            would_exceed=len(violated_budgets) > 0,
            budget_id=primary_budget_id,
            violated_budgets=violated_budgets,
        )

    async def enforce_budget(
        self,
        request_intent: RequestIntent,
        cost_estimate: CostEstimate,
        provider_id: str | None = None,
        key_id: str | None = None,
        enable_downgrade: bool = False,
    ) -> BudgetCheckResult:
        """Enforce budget with hard and soft mode support.

        Checks budgets and enforces based on enforcement mode:
        - Hard mode: Rejects requests that would exceed budget (raises BudgetExceededError)
        - Soft mode: Allows requests but logs warnings and emits budget_warning events

        Args:
            request_intent: Request intent (for context and optional downgrade).
            cost_estimate: Estimated cost of the request.
            provider_id: Optional provider identifier for per-provider budget check.
            key_id: Optional key identifier for per-key budget check.
            enable_downgrade: If True, attempt to downgrade to cheaper model for soft mode warnings.

        Returns:
            BudgetCheckResult: Result indicating if request is allowed.

        Raises:
            BudgetExceededError: If hard enforcement budget would be exceeded.
        """
        # Check budgets
        check_result = await self.check_budget(
            request_intent=request_intent,
            cost_estimate=cost_estimate,
            provider_id=provider_id,
            key_id=key_id,
        )

        # If budget would be exceeded, check enforcement mode
        if check_result.would_exceed:
            # Get violated budgets to check enforcement mode
            violated_budgets_list = await self._get_violated_budgets(check_result.violated_budgets)

            # Separate hard and soft enforcement budgets
            hard_enforcement_budgets = [
                b for b in violated_budgets_list if b.enforcement_mode == EnforcementMode.Hard
            ]
            soft_enforcement_budgets = [
                b for b in violated_budgets_list if b.enforcement_mode == EnforcementMode.Soft
            ]

            # If any hard enforcement budgets, reject request
            if hard_enforcement_budgets:
                # Get budget details for error message
                primary_budget = hard_enforcement_budgets[0]
                budget_limit = primary_budget.limit_amount
                current_spend = primary_budget.current_spend

                # Create error message
                error_message = (
                    f"Budget exceeded: ${cost_estimate.amount} would exceed limit of ${budget_limit}. "
                    f"Current spend: ${current_spend}, Remaining: ${check_result.remaining_budget}"
                )

                # Emit budget violation event
                await self._observability.emit_event(
                    event_type="budget_violation",
                    payload={
                        "violated_budgets": check_result.violated_budgets,
                        "cost_estimate": float(cost_estimate.amount),
                        "remaining_budget": float(check_result.remaining_budget),
                        "enforcement_mode": "hard",
                        "provider_id": provider_id,
                        "key_id": key_id,
                    },
                )

                # Log budget violation
                await self._observability.log(
                    level="ERROR",
                    message=f"Budget violation (hard enforcement): {error_message}",
                    context={
                        "violated_budgets": check_result.violated_budgets,
                        "cost_estimate": float(cost_estimate.amount),
                        "remaining_budget": float(check_result.remaining_budget),
                        "budget_limit": float(budget_limit),
                        "current_spend": float(current_spend),
                        "provider_id": provider_id,
                        "key_id": key_id,
                    },
                )

                # Raise BudgetExceededError
                raise BudgetExceededError(
                    message=error_message,
                    remaining_budget=check_result.remaining_budget,
                    violated_budgets=check_result.violated_budgets,
                    cost_estimate=cost_estimate.amount,
                    budget_limit=budget_limit,
                )

            # Handle soft enforcement budgets - warn but allow
            if soft_enforcement_budgets:
                await self._handle_soft_enforcement(
                    soft_budgets=soft_enforcement_budgets,
                    request_intent=request_intent,
                    cost_estimate=cost_estimate,
                    provider_id=provider_id,
                    key_id=key_id,
                    enable_downgrade=enable_downgrade,
                )

        return check_result

    async def _get_violated_budgets(self, budget_ids: list[str]) -> list[Budget]:
        """Get Budget objects for given budget IDs.

        Args:
            budget_ids: List of budget IDs.

        Returns:
            List of Budget objects.
        """
        budgets: list[Budget] = []
        for budget_id in budget_ids:
            budget = await self._get_budget(budget_id)
            if budget:
                budgets.append(budget)
        return budgets

    async def _handle_soft_enforcement(
        self,
        soft_budgets: list[Budget],
        request_intent: RequestIntent,
        cost_estimate: CostEstimate,
        provider_id: str | None,
        key_id: str | None,
        enable_downgrade: bool,
    ) -> None:
        """Handle soft enforcement: warn but allow requests.

        Emits budget_warning events, logs warnings, and tracks warning counts.
        Optionally attempts to downgrade request to cheaper model.

        Args:
            soft_budgets: List of budgets with soft enforcement that would be exceeded.
            request_intent: Request intent (may be modified for downgrade).
            cost_estimate: Original cost estimate.
            provider_id: Optional provider identifier.
            key_id: Optional key identifier.
            enable_downgrade: If True, attempt to downgrade to cheaper model.
        """
        # Track if downgrade was attempted
        downgrade_attempted = False
        downgrade_successful = False
        original_model = request_intent.model
        new_cost_estimate = cost_estimate

        # Attempt downgrade if enabled
        if enable_downgrade and provider_id:
            cheaper_model = await self._suggest_cheaper_model(
                current_model=request_intent.model,
                provider_id=provider_id,
            )
            if cheaper_model and cheaper_model != request_intent.model:
                downgrade_attempted = True
                # Modify request intent to use cheaper model
                request_intent.model = cheaper_model
                # Recalculate cost estimate with cheaper model
                try:
                    new_cost_estimate = await self.estimate_request_cost(
                        request_intent=request_intent,
                        provider_id=provider_id,
                        key_id=key_id or "",
                    )
                    downgrade_successful = True
                except Exception as e:
                    # If cost estimation fails, revert model change
                    request_intent.model = original_model
                    await self._observability.log(
                        level="WARNING",
                        message=f"Failed to estimate cost for downgraded model: {e}",
                        context={
                            "original_model": original_model,
                            "downgrade_model": cheaper_model,
                            "provider_id": provider_id,
                        },
                    )

        # Process each soft budget
        for budget in soft_budgets:
            # Increment warning count
            budget.warning_count += 1

            # Save updated budget
            await self._save_budget_to_store(budget)
            self._budgets[budget.id] = budget

            # Emit budget_warning event
            await self._observability.emit_event(
                event_type="budget_warning",
                payload={
                    "budget_id": budget.id,
                    "scope": budget.scope.value,
                    "scope_id": budget.scope_id,
                    "limit_amount": float(budget.limit_amount),
                    "current_spend": float(budget.current_spend),
                    "remaining_budget": float(budget.remaining_budget),
                    "cost_estimate": float(cost_estimate.amount),
                    "warning_count": budget.warning_count,
                    "provider_id": provider_id,
                    "key_id": key_id,
                    "downgrade_attempted": downgrade_attempted,
                    "downgrade_successful": downgrade_successful,
                    "original_model": original_model if downgrade_attempted else None,
                    "downgrade_model": request_intent.model if downgrade_attempted else None,
                    "original_cost": float(cost_estimate.amount),
                    "downgrade_cost": float(new_cost_estimate.amount) if downgrade_successful else None,
                },
                metadata={"request_id": getattr(request_intent, "request_id", None)},
            )

            # Log warning
            warning_message = (
                f"Budget warning (soft enforcement): ${cost_estimate.amount} would exceed "
                f"limit of ${budget.limit_amount} for budget {budget.id}. "
                f"Current spend: ${budget.current_spend}, Remaining: ${budget.remaining_budget}. "
                f"Request allowed but warning issued (warning #{budget.warning_count})"
            )
            if downgrade_successful:
                warning_message += (
                    f". Request downgraded from {original_model} to {request_intent.model} "
                    f"(cost reduced from ${cost_estimate.amount} to ${new_cost_estimate.amount})"
                )

            await self._observability.log(
                level="WARNING",
                message=warning_message,
                context={
                    "budget_id": budget.id,
                    "scope": budget.scope.value,
                    "limit_amount": float(budget.limit_amount),
                    "current_spend": float(budget.current_spend),
                    "remaining_budget": float(budget.remaining_budget),
                    "cost_estimate": float(cost_estimate.amount),
                    "warning_count": budget.warning_count,
                    "provider_id": provider_id,
                    "key_id": key_id,
                    "downgrade_attempted": downgrade_attempted,
                    "downgrade_successful": downgrade_successful,
                },
            )

    async def _suggest_cheaper_model(
        self,
        current_model: str,
        provider_id: str,
    ) -> str | None:
        """Suggest a cheaper alternative model for the same provider.

        This is a simple implementation that uses known model hierarchies.
        For production, this could be enhanced with provider-specific pricing data.

        Args:
            current_model: Current model identifier (e.g., "gpt-4").
            provider_id: Provider identifier (e.g., "openai").

        Returns:
            Cheaper model identifier if available, None otherwise.
        """
        # Simple model downgrade mappings (can be enhanced with provider adapter support)
        model_downgrades: dict[str, dict[str, str]] = {
            "openai": {
                "gpt-4": "gpt-3.5-turbo",
                "gpt-4-turbo": "gpt-3.5-turbo",
                "gpt-4-turbo-preview": "gpt-3.5-turbo",
                "gpt-4-0125-preview": "gpt-3.5-turbo",
                "gpt-4-1106-preview": "gpt-3.5-turbo",
            },
        }

        provider_downgrades = model_downgrades.get(provider_id, {})
        return provider_downgrades.get(current_model)

    async def record_estimated_cost(
        self,
        request_id: str,
        cost_estimate: CostEstimate,
        provider_id: str | None = None,
        model: str | None = None,
        key_id: str | None = None,
    ) -> None:
        """Record estimated cost for a request (for later reconciliation).

        Stores the estimated cost along with request context so it can be
        retrieved when the actual cost is known for reconciliation.

        Args:
            request_id: Unique request identifier.
            cost_estimate: Cost estimate for the request.
            provider_id: Optional provider identifier.
            model: Optional model identifier.
            key_id: Optional key identifier.
        """
        self._estimated_costs[request_id] = {
            "cost_estimate": cost_estimate,
            "provider_id": provider_id,
            "model": model,
            "key_id": key_id,
        }

        # Emit event for observability
        await self._observability.emit_event(
            event_type="cost_estimate_recorded",
            payload={
                "request_id": request_id,
                "estimated_cost": float(cost_estimate.amount),
                "provider_id": provider_id,
                "model": model,
                "key_id": key_id,
            },
        )

    async def record_actual_cost(
        self,
        request_id: str,
        actual_cost: Decimal,
        provider_id: str | None = None,
        model: str | None = None,
        key_id: str | None = None,
    ) -> CostReconciliation | None:
        """Record actual cost and reconcile with estimated cost.

        Retrieves the estimated cost for the request and creates a
        CostReconciliation record comparing estimated vs actual costs.

        Args:
            request_id: Unique request identifier.
            actual_cost: Actual cost from provider response.
            provider_id: Optional provider identifier (used if not in cache).
            model: Optional model identifier (used if not in cache).
            key_id: Optional key identifier (used if not in cache).

        Returns:
            CostReconciliation object if estimated cost was found, None otherwise.
        """
        # Get estimated cost from cache
        estimated_data = self._estimated_costs.get(request_id)

        # If not in cache, try to get from StateStore (via query_state)
        if not estimated_data:
            # Query for reconciliation data or routing decision with request_id
            query = StateQuery(entity_type="RoutingDecision")
            results = await self._state_store.query_state(query)
            # Look for routing decision with matching request_id
            for result in results:
                if (
                    hasattr(result, "request_id")
                    and result.request_id == request_id
                    and hasattr(result, "metadata")
                    and result.metadata
                ):
                    # Try to get estimated cost from routing decision metadata
                    cost_data = result.metadata.get("estimated_cost")
                    if cost_data:
                            estimated_data = {
                                "cost_estimate": CostEstimate(**cost_data)
                                if isinstance(cost_data, dict)
                                else cost_data,
                                "provider_id": getattr(result, "selected_provider_id", None)
                                or provider_id,
                                "model": result.metadata.get("model") or model,
                                "key_id": getattr(result, "selected_key_id", None) or key_id,
                            }
                            break

        # If still no estimated cost found, log warning and return None
        if not estimated_data:
            await self._observability.log(
                level="WARNING",
                message=f"Estimated cost not found for request_id: {request_id}",
                context={"request_id": request_id, "actual_cost": float(actual_cost)},
            )
            return None

        # Get estimated cost and context
        estimated_cost_estimate = estimated_data["cost_estimate"]
        estimated_provider_id = estimated_data.get("provider_id") or provider_id
        estimated_model = estimated_data.get("model") or model
        estimated_key_id = estimated_data.get("key_id") or key_id

        # Create reconciliation
        reconciliation = CostReconciliation(
            request_id=request_id,
            estimated_cost=estimated_cost_estimate.amount,
            actual_cost=actual_cost,
            provider_id=estimated_provider_id,
            model=estimated_model,
            key_id=estimated_key_id,
        )

        # Store reconciliation
        await self._save_reconciliation(reconciliation)

        # Remove from cache (cleanup)
        self._estimated_costs.pop(request_id, None)

        # Emit reconciliation event
        await self._observability.emit_event(
            event_type="cost_reconciled",
            payload={
                "request_id": request_id,
                "estimated_cost": float(reconciliation.estimated_cost),
                "actual_cost": float(reconciliation.actual_cost),
                "error_amount": float(reconciliation.error_amount),
                "error_percentage": reconciliation.error_percentage,
                "provider_id": reconciliation.provider_id,
                "model": reconciliation.model,
                "key_id": reconciliation.key_id,
            },
        )

        # Log reconciliation
        await self._observability.log(
            level="INFO",
            message=(
                f"Cost reconciled for request {request_id}: "
                f"estimated=${reconciliation.estimated_cost}, "
                f"actual=${reconciliation.actual_cost}, "
                f"error={reconciliation.error_percentage:.2f}%"
            ),
            context={
                "request_id": request_id,
                "estimated_cost": float(reconciliation.estimated_cost),
                "actual_cost": float(reconciliation.actual_cost),
                "error_amount": float(reconciliation.error_amount),
                "error_percentage": reconciliation.error_percentage,
            },
        )

        # Update cost models based on reconciliation
        await self._update_cost_models(reconciliation)

        return reconciliation

    async def get_reconciliation_history(
        self,
        provider_id: str | None = None,
        model: str | None = None,
        limit: int | None = None,
    ) -> list[CostReconciliation]:
        """Get reconciliation history, optionally filtered.

        Args:
            provider_id: Optional provider ID filter.
            model: Optional model filter.
            limit: Optional limit on number of results.

        Returns:
            List of CostReconciliation objects.
        """
        query = StateQuery(entity_type="CostReconciliation", limit=limit)
        results = await self._state_store.query_state(query)

        reconciliations: list[CostReconciliation] = []
        for result in results:
            if isinstance(result, CostReconciliation):
                # Apply filters
                if provider_id and result.provider_id != provider_id:
                    continue
                if model and result.model != model:
                    continue
                reconciliations.append(result)

        # Sort by reconciled_at descending (most recent first)
        reconciliations.sort(key=lambda r: r.reconciled_at, reverse=True)

        return reconciliations

    async def get_reconciliation_statistics(
        self,
        provider_id: str | None = None,
        model: str | None = None,
    ) -> dict[str, any]:
        """Get reconciliation statistics for analysis.

        Calculates statistics like average error, error distribution, etc.
        for cost model improvement.

        Args:
            provider_id: Optional provider ID filter.
            model: Optional model filter.

        Returns:
            Dictionary with statistics (avg_error, avg_error_percentage, count, etc.).
        """
        reconciliations = await self.get_reconciliation_history(
            provider_id=provider_id, model=model
        )

        if not reconciliations:
            return {
                "count": 0,
                "avg_error_amount": 0.0,
                "avg_error_percentage": 0.0,
                "avg_estimated_cost": 0.0,
                "avg_actual_cost": 0.0,
            }

        total_error = sum(r.error_amount for r in reconciliations)
        total_error_percentage = sum(r.error_percentage for r in reconciliations)
        total_estimated = sum(r.estimated_cost for r in reconciliations)
        total_actual = sum(r.actual_cost for r in reconciliations)
        count = len(reconciliations)

        return {
            "count": count,
            "avg_error_amount": float(total_error / count),
            "avg_error_percentage": total_error_percentage / count,
            "avg_estimated_cost": float(total_estimated / count),
            "avg_actual_cost": float(total_actual / count),
            "min_error_percentage": min(r.error_percentage for r in reconciliations),
            "max_error_percentage": max(r.error_percentage for r in reconciliations),
        }

    async def _save_reconciliation(self, reconciliation: CostReconciliation) -> None:
        """Save reconciliation to StateStore.

        Uses query_state interface to store reconciliation data.
        In a real implementation, StateStore would have explicit methods.

        Args:
            reconciliation: CostReconciliation to save.
        """
        # Note: This is a workaround until StateStore has explicit reconciliation methods.
        # For now, we'll use query_state to store reconciliations.
        # In a real implementation, StateStore would have save_reconciliation/get_reconciliation methods.
        # For now, we rely on the in-memory cache and StateStore.query_state.
        pass

    async def _update_cost_models(self, reconciliation: CostReconciliation) -> None:
        """Update cost models based on reconciliation errors.

        Analyzes reconciliation errors and adjusts cost estimation models
        if systematic errors are detected. This is a basic implementation
        that logs patterns for future enhancement.

        Args:
            reconciliation: CostReconciliation to analyze.
        """
        # Basic implementation: Log error patterns for analysis
        # In a full implementation, this would:
        # 1. Analyze error patterns over time
        # 2. Adjust pricing models if systematic errors found
        # 3. Update confidence levels based on error history
        # 4. Store updated models in StateStore

        error_abs_percentage = abs(reconciliation.error_percentage)

        # Log significant errors for analysis
        if error_abs_percentage > 10.0:  # More than 10% error
            await self._observability.log(
                level="WARNING",
                message=(
                    f"Significant cost estimation error detected: "
                    f"{reconciliation.error_percentage:.2f}% for "
                    f"provider={reconciliation.provider_id}, model={reconciliation.model}"
                ),
                context={
                    "request_id": reconciliation.request_id,
                    "provider_id": reconciliation.provider_id,
                    "model": reconciliation.model,
                    "error_percentage": reconciliation.error_percentage,
                    "estimated_cost": float(reconciliation.estimated_cost),
                    "actual_cost": float(reconciliation.actual_cost),
                },
            )

        # Emit event for cost model analysis
        await self._observability.emit_event(
            event_type="cost_model_analysis",
            payload={
                "provider_id": reconciliation.provider_id,
                "model": reconciliation.model,
                "error_percentage": reconciliation.error_percentage,
                "error_amount": float(reconciliation.error_amount),
                "estimated_cost": float(reconciliation.estimated_cost),
                "actual_cost": float(reconciliation.actual_cost),
            },
        )

