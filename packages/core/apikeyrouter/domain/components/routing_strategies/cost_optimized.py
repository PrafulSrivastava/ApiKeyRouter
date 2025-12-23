"""Cost-optimized routing strategy implementation."""

from __future__ import annotations

from decimal import Decimal

from apikeyrouter.domain.components.quota_awareness_engine import QuotaAwarenessEngine
from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.api_key import APIKey
from apikeyrouter.domain.models.cost_estimate import CostEstimate
from apikeyrouter.domain.models.quota_state import CapacityState, QuotaState
from apikeyrouter.domain.models.request_intent import RequestIntent


class CostOptimizedStrategy:
    """Routing strategy that optimizes for lowest cost.

    Scores keys by estimated cost (lower cost = higher score), considers
    quota state to avoid exhausted keys, and selects the lowest-cost
    eligible key.
    """

    def __init__(
        self,
        observability_manager: ObservabilityManager,
        quota_awareness_engine: QuotaAwarenessEngine | None = None,
    ) -> None:
        """Initialize CostOptimizedStrategy.

        Args:
            observability_manager: ObservabilityManager for logging.
            quota_awareness_engine: Optional QuotaAwarenessEngine for quota state.
        """
        self._observability = observability_manager
        self._quota_engine = quota_awareness_engine

    async def score_keys(
        self,
        eligible_keys: list[APIKey],
        request_intent: RequestIntent,
        providers: dict[str, ProviderAdapter] | None = None,
    ) -> dict[str, float]:
        """Score keys by estimated cost (lower cost = higher score).

        For each key, gets cost estimate from ProviderAdapter if available,
        otherwise falls back to metadata. Normalizes scores to 0.0-1.0 range.

        Args:
            eligible_keys: List of eligible API keys to score.
            request_intent: RequestIntent for cost estimation.
            providers: Optional dict mapping provider_id to ProviderAdapter.

        Returns:
            Dictionary mapping key_id to score (higher is better, 0.0-1.0).
        """
        if not eligible_keys:
            return {}

        scores: dict[str, float] = {}
        costs: list[Decimal] = []
        cost_estimates: dict[str, CostEstimate] = {}

        # Get cost estimates for each key
        for key in eligible_keys:
            cost_estimate: CostEstimate | None = None

            # Try to get cost estimate from ProviderAdapter
            if providers and key.provider_id in providers:
                try:
                    adapter = providers[key.provider_id]
                    cost_estimate = await adapter.estimate_cost(request_intent)
                    cost_estimates[key.id] = cost_estimate
                    costs.append(cost_estimate.amount)
                except Exception as e:
                    # Log error but continue with fallback
                    await self._observability.log(
                        level="WARNING",
                        message=f"Failed to estimate cost for key {key.id}: {e}",
                        context={"key_id": key.id, "provider_id": key.provider_id},
                    )
                    # Fall through to metadata fallback

            # Fallback to metadata if adapter estimate failed or unavailable
            if cost_estimate is None:
                cost_value = key.metadata.get("estimated_cost_per_request")
                if cost_value is not None:
                    try:
                        cost_decimal = Decimal(str(cost_value))
                        costs.append(cost_decimal)
                    except (ValueError, TypeError):
                        # Invalid cost in metadata, use default
                        costs.append(Decimal("0.01"))
                else:
                    # No cost info available, use default
                    costs.append(Decimal("0.01"))

        if not costs:
            # No costs available, return equal scores
            return {key.id: 1.0 for key in eligible_keys}

        # Normalize: lower cost = higher score
        max_cost = max(costs) if costs else Decimal("1.0")
        min_cost = min(costs) if costs else Decimal("0.0")

        if max_cost == min_cost:
            # All costs equal, return equal scores
            return {key.id: 1.0 for key in eligible_keys}

        # Score = 1.0 - normalized_cost (so lower cost = higher score)
        for cost_index, key in enumerate(eligible_keys):
            cost = costs[cost_index]
            normalized_cost = float((cost - min_cost) / (max_cost - min_cost))
            scores[key.id] = 1.0 - normalized_cost

        return scores

    async def filter_by_quota_state(
        self, eligible_keys: list[APIKey]
    ) -> tuple[list[APIKey], dict[str, QuotaState], list[APIKey]]:
        """Filter eligible keys by quota state.

        Filters out keys with Exhausted capacity state. Returns filtered
        keys, quota states dict, and list of filtered keys.

        Args:
            eligible_keys: List of eligible API keys to filter.

        Returns:
            Tuple of:
            - Filtered list of eligible keys (Exhausted filtered out)
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

                # Keep keys with Abundant, Constrained, Critical, or Recovering states
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

    async def apply_quota_multipliers(
        self, scores: dict[str, float], quota_states: dict[str, QuotaState]
    ) -> dict[str, float]:
        """Apply capacity state multipliers to routing scores.

        Boosts scores for Abundant keys, penalizes Constrained and Critical keys.

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
            elif capacity_state == CapacityState.Critical:
                # Penalize score by 30% for critical capacity
                adjusted_scores[key_id] = base_score * 0.70
            elif capacity_state == CapacityState.Recovering:
                # Slight penalty for recovering (5%)
                adjusted_scores[key_id] = base_score * 0.95
            # Exhausted should already be filtered out

            # Ensure score stays in valid range
            adjusted_scores[key_id] = max(0.0, min(1.0, adjusted_scores[key_id]))

        return adjusted_scores

    def select_key(
        self, scores: dict[str, float], eligible_keys: list[APIKey]
    ) -> tuple[str, float]:
        """Select key with highest score (lowest cost).

        Args:
            scores: Dictionary mapping key_id to score.
            eligible_keys: List of eligible API keys.

        Returns:
            Tuple of (selected_key_id, score).

        Raises:
            ValueError: If no scores available or no eligible keys.
        """
        if not scores:
            raise ValueError("No scores available for key selection")

        if not eligible_keys:
            raise ValueError("No eligible keys available for selection")

        # Select key with highest score (lowest cost)
        max_score = max(scores.values())
        keys_with_max_score = [key_id for key_id, score in scores.items() if score == max_score]

        # Handle ties: select first key (deterministic)
        selected_key_id = keys_with_max_score[0]

        return selected_key_id, max_score

    def generate_explanation(
        self,
        selected_key_id: str,
        cost_estimate: CostEstimate | None,
        quota_state: QuotaState | None,
        eligible_count: int,
        filtered_count: int,
        alternative_costs: dict[str, Decimal] | None = None,
    ) -> str:
        """Generate human-readable explanation for routing decision.

        Args:
            selected_key_id: The selected API key ID.
            cost_estimate: Optional cost estimate for selected key.
            quota_state: Optional quota state for selected key.
            eligible_count: Number of eligible keys considered.
            filtered_count: Number of keys filtered out by quota.
            alternative_costs: Optional dict mapping key_id to cost for alternatives.

        Returns:
            Human-readable explanation string.
        """
        explanation_parts = [f"Selected key {selected_key_id}"]

        # Include cost information
        if cost_estimate:
            explanation_parts.append(f"with lowest estimated cost of ${cost_estimate.amount:.6f}")
        else:
            explanation_parts.append("with lowest estimated cost")

        # Include quota state
        if quota_state:
            explanation_parts.append(f"({quota_state.capacity_state.value} quota state)")

        # Include cost comparison with alternatives
        if alternative_costs and len(alternative_costs) > 1:
            sorted_costs = sorted(alternative_costs.items(), key=lambda x: x[1])
            if sorted_costs[0][0] == selected_key_id and len(sorted_costs) > 1:
                next_cheapest_key, next_cheapest_cost = sorted_costs[1]
                savings = next_cheapest_cost - alternative_costs[selected_key_id]
                explanation_parts.append(
                    f"(saves ${savings:.6f} vs next cheapest key {next_cheapest_key})"
                )

        explanation_parts.append(f"(highest score among {eligible_count} eligible keys)")

        if filtered_count > 0:
            explanation_parts.append(f"({filtered_count} key(s) excluded due to exhausted quota)")

        return " ".join(explanation_parts)
