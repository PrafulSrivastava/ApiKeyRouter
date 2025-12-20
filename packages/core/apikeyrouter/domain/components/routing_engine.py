"""RoutingEngine component for intelligent API key routing."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from apikeyrouter.domain.components.cost_controller import CostController
from apikeyrouter.domain.components.key_manager import KeyManager
from apikeyrouter.domain.components.policy_engine import PolicyEngine
from apikeyrouter.domain.components.quota_awareness_engine import QuotaAwarenessEngine
from apikeyrouter.domain.components.routing_strategies.cost_optimized import (
    CostOptimizedStrategy,
)
from apikeyrouter.domain.components.routing_strategies.fairness import (
    FairnessStrategy,
)
from apikeyrouter.domain.components.routing_strategies.reliability_optimized import (
    ReliabilityOptimizedStrategy,
)
from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.interfaces.state_store import StateStore
from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.domain.models.budget_check_result import BudgetCheckResult
from apikeyrouter.domain.models.cost_estimate import CostEstimate
from apikeyrouter.domain.models.policy import PolicyScope, PolicyType
from apikeyrouter.domain.models.quota_state import CapacityState, QuotaState
from apikeyrouter.domain.models.request_intent import RequestIntent
from apikeyrouter.domain.models.routing_decision import (
    ObjectiveType,
    RoutingDecision,
    RoutingObjective,
)


class NoEligibleKeysError(Exception):
    """Raised when no eligible keys are available for routing."""

    pass


class RoutingEngine:
    """Makes intelligent routing decisions based on explicit objectives.

    RoutingEngine selects API keys for requests using various strategies.
    This implementation provides simple round-robin routing as a baseline.
    """

    def __init__(
        self,
        key_manager: KeyManager,
        state_store: StateStore,
        observability_manager: ObservabilityManager,
        quota_awareness_engine: QuotaAwarenessEngine | None = None,
        providers: dict[str, ProviderAdapter] | None = None,
        policy_engine: PolicyEngine | None = None,
        cost_controller: CostController | None = None,
    ) -> None:
        """Initialize RoutingEngine with dependencies.

        Args:
            key_manager: KeyManager for getting eligible keys.
            state_store: StateStore for routing history (optional for round-robin).
            observability_manager: ObservabilityManager for logging and events.
            quota_awareness_engine: Optional QuotaAwarenessEngine for quota-aware routing.
            providers: Optional dict mapping provider_id to ProviderAdapter for cost estimation.
            policy_engine: Optional PolicyEngine for policy-based routing constraints.
            cost_controller: Optional CostController for cost estimation and budget enforcement.
        """
        self._key_manager = key_manager
        self._state_store = state_store
        self._observability = observability_manager
        self._quota_engine = quota_awareness_engine
        self._providers = providers or {}
        self._policy_engine = policy_engine
        self._cost_controller = cost_controller

        # Initialize routing strategies
        self._cost_strategy = CostOptimizedStrategy(
            observability_manager=observability_manager,
            quota_awareness_engine=quota_awareness_engine,
        )
        self._reliability_strategy = ReliabilityOptimizedStrategy(
            observability_manager=observability_manager,
            quota_awareness_engine=quota_awareness_engine,
        )
        self._fairness_strategy = FairnessStrategy(
            observability_manager=observability_manager,
            quota_awareness_engine=quota_awareness_engine,
        )

        # Track last used key index per provider for round-robin
        # Format: {provider_id: last_key_index}
        self._last_key_indices: dict[str, int] = {}

    async def evaluate_keys(
        self,
        eligible_keys: list[APIKey],
        objective: RoutingObjective,
        request_intent: RequestIntent | None = None,
    ) -> dict[str, float]:
        """Evaluate and score eligible keys based on routing objective.

        Supports single-objective and multi-objective optimization with
        configurable weights.

        Args:
            eligible_keys: List of eligible API keys to evaluate.
            objective: RoutingObjective specifying what to optimize for.
            request_intent: Optional RequestIntent for cost estimation.

        Returns:
            Dictionary mapping key_id to score (higher is better).

        Raises:
            ValueError: If objective type is not supported.
        """
        if not eligible_keys:
            return {}

        # Check if multi-objective optimization is requested
        if objective.weights:
            return await self._calculate_composite_score(
                eligible_keys, objective, request_intent
            )

        # Single-objective optimization (existing behavior)
        primary_objective = objective.primary.lower()

        if primary_objective == ObjectiveType.Cost.value:
            return await self._score_by_cost(eligible_keys, request_intent)
        elif primary_objective == ObjectiveType.Reliability.value:
            return await self._score_by_reliability(eligible_keys, request_intent)
        elif primary_objective == ObjectiveType.Fairness.value:
            return await self._score_by_fairness(eligible_keys, request_intent)
        elif primary_objective == ObjectiveType.Quality.value:
            # Quality scoring not yet implemented, fallback to reliability
            return await self._score_by_reliability(eligible_keys)
        else:
            # Unknown objective, default to fairness
            await self._observability.log(
                level="WARNING",
                message=f"Unknown objective type: {primary_objective}, defaulting to fairness",
                context={"objective": primary_objective},
            )
            return await self._score_by_fairness(eligible_keys)

    async def _score_by_cost(
        self, keys: list[APIKey], request_intent: RequestIntent | None = None
    ) -> dict[str, float]:
        """Score keys by estimated cost (lower cost = higher score).

        Uses CostController if available for accurate cost estimation,
        otherwise falls back to CostOptimizedStrategy or metadata-based scoring.

        Args:
            keys: List of API keys to score.
            request_intent: Optional RequestIntent for cost estimation.

        Returns:
            Dictionary mapping key_id to score (higher is better).
        """
        # Use CostController if available for accurate cost estimation
        if self._cost_controller and request_intent is not None:
            scores: dict[str, float] = {}
            costs: list[Decimal] = []

            # Get cost estimates for each key
            for key in keys:
                try:
                    cost_estimate = await self._cost_controller.estimate_request_cost(
                        request_intent=request_intent,
                        provider_id=key.provider_id,
                        key_id=key.id,
                    )
                    costs.append(cost_estimate.amount)
                except Exception as e:
                    # If cost estimation fails, use fallback
                    await self._observability.log(
                        level="WARNING",
                        message=f"Failed to estimate cost for key {key.id}: {e}",
                        context={"key_id": key.id, "provider_id": key.provider_id},
                    )
                    # Fallback to metadata or default cost
                    cost_value = key.metadata.get("estimated_cost_per_request")
                    if cost_value is not None:
                        try:
                            costs.append(Decimal(str(cost_value)))
                        except (ValueError, TypeError):
                            costs.append(Decimal("0.01"))
                    else:
                        costs.append(Decimal("0.01"))

            if not costs:
                # No costs available, return equal scores
                return {key.id: 1.0 for key in keys}

            # Normalize: lower cost = higher score
            max_cost = max(costs) if costs else Decimal("1.0")
            min_cost = min(costs) if costs else Decimal("0.0")

            if max_cost == min_cost:
                # All costs equal, return equal scores
                return {key.id: 1.0 for key in keys}

            # Score = 1.0 - normalized_cost (so lower cost = higher score)
            for i, key in enumerate(keys):
                normalized_cost = float((costs[i] - min_cost) / (max_cost - min_cost))
                scores[key.id] = 1.0 - normalized_cost

            return scores

        # Fallback to CostOptimizedStrategy if request_intent is available
        if request_intent is not None:
            return await self._cost_strategy.score_keys(
                eligible_keys=keys,
                request_intent=request_intent,
                providers=self._providers if self._providers else None,
            )

        # Fallback to metadata-based scoring (backward compatibility)
        scores: dict[str, float] = {}
        costs: list[float] = []

        # Extract costs from metadata
        for key in keys:
            # Try to get cost from metadata
            cost = key.metadata.get("estimated_cost_per_request")
            if cost is None:
                # Fallback: use a default cost based on state
                # Available keys get lower default cost
                cost = 0.01 if key.state == KeyState.Available else 0.02
            else:
                # Ensure cost is a number
                try:
                    cost = float(cost)
                except (ValueError, TypeError):
                    cost = 0.01  # Default if invalid

            costs.append(cost)

        if not costs:
            # No costs available, return equal scores
            return {key.id: 1.0 for key in keys}

        # Normalize: lower cost = higher score
        # Invert costs so lower cost gets higher score
        max_cost = max(costs) if costs else 1.0
        min_cost = min(costs) if costs else 0.0

        if max_cost == min_cost:
            # All costs equal, return equal scores
            return {key.id: 1.0 for key in keys}

        # Score = 1.0 - normalized_cost (so lower cost = higher score)
        for i, key in enumerate(keys):
            normalized_cost = (costs[i] - min_cost) / (max_cost - min_cost)
            scores[key.id] = 1.0 - normalized_cost

        return scores

    async def _score_by_reliability(
        self, keys: list[APIKey], request_intent: RequestIntent | None = None
    ) -> dict[str, float]:
        """Score keys by reliability (higher success rate = higher score).

        Uses ReliabilityOptimizedStrategy if available, otherwise falls back
        to simple scoring based on success rate and key state.

        Args:
            keys: List of API keys to score.
            request_intent: Optional RequestIntent (not used for reliability).

        Returns:
            Dictionary mapping key_id to score (higher is better).
        """
        # Use ReliabilityOptimizedStrategy
        return await self._reliability_strategy.score_keys(
            eligible_keys=keys,
            request_intent=request_intent,
            providers=self._providers if self._providers else None,
        )

    async def _filter_by_budget(
        self,
        eligible_keys: list[APIKey],
        request_intent_obj: RequestIntent | None,
        provider_id: str,
    ) -> tuple[list[APIKey], dict[str, BudgetCheckResult], dict[str, CostEstimate], list[APIKey]]:
        """Filter eligible keys by budget constraints and get cost estimates.

        Filters out keys that would exceed budget with hard enforcement.
        For soft enforcement, keys are kept but will be penalized in scoring.

        Args:
            eligible_keys: List of eligible API keys to filter.
            request_intent_obj: Optional RequestIntent for cost estimation.
            provider_id: Provider identifier.

        Returns:
            Tuple of:
            - Filtered list of eligible keys (hard enforcement filtered out)
            - Dictionary mapping key_id to BudgetCheckResult
            - Dictionary mapping key_id to CostEstimate
            - List of filtered keys (for explanation)
        """
        if not self._cost_controller or not request_intent_obj:
            # No cost controller or request intent, return all keys
            return eligible_keys, {}, {}, []

        budget_results: dict[str, BudgetCheckResult] = {}
        cost_estimates: dict[str, CostEstimate] = {}
        filtered_keys: list[APIKey] = []
        filtered_eligible_keys: list[APIKey] = []

        # Query cost estimates and budget checks for each key
        for key in eligible_keys:
            try:
                # Get cost estimate
                cost_estimate = await self._cost_controller.estimate_request_cost(
                    request_intent=request_intent_obj,
                    provider_id=key.provider_id,
                    key_id=key.id,
                )
                cost_estimates[key.id] = cost_estimate

                # Check budget
                budget_result = await self._cost_controller.check_budget(
                    request_intent=request_intent_obj,
                    cost_estimate=cost_estimate,
                    provider_id=key.provider_id,
                    key_id=key.id,
                )
                budget_results[key.id] = budget_result

                # Filter out keys that would exceed budget with hard enforcement
                if budget_result.would_exceed:
                    # Check if any violated budgets have hard enforcement
                    violated_budgets = budget_result.violated_budgets
                    if violated_budgets:
                        # Get budget objects to check enforcement mode
                        from apikeyrouter.domain.models.budget import EnforcementMode

                        has_hard_enforcement = False
                        for budget_id in violated_budgets:
                            budget = await self._cost_controller.get_budget(budget_id)
                            if budget and budget.enforcement_mode == EnforcementMode.Hard:
                                has_hard_enforcement = True
                                break

                        if has_hard_enforcement:
                            # Hard enforcement - filter out this key
                            filtered_keys.append(key)
                            continue

                # Keep key (either within budget or soft enforcement)
                filtered_eligible_keys.append(key)
            except Exception as e:
                # If cost estimation or budget check fails, log but don't filter out the key
                # (graceful degradation)
                await self._observability.log(
                    level="WARNING",
                    message=f"Failed to check budget for key {key.id}: {e}",
                    context={"key_id": key.id, "provider_id": provider_id},
                )
                # Include key without budget check (assume it's OK)
                filtered_eligible_keys.append(key)

        return filtered_eligible_keys, budget_results, cost_estimates, filtered_keys

    async def _filter_by_quota_state(
        self, eligible_keys: list[APIKey]
    ) -> tuple[list[APIKey], dict[str, QuotaState], list[APIKey]]:
        """Filter eligible keys by quota state and retrieve quota states.

        Filters out keys with Exhausted capacity state. Optionally filters
        or heavily penalizes Critical keys.

        Args:
            eligible_keys: List of eligible API keys to filter.

        Returns:
            Tuple of:
            - Filtered list of eligible keys (Exhausted and Critical filtered out)
            - Dictionary mapping key_id to QuotaState
            - List of filtered keys (for explanation)
        """
        if not self._quota_engine:
            return eligible_keys, {}, []

        quota_states: dict[str, QuotaState] = {}
        filtered_keys: list[APIKey] = []
        filtered_eligible_keys: list[APIKey] = []

        # Query quota state for each key
        for key in eligible_keys:
            try:
                quota_state = await self._quota_engine.get_quota_state(key.id)
                quota_states[key.id] = quota_state

                # Filter out Exhausted keys
                if quota_state.capacity_state == CapacityState.Exhausted:
                    filtered_keys.append(key)
                    continue

                # Filter out Critical keys (too risky)
                if quota_state.capacity_state == CapacityState.Critical:
                    filtered_keys.append(key)
                    continue

                # Keep keys with Abundant, Constrained, or Recovering states
                filtered_eligible_keys.append(key)
            except Exception as e:
                # If quota state query fails, log but don't filter out the key
                # (graceful degradation)
                await self._observability.log(
                    level="WARNING",
                    message=f"Failed to get quota state for key {key.id}: {e}",
                    context={"key_id": key.id},
                )
                # Include key without quota state (assume it's OK)
                filtered_eligible_keys.append(key)

        return filtered_eligible_keys, quota_states, filtered_keys

    async def _apply_budget_penalties(
        self,
        scores: dict[str, float],
        budget_results: dict[str, BudgetCheckResult],
    ) -> dict[str, float]:
        """Apply budget penalties to scores for soft enforcement.

        Penalizes keys that would exceed budget with soft enforcement
        by reducing their scores.

        Args:
            scores: Dictionary mapping key_id to base score.
            budget_results: Dictionary mapping key_id to BudgetCheckResult.

        Returns:
            Dictionary mapping key_id to adjusted score.
        """
        adjusted_scores = scores.copy()

        for key_id, budget_result in budget_results.items():
            if key_id not in adjusted_scores:
                continue

            if budget_result.would_exceed:
                # Check if any violated budgets have soft enforcement
                violated_budgets = budget_result.violated_budgets
                if violated_budgets:
                    from apikeyrouter.domain.models.budget import EnforcementMode

                    has_soft_enforcement = False
                    for budget_id in violated_budgets:
                        budget = await self._cost_controller.get_budget(budget_id)
                        if budget and budget.enforcement_mode == EnforcementMode.Soft:
                            has_soft_enforcement = True
                            break

                    if has_soft_enforcement and self._cost_controller:
                        # Soft enforcement - penalize score by 30%
                        base_score = adjusted_scores[key_id]
                        adjusted_scores[key_id] = base_score * 0.7
                        # Ensure score stays in valid range
                        adjusted_scores[key_id] = max(0.0, min(1.0, adjusted_scores[key_id]))

        return adjusted_scores

    async def _apply_quota_multipliers(
        self, scores: dict[str, float], quota_states: dict[str, QuotaState]
    ) -> dict[str, float]:
        """Apply capacity state multipliers to routing scores.

        Boosts scores for Abundant keys, penalizes Constrained keys.

        Args:
            scores: Dictionary mapping key_id to base score.
            quota_states: Dictionary mapping key_id to QuotaState.

        Returns:
            Dictionary mapping key_id to adjusted score.
        """
        adjusted_scores = scores.copy()

        for key_id, quota_state in quota_states.items():
            if key_id not in adjusted_scores:
                continue

            base_score = adjusted_scores[key_id]
            capacity_state = quota_state.capacity_state

            # Apply multipliers based on capacity state
            if capacity_state == CapacityState.Abundant:
                # Boost score by 20% for abundant capacity
                adjusted_scores[key_id] = base_score * 1.2
            elif capacity_state == CapacityState.Constrained:
                # Penalize score by 15% for constrained capacity
                adjusted_scores[key_id] = base_score * 0.85
            elif capacity_state == CapacityState.Recovering:
                # Slight penalty for recovering (5%)
                adjusted_scores[key_id] = base_score * 0.95
            # Critical and Exhausted should already be filtered out

            # Ensure score stays in valid range
            adjusted_scores[key_id] = max(0.0, min(1.0, adjusted_scores[key_id]))

        return adjusted_scores

    def _build_explanation(
        self,
        selected_key: APIKey,
        objective: RoutingObjective,
        score: float,
        quota_state: QuotaState | None,
        eligible_count: int,
        filtered_count: int,
        cost_estimate: Any | None = None,
        budget_result: BudgetCheckResult | None = None,
        budget_filtered_count: int = 0,
        objective_scores: dict[str, dict[str, float]] | None = None,
        applied_policies: list[str] | None = None,
        policy_reasons: list[str] | None = None,
    ) -> str:
        """Build human-readable explanation for routing decision.

        Args:
            selected_key: The selected API key.
            objective: The routing objective used.
            score: The score of the selected key.
            quota_state: Optional quota state for the selected key.
            eligible_count: Number of eligible keys considered.
            filtered_count: Number of keys filtered out by quota.
            cost_estimate: Optional cost estimate for cost objective.

        Returns:
            Human-readable explanation string.
        """
        # For cost objective, use strategy's explanation if cost estimate is available
        if (
            objective.primary.lower() == ObjectiveType.Cost.value
            and cost_estimate is not None
        ):
            explanation = self._cost_strategy.generate_explanation(
                selected_key_id=selected_key.id,
                cost_estimate=cost_estimate,
                quota_state=quota_state,
                eligible_count=eligible_count,
                filtered_count=filtered_count,
            )

            # Append budget information if available
            if budget_result:
                if budget_result.would_exceed:
                    explanation += f" Budget warning: request would exceed budget (remaining: ${budget_result.remaining_budget:.2f})."
                else:
                    explanation += f" Within budget constraints (remaining: ${budget_result.remaining_budget:.2f})."

            if budget_filtered_count > 0:
                explanation += f" {budget_filtered_count} key(s) excluded due to budget constraints."

            # Append policy information if available
            if applied_policies:
                policy_info = f" Policies applied: {', '.join(applied_policies)}"
                explanation += policy_info
                if policy_reasons:
                    explanation += f" ({'; '.join(policy_reasons)})"
            return explanation

        # For reliability objective, use strategy's explanation
        if objective.primary.lower() == ObjectiveType.Reliability.value:
            # Calculate success rate for explanation
            total_requests = selected_key.usage_count + selected_key.failure_count
            success_rate = (
                selected_key.usage_count / total_requests
                if total_requests > 0
                else 0.95
            )
            explanation = self._reliability_strategy.generate_explanation(
                selected_key_id=selected_key.id,
                success_rate=success_rate,
                quota_state=quota_state,
                eligible_count=eligible_count,
                filtered_count=filtered_count,
                failure_count=selected_key.failure_count,
                usage_count=selected_key.usage_count,
            )
            # Append policy information if available
            if applied_policies:
                policy_info = f" Policies applied: {', '.join(applied_policies)}"
                explanation += policy_info
                if policy_reasons:
                    explanation += f" ({'; '.join(policy_reasons)})"
            return explanation

        # For fairness objective, use strategy's explanation
        if objective.primary.lower() == ObjectiveType.Fairness.value:
            # Calculate relative usage for explanation
            # Use selected_key.usage_count as proxy (we don't have all keys here)
            # The explanation will show usage_count but relative_usage may be approximate
            relative_usage = None  # Will be calculated if needed
            explanation = self._fairness_strategy.generate_explanation(
                selected_key_id=selected_key.id,
                usage_count=selected_key.usage_count,
                relative_usage=relative_usage,
                quota_state=quota_state,
                eligible_count=eligible_count,
                filtered_count=filtered_count,
                total_usage=0,  # Not available in this context
            )
            # Append policy information if available
            if applied_policies:
                policy_info = f" Policies applied: {', '.join(applied_policies)}"
                explanation += policy_info
                if policy_reasons:
                    explanation += f" ({'; '.join(policy_reasons)})"
            return explanation

        # For multi-objective optimization, generate trade-off explanation
        if objective.weights and objective_scores:
            return self._build_multi_objective_explanation(
                selected_key=selected_key,
                objective=objective,
                composite_score=score,
                quota_state=quota_state,
                eligible_count=eligible_count,
                filtered_count=filtered_count,
                objective_scores=objective_scores,
                cost_estimate=cost_estimate,
                budget_result=budget_result,
                budget_filtered_count=budget_filtered_count,
                applied_policies=applied_policies,
                policy_reasons=policy_reasons,
            )

        # Default explanation for other objectives
        explanation_parts = [
            f"Selected key {selected_key.id} with {objective.primary} score of {score:.4f}"
        ]

        if quota_state:
            explanation_parts.append(
                f"({quota_state.capacity_state.value} quota state)"
            )

        explanation_parts.append(f"(highest among {eligible_count} eligible keys)")

        if filtered_count > 0:
            explanation_parts.append(
                f"({filtered_count} key(s) excluded due to exhausted/critical quota"
            )
            if budget_filtered_count > 0:
                explanation_parts[-1] += f" and {budget_filtered_count} due to budget constraints"
            explanation_parts[-1] += ")"

        # Add policy information if policies were applied
        if applied_policies:
            policy_info = f"Policies applied: {', '.join(applied_policies)}"
            explanation_parts.append(f"({policy_info})")
            if policy_reasons:
                explanation_parts.append(f"Policy reasons: {'; '.join(policy_reasons)}")

        return " ".join(explanation_parts)

    def _build_multi_objective_explanation(
        self,
        selected_key: APIKey,
        objective: RoutingObjective,
        composite_score: float,
        quota_state: QuotaState | None,
        eligible_count: int,
        filtered_count: int,
        objective_scores: dict[str, dict[str, float]],
        cost_estimate: Any | None = None,
        budget_result: BudgetCheckResult | None = None,
        budget_filtered_count: int = 0,
        applied_policies: list[str] | None = None,
        policy_reasons: list[str] | None = None,
    ) -> str:
        """Build explanation for multi-objective routing decision.

        Args:
            selected_key: The selected API key.
            objective: The routing objective with weights.
            composite_score: The composite score of the selected key.
            quota_state: Optional quota state for selected key.
            eligible_count: Number of eligible keys considered.
            filtered_count: Number of keys filtered out by quota.
            objective_scores: Dictionary mapping objective to scores per key.
            cost_estimate: Optional cost estimate for selected key.

        Returns:
            Human-readable explanation string with trade-offs.
        """
        explanation_parts = [f"Selected key {selected_key.id}"]

        # Normalize weights
        normalized_weights = self._normalize_weights(objective.weights)

        # Build trade-off description
        trade_off_parts = []

        # Get selected key's scores for each objective
        selected_scores = {}
        for obj, scores in objective_scores.items():
            if selected_key.id in scores:
                selected_scores[obj] = scores[selected_key.id]

        # Add cost information if available
        if ObjectiveType.Cost.value in normalized_weights:
            weight = normalized_weights[ObjectiveType.Cost.value]
            if cost_estimate:
                trade_off_parts.append(
                    f"cost (${cost_estimate.amount:.6f}, weight: {weight:.0%})"
                )
            elif ObjectiveType.Cost.value in selected_scores:
                trade_off_parts.append(
                    f"cost (score: {selected_scores[ObjectiveType.Cost.value]:.2f}, weight: {weight:.0%})"
                )

        # Add reliability information
        if ObjectiveType.Reliability.value in normalized_weights:
            weight = normalized_weights[ObjectiveType.Reliability.value]
            if ObjectiveType.Reliability.value in selected_scores:
                reliability_score = selected_scores[ObjectiveType.Reliability.value]
                # Estimate success rate from score (approximate)
                estimated_success_rate = reliability_score * 100
                trade_off_parts.append(
                    f"reliability ({estimated_success_rate:.0f}%, weight: {weight:.0%})"
                )

        # Add fairness information
        if ObjectiveType.Fairness.value in normalized_weights:
            weight = normalized_weights[ObjectiveType.Fairness.value]
            if ObjectiveType.Fairness.value in selected_scores:
                fairness_score = selected_scores[ObjectiveType.Fairness.value]
                trade_off_parts.append(
                    f"fairness (score: {fairness_score:.2f}, weight: {weight:.0%})"
                )

        if trade_off_parts:
            explanation_parts.append(f"balancing {', '.join(trade_off_parts)}")

        # Add composite score
        explanation_parts.append(f"with composite score of {composite_score:.4f}")

        # Add quota state
        if quota_state:
            explanation_parts.append(f"({quota_state.capacity_state.value} quota state)")

        explanation_parts.append(f"(best composite score among {eligible_count} eligible keys)")

        if filtered_count > 0:
            explanation_parts.append(
                f"({filtered_count} key(s) excluded due to exhausted quota"
            )
            if budget_filtered_count > 0:
                explanation_parts[-1] += f" and {budget_filtered_count} due to budget constraints"
            explanation_parts[-1] += ")"

        # Add budget information if available
        if budget_result:
            if budget_result.would_exceed:
                explanation_parts.append(
                    f"Budget warning: request would exceed budget (remaining: ${budget_result.remaining_budget:.2f})"
                )
            else:
                explanation_parts.append(
                    f"Within budget constraints (remaining: ${budget_result.remaining_budget:.2f})"
                )

        # Add policy information if policies were applied
        if applied_policies:
            policy_info = f"Policies applied: {', '.join(applied_policies)}"
            explanation_parts.append(f"({policy_info})")
            if policy_reasons:
                explanation_parts.append(f"Policy reasons: {'; '.join(policy_reasons)}")

        return " ".join(explanation_parts)

    async def _score_by_fairness(
        self, keys: list[APIKey], request_intent: RequestIntent | None = None
    ) -> dict[str, float]:
        """Score keys by fairness (less used = higher score).

        Uses FairnessStrategy to balance load across all eligible keys
        by scoring inversely to usage count.

        Args:
            keys: List of API keys to score.
            request_intent: Optional RequestIntent (not used for fairness).

        Returns:
            Dictionary mapping key_id to score (higher is better).
        """
        # Use FairnessStrategy
        return await self._fairness_strategy.score_keys(
            eligible_keys=keys,
            request_intent=request_intent,
            providers=self._providers if self._providers else None,
        )

    def _normalize_weights(self, weights: dict[str, float]) -> dict[str, float]:
        """Normalize weights to sum to 1.0.

        Args:
            weights: Dictionary mapping objective to weight.

        Returns:
            Normalized weights dictionary.
        """
        total_weight = sum(weights.values())
        if total_weight == 0.0:
            # All weights are zero, return equal weights
            return {obj: 1.0 / len(weights) for obj in weights}
        elif total_weight == 1.0:
            # Already normalized
            return weights
        else:
            # Normalize to sum to 1.0
            return {obj: weight / total_weight for obj, weight in weights.items()}

    async def _calculate_composite_score(
        self,
        eligible_keys: list[APIKey],
        objective: RoutingObjective,
        request_intent: RequestIntent | None = None,
    ) -> dict[str, float]:
        """Calculate composite score from multiple objectives with weights.

        Args:
            eligible_keys: List of eligible API keys to evaluate.
            objective: RoutingObjective with weights for multi-objective optimization.
            request_intent: Optional RequestIntent for cost estimation.

        Returns:
            Dictionary mapping key_id to composite score (higher is better).
        """
        if not eligible_keys:
            return {}

        # Normalize weights to sum to 1.0
        normalized_weights = self._normalize_weights(objective.weights)

        # Collect all objectives to evaluate (primary + secondary + weights)
        objectives_to_evaluate = set()
        if objective.primary:
            objectives_to_evaluate.add(objective.primary.lower())
        if objective.secondary:
            objectives_to_evaluate.update(obj.lower() for obj in objective.secondary)
        # Also include objectives from weights dict
        objectives_to_evaluate.update(obj.lower() for obj in normalized_weights)

        # Calculate scores for each objective
        objective_scores: dict[str, dict[str, float]] = {}

        for obj in objectives_to_evaluate:
            if obj == ObjectiveType.Cost.value:
                objective_scores[obj] = await self._score_by_cost(
                    eligible_keys, request_intent
                )
            elif obj == ObjectiveType.Reliability.value:
                objective_scores[obj] = await self._score_by_reliability(
                    eligible_keys, request_intent
                )
            elif obj == ObjectiveType.Fairness.value:
                objective_scores[obj] = await self._score_by_fairness(
                    eligible_keys, request_intent
                )
            elif obj == ObjectiveType.Quality.value:
                # Quality not implemented, fallback to reliability
                objective_scores[obj] = await self._score_by_reliability(
                    eligible_keys, request_intent
                )
            else:
                # Unknown objective, skip it
                await self._observability.log(
                    level="WARNING",
                    message=f"Unknown objective type in weights: {obj}, skipping",
                    context={"objective": obj},
                )
                continue

        # Calculate composite scores: Σ(weight_i * score_i)
        composite_scores: dict[str, float] = {}

        for key in eligible_keys:
            composite_score = 0.0
            for obj, weight in normalized_weights.items():
                if obj in objective_scores and key.id in objective_scores[obj]:
                    composite_score += weight * objective_scores[obj][key.id]
            composite_scores[key.id] = composite_score

        # Normalize composite scores to 0.0-1.0 range
        if composite_scores:
            max_score = max(composite_scores.values())
            min_score = min(composite_scores.values())
            if max_score > min_score:
                # Normalize
                for key_id in composite_scores:
                    composite_scores[key_id] = (composite_scores[key_id] - min_score) / (
                        max_score - min_score
                    )
            elif max_score == min_score and max_score > 0:
                # All scores equal, keep as is
                pass
            else:
                # All scores are 0, set to equal low scores
                for key_id in composite_scores:
                    composite_scores[key_id] = 0.1

        return composite_scores

    async def route_request(
        self,
        request_intent: dict[str, Any],
        objective: RoutingObjective | None = None,
        request_intent_obj: RequestIntent | None = None,
    ) -> RoutingDecision:
        """Route a request to an eligible API key using round-robin strategy.

        Args:
            request_intent: Request information dict containing:
                - provider_id: str (required) - Provider to route to
                - request_id: str (optional) - Request identifier, generated if not provided
            objective: Optional RoutingObjective. If None, defaults to fairness
                (appropriate for round-robin).

        Returns:
            RoutingDecision with selected key and explanation.

        Raises:
            NoEligibleKeysError: If no eligible keys are available.
            ValueError: If request_intent is missing required fields.
        """
        # Extract provider_id from request_intent
        provider_id = request_intent.get("provider_id")
        if not provider_id or not isinstance(provider_id, str):
            raise ValueError("request_intent must contain 'provider_id' (str)")

        # Get or generate request_id
        request_id = request_intent.get("request_id") or str(uuid.uuid4())

        # Default to fairness objective for round-robin
        if objective is None:
            objective = RoutingObjective(primary=ObjectiveType.Fairness.value)

        # Get eligible keys from KeyManager
        eligible_keys = await self._key_manager.get_eligible_keys(provider_id=provider_id)

        if not eligible_keys:
            # Log and emit event for no eligible keys
            await self._observability.log(
                level="WARNING",
                message=f"No eligible keys found for provider {provider_id}",
                context={"provider_id": provider_id, "request_id": request_id},
            )
            await self._observability.emit_event(
                event_type="routing_failed",
                payload={
                    "provider_id": provider_id,
                    "request_id": request_id,
                    "reason": "no_eligible_keys",
                },
            )
            raise NoEligibleKeysError(
                f"No eligible keys available for provider: {provider_id}"
            )

        # Apply quota-aware filtering if QuotaAwarenessEngine is available
        if self._quota_engine is not None:
            eligible_keys, quota_states, quota_filtered_keys = await self._filter_by_quota_state(
                eligible_keys
            )

            if not eligible_keys:
                # All keys filtered out by quota state
                await self._observability.log(
                    level="WARNING",
                    message=f"All keys filtered out by quota state for provider {provider_id}",
                    context={
                        "provider_id": provider_id,
                        "request_id": request_id,
                        "filtered_count": len(quota_filtered_keys),
                    },
                )
                await self._observability.emit_event(
                    event_type="routing_failed",
                    payload={
                        "provider_id": provider_id,
                        "request_id": request_id,
                        "reason": "all_keys_quota_exhausted",
                        "filtered_keys": [k.id for k in quota_filtered_keys],
                    },
                )
                raise NoEligibleKeysError(
                    f"All eligible keys have exhausted quota for provider: {provider_id}"
                )
        else:
            # No quota engine, use all eligible keys without quota filtering
            quota_states = {}
            quota_filtered_keys = []

        # Apply budget-aware filtering if CostController is available
        budget_results: dict[str, BudgetCheckResult] = {}
        cost_estimates: dict[str, CostEstimate] = {}
        budget_filtered_keys: list[APIKey] = []

        if self._cost_controller is not None and request_intent_obj is not None:
            eligible_keys, budget_results, cost_estimates, budget_filtered_keys = (
                await self._filter_by_budget(eligible_keys, request_intent_obj, provider_id)
            )

            if not eligible_keys:
                # All keys filtered out by budget constraints
                await self._observability.log(
                    level="WARNING",
                    message=f"All keys filtered out by budget constraints for provider {provider_id}",
                    context={
                        "provider_id": provider_id,
                        "request_id": request_id,
                        "filtered_count": len(budget_filtered_keys),
                    },
                )
                await self._observability.emit_event(
                    event_type="routing_failed",
                    payload={
                        "provider_id": provider_id,
                        "request_id": request_id,
                        "reason": "all_keys_budget_exceeded",
                        "filtered_keys": [k.id for k in budget_filtered_keys],
                    },
                )
                raise NoEligibleKeysError(
                    f"All eligible keys would exceed budget for provider: {provider_id}"
                )

        # Combine filtered keys for explanation
        filtered_keys = quota_filtered_keys + budget_filtered_keys

        # Apply policy-based filtering if PolicyEngine is available
        policy_filtered_keys: list[APIKey] = []
        applied_policies: list[str] = []
        policy_constraints: dict[str, Any] = {}
        policy_reasons: list[str] = []

        if self._policy_engine is not None:
            # Query applicable policies
            applicable_policies = await self._policy_engine.get_applicable_policies(
                scope=PolicyScope.PerProvider,
                policy_type=PolicyType.Routing,
                scope_id=provider_id,
            )

            # Also check global policies
            global_policies = await self._policy_engine.get_applicable_policies(
                scope=PolicyScope.Global,
                policy_type=PolicyType.Routing,
            )
            applicable_policies.extend(global_policies)

            # Resolve policy conflicts (order by precedence)
            if applicable_policies:
                applicable_policies = await self._policy_engine.resolve_policy_conflicts(
                    applicable_policies
                )

            # Evaluate each policy and accumulate results
            for policy in applicable_policies:
                if not policy.enabled:
                    continue

                # Build context for policy evaluation
                context = {
                    "eligible_keys": eligible_keys,
                    "request_intent": request_intent_obj,
                    "provider_id": provider_id,
                    "request_id": request_id,
                }

                # Evaluate policy
                policy_result = await self._policy_engine.evaluate_policy(policy, context)

                # Check if routing is allowed
                if not policy_result.allowed:
                    # Policy rejects routing
                    await self._observability.log(
                        level="WARNING",
                        message=f"Policy {policy.id} rejected routing",
                        context={
                            "policy_id": policy.id,
                            "provider_id": provider_id,
                            "request_id": request_id,
                            "reason": policy_result.reason,
                        },
                    )
                    raise NoEligibleKeysError(
                        f"Policy {policy.id} rejected routing: {policy_result.reason}"
                    )

                # Accumulate filtered keys
                policy_filtered_keys.extend(
                    [k for k in eligible_keys if k.id in policy_result.filtered_keys]
                )

                # Accumulate constraints
                policy_constraints.update(policy_result.constraints)

                # Track applied policies
                applied_policies.extend(policy_result.applied_policies)

                if policy_result.reason:
                    policy_reasons.append(f"{policy.name}: {policy_result.reason}")

            # Remove policy-filtered keys from eligible_keys
            if policy_filtered_keys:
                filtered_key_ids = {k.id for k in policy_filtered_keys}
                eligible_keys = [k for k in eligible_keys if k.id not in filtered_key_ids]
                filtered_keys.extend(policy_filtered_keys)

                if not eligible_keys:
                    # All keys filtered out by policies
                    await self._observability.log(
                        level="WARNING",
                        message=f"All keys filtered out by policies for provider {provider_id}",
                        context={
                            "provider_id": provider_id,
                            "request_id": request_id,
                            "filtered_count": len(policy_filtered_keys),
                            "policies": applied_policies,
                        },
                    )
                    await self._observability.emit_event(
                        event_type="routing_failed",
                        payload={
                            "provider_id": provider_id,
                            "request_id": request_id,
                            "reason": "all_keys_policy_filtered",
                            "filtered_keys": [k.id for k in policy_filtered_keys],
                            "policies": applied_policies,
                        },
                    )
                    raise NoEligibleKeysError(
                        f"All eligible keys filtered by policies for provider: {provider_id}"
                    )

            # Apply policy constraints to objective if needed
            if policy_constraints:
                # Merge constraints into objective (create new objective since it's frozen)
                merged_constraints = dict(objective.constraints) if objective.constraints else {}
                merged_constraints.update(policy_constraints)
                objective = RoutingObjective(
                    primary=objective.primary,
                    secondary=objective.secondary,
                    constraints=merged_constraints,
                    weights=objective.weights,
                )

        # Objective-based routing: evaluate and select best key
        # This includes fairness, which scores keys inversely to usage count
        strategy = f"objective_based_{objective.primary}"

        # Store objective scores for multi-objective explanation
        objective_scores_for_explanation: dict[str, dict[str, float]] = {}

        # Check if multi-objective optimization
        if objective.weights:
            # For multi-objective, we need to get individual objective scores
            normalized_weights = self._normalize_weights(objective.weights)
            objectives_to_evaluate = set()
            if objective.primary:
                objectives_to_evaluate.add(objective.primary.lower())
            if objective.secondary:
                objectives_to_evaluate.update(obj.lower() for obj in objective.secondary)
            objectives_to_evaluate.update(obj.lower() for obj in normalized_weights)

            # Get scores for each objective
            for obj in objectives_to_evaluate:
                if obj == ObjectiveType.Cost.value:
                    objective_scores_for_explanation[obj] = await self._score_by_cost(
                        eligible_keys, request_intent_obj
                    )
                elif obj == ObjectiveType.Reliability.value:
                    objective_scores_for_explanation[obj] = await self._score_by_reliability(
                        eligible_keys, request_intent_obj
                    )
                elif obj == ObjectiveType.Fairness.value:
                    objective_scores_for_explanation[obj] = await self._score_by_fairness(
                        eligible_keys, request_intent_obj
                    )

        scores = await self.evaluate_keys(eligible_keys, objective, request_intent_obj)

        # Apply budget penalties for soft enforcement if cost controller is available
        if self._cost_controller is not None and budget_results:
            scores = await self._apply_budget_penalties(scores, budget_results)

        # Apply quota state multipliers to scores if quota engine is available
        if self._quota_engine is not None and quota_states:
            scores = await self._apply_quota_multipliers(scores, quota_states)

        # Select key with highest score
        # If multiple keys have the same highest score, use round-robin for fairness
        max_score = max(scores.values()) if scores else 0.0
        keys_with_max_score = [key_id for key_id, score in scores.items() if score == max_score]

        if len(keys_with_max_score) > 1 and objective.primary == ObjectiveType.Fairness.value:
            # Multiple keys tied for highest score - use round-robin
            last_index = self._last_key_indices.get(provider_id, -1)
            # Find the index of the last selected key in the tied keys list
            if last_index >= 0:
                try:
                    last_key_id = eligible_keys[last_index].id
                    if last_key_id in keys_with_max_score:
                        last_tied_index = keys_with_max_score.index(last_key_id)
                        next_tied_index = (last_tied_index + 1) % len(keys_with_max_score)
                    else:
                        next_tied_index = 0
                except (IndexError, ValueError):
                    next_tied_index = 0
            else:
                next_tied_index = 0

            selected_key_id = keys_with_max_score[next_tied_index]
            # Update last used index to the actual key's position in eligible_keys
            selected_key = next(k for k in eligible_keys if k.id == selected_key_id)
            selected_index = eligible_keys.index(selected_key)
            self._last_key_indices[provider_id] = selected_index
        else:
            # Single best key or not fairness objective - select highest score
            selected_key_id = max(scores, key=scores.get)
            selected_key = next(k for k in eligible_keys if k.id == selected_key_id)
            # Update last used index for potential future round-robin
            selected_index = eligible_keys.index(selected_key)
            self._last_key_indices[provider_id] = selected_index

        selected_score = scores[selected_key_id]

        # Verify selected key is within budget (final check)
        if self._cost_controller and request_intent_obj and selected_key.id in budget_results:
            selected_budget_check = budget_results[selected_key.id]
            if selected_budget_check.would_exceed:
                # Check if hard enforcement would reject this
                from apikeyrouter.domain.models.budget import EnforcementMode
                violated_budgets = selected_budget_check.violated_budgets
                for budget_id in violated_budgets:
                    budget = await self._cost_controller.get_budget(budget_id)
                    if budget and budget.enforcement_mode == EnforcementMode.Hard:
                        # This should not happen if filtering worked correctly, but log warning
                        await self._observability.log(
                            level="WARNING",
                            message=f"Selected key {selected_key.id} would exceed hard budget enforcement",
                            context={
                                "key_id": selected_key.id,
                                "provider_id": provider_id,
                                "request_id": request_id,
                                "violated_budgets": violated_budgets,
                            },
                        )

        # Get quota state for selected key (for explanation)
        selected_quota_state = quota_states.get(selected_key.id) if quota_states else None

        # Create RoutingDecision
        decision_id = str(uuid.uuid4())
        decision_timestamp = datetime.utcnow()

        # Build eligible key IDs list (include filtered keys for transparency)
        eligible_key_ids = [key.id for key in eligible_keys]
        if filtered_keys:
            eligible_key_ids.extend([key.id for key in filtered_keys])

        # Get cost estimate for selected key (for explanation)
        cost_estimate = None
        selected_budget_result = None

        if selected_key.id in cost_estimates:
            # Use cost estimate from budget filtering
            cost_estimate = cost_estimates[selected_key.id]
            selected_budget_result = budget_results.get(selected_key.id)
        elif (
            objective.primary.lower() == ObjectiveType.Cost.value
            and request_intent_obj is not None
            and self._cost_controller
        ):
            # Try to get cost estimate from CostController
            try:
                cost_estimate = await self._cost_controller.estimate_request_cost(
                    request_intent=request_intent_obj,
                    provider_id=selected_key.provider_id,
                    key_id=selected_key.id,
                )
                selected_budget_result = await self._cost_controller.check_budget(
                    request_intent=request_intent_obj,
                    cost_estimate=cost_estimate,
                    provider_id=selected_key.provider_id,
                    key_id=selected_key.id,
                )
            except Exception:
                # If cost estimation fails, try adapter fallback
                if self._providers and selected_key.provider_id in self._providers:
                    try:
                        adapter = self._providers[selected_key.provider_id]
                        cost_estimate = await adapter.estimate_cost(request_intent_obj)
                    except Exception:
                        # If cost estimation fails, continue without cost info
                        pass

        explanation = self._build_explanation(
            selected_key,
            objective,
            selected_score,
            selected_quota_state,
            len(eligible_keys),
            len(filtered_keys),
            cost_estimate=cost_estimate,
            budget_result=selected_budget_result,
            budget_filtered_count=len(budget_filtered_keys),
            objective_scores=objective_scores_for_explanation if objective.weights else None,
            applied_policies=applied_policies if self._policy_engine else None,
            policy_reasons=policy_reasons if self._policy_engine else None,
        )

        # Create evaluation results with scores, quota states, and cost information
        evaluation_results = {}
        for key_id, score in scores.items():
            result = {"score": score}
            if quota_states and key_id in quota_states:
                result["quota_state"] = quota_states[key_id].capacity_state.value

            # Include cost information if available
            if key_id in cost_estimates:
                result["cost_estimate"] = float(cost_estimates[key_id].amount)
            if key_id in budget_results:
                budget_result = budget_results[key_id]
                result["budget_check"] = {
                    "allowed": budget_result.allowed,
                    "would_exceed": budget_result.would_exceed,
                    "remaining_budget": float(budget_result.remaining_budget),
                }

            # Include per-objective scores for multi-objective optimization
            if objective.weights and objective_scores_for_explanation:
                result["objective_scores"] = {}
                for obj, obj_scores in objective_scores_for_explanation.items():
                    if key_id in obj_scores:
                        result["objective_scores"][obj] = obj_scores[key_id]

            evaluation_results[key_id] = result

        # Create RoutingDecision
        decision = RoutingDecision(
            id=decision_id,
            request_id=request_id,
            selected_key_id=selected_key.id,
            selected_provider_id=selected_key.provider_id,
            decision_timestamp=decision_timestamp,
            objective=objective,
            eligible_keys=eligible_key_ids,
            evaluation_results=evaluation_results,
            explanation=explanation,
            confidence=0.9,  # Objective-based routing has some uncertainty
            alternatives_considered=[],  # Could be enhanced in future
        )

        # Log routing decision
        await self._observability.log(
            level="INFO",
            message=f"Routing decision made: {selected_key.id}",
            context={
                "decision_id": decision_id,
                "request_id": request_id,
                "provider_id": provider_id,
                "selected_key_id": selected_key.id,
                "eligible_keys_count": len(eligible_keys),
            },
        )

        # Emit routing_decision event
        await self._observability.emit_event(
            event_type="routing_decision",
            payload={
                "decision_id": decision_id,
                "request_id": request_id,
                "provider_id": provider_id,
                "selected_key_id": selected_key.id,
                "objective": objective.primary,
                "strategy": strategy,
            },
            metadata={
                "decision_timestamp": decision_timestamp.isoformat(),
                "eligible_keys_count": len(eligible_keys),
            },
        )

        return decision

    def explain_decision(self, decision: RoutingDecision) -> str:
        """Generate a detailed, human-readable explanation of a routing decision.

        Creates a structured explanation that includes the objective, selected key,
        scores, alternatives, quota state, and reasoning for the decision.

        Args:
            decision: The RoutingDecision to explain.

        Returns:
            Formatted human-readable explanation string.
        """
        lines: list[str] = []

        # Header
        lines.append("=" * 60)
        lines.append("ROUTING DECISION EXPLANATION")
        lines.append("=" * 60)
        lines.append("")

        # Objective Section
        lines.append("OBJECTIVE:")
        lines.append(f"  Primary: {decision.objective.primary}")
        if decision.objective.secondary:
            lines.append(f"  Secondary: {', '.join(decision.objective.secondary)}")
        if decision.objective.constraints:
            constraints_str = ", ".join(
                f"{k}={v}" for k, v in decision.objective.constraints.items()
            )
            lines.append(f"  Constraints: {constraints_str}")
        if decision.objective.weights:
            weights_str = ", ".join(
                f"{k}={v:.2f}" for k, v in decision.objective.weights.items()
            )
            lines.append(f"  Weights: {weights_str}")
        lines.append("")

        # Selection Section
        lines.append("SELECTED KEY:")
        lines.append(f"  Key ID: {decision.selected_key_id}")
        lines.append(f"  Provider: {decision.selected_provider_id}")
        lines.append(f"  Confidence: {decision.confidence:.2%}")
        lines.append(f"  Decision Time: {decision.decision_timestamp.isoformat()}")
        lines.append("")

        # Reasoning Section
        lines.append("REASONING:")
        if decision.evaluation_results:
            # Get selected key score
            selected_score = decision.evaluation_results.get(decision.selected_key_id, {})
            score_value = selected_score.get("score") if isinstance(selected_score, dict) else None

            if score_value is not None:
                lines.append(
                    f"  Selected key has the highest {decision.objective.primary} score: {score_value:.4f}"
                )

                # Compare to alternatives
                other_scores = [
                    (key_id, result.get("score"))
                    for key_id, result in decision.evaluation_results.items()
                    if key_id != decision.selected_key_id
                    and isinstance(result, dict)
                    and result.get("score") is not None
                ]

                if other_scores:
                    # Find closest competitor
                    other_scores.sort(key=lambda x: x[1] if x[1] is not None else 0.0, reverse=True)
                    closest_key_id, closest_score = other_scores[0]
                    score_diff = score_value - (closest_score if closest_score is not None else 0.0)
                    lines.append(
                        f"  Margin over closest alternative ({closest_key_id}): {score_diff:.4f}"
                    )
            else:
                lines.append("  Selected using round-robin strategy (fairness objective)")
        else:
            lines.append("  Selected using round-robin strategy")

        # Quota state reasoning
        if decision.evaluation_results:
            selected_result = decision.evaluation_results.get(decision.selected_key_id, {})
            if isinstance(selected_result, dict) and "quota_state" in selected_result:
                quota_state = selected_result["quota_state"]
                lines.append(f"  Quota state: {quota_state}")
                if quota_state == "abundant":
                    lines.append("    → Abundant capacity provides reliability buffer")
                elif quota_state == "constrained":
                    lines.append("    → Constrained capacity (score penalized by 15%)")
                elif quota_state == "recovering":
                    lines.append("    → Recovering from exhaustion (score penalized by 5%)")

        lines.append("")

        # Evaluation Results Section
        if decision.evaluation_results:
            lines.append("EVALUATION RESULTS:")
            # Sort by score (descending)
            sorted_results = sorted(
                decision.evaluation_results.items(),
                key=lambda x: (
                    x[1].get("score") if isinstance(x[1], dict) and x[1].get("score") is not None else 0.0
                ),
                reverse=True,
            )

            for rank, (key_id, result) in enumerate(sorted_results, 1):
                if not isinstance(result, dict):
                    continue

                score = result.get("score")
                quota_state = result.get("quota_state")

                line_parts = [f"  {rank}. Key {key_id}"]
                if score is not None:
                    line_parts.append(f"Score: {score:.4f}")
                if quota_state:
                    line_parts.append(f"Quota: {quota_state}")

                marker = " ← SELECTED" if key_id == decision.selected_key_id else ""
                lines.append(" ".join(line_parts) + marker)

            lines.append("")

        # Alternatives Considered Section
        if decision.alternatives_considered:
            lines.append("ALTERNATIVES CONSIDERED:")
            for alt in decision.alternatives_considered:
                lines.append(f"  • Key {alt.key_id} (Provider: {alt.provider_id})")
                if alt.score is not None:
                    lines.append(f"    Score: {alt.score:.4f}")
                if alt.reason_not_selected:
                    lines.append(f"    Reason: {alt.reason_not_selected}")
            lines.append("")

        # Eligible Keys Section
        if decision.eligible_keys:
            lines.append("ELIGIBLE KEYS:")
            lines.append(f"  Total eligible: {len(decision.eligible_keys)}")
            lines.append(f"  Keys: {', '.join(decision.eligible_keys)}")
            lines.append("")

        # Quota Filtering Section (if applicable)
        if decision.evaluation_results:
            # Check if any keys were filtered (present in eligible_keys but not in evaluation_results)
            filtered_keys = [
                key_id
                for key_id in decision.eligible_keys
                if key_id not in decision.evaluation_results
            ]
            if filtered_keys:
                lines.append("QUOTA FILTERING:")
                lines.append(f"  {len(filtered_keys)} key(s) filtered out due to exhausted/critical quota:")
                for key_id in filtered_keys:
                    lines.append(f"    • {key_id}")
                lines.append("")

        # Summary
        lines.append("SUMMARY:")
        lines.append(f"  {decision.explanation}")
        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

