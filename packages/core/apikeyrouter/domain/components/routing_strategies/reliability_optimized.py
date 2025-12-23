"""Reliability-optimized routing strategy implementation."""

from __future__ import annotations

from apikeyrouter.domain.components.quota_awareness_engine import QuotaAwarenessEngine
from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.domain.models.quota_state import CapacityState, QuotaState
from apikeyrouter.domain.models.request_intent import RequestIntent


class ReliabilityOptimizedStrategy:
    """Routing strategy that optimizes for highest reliability.

    Scores keys by success rate, health state, and quota state. Prefers keys
    with high success rates and avoids keys with recent failures.
    """

    def __init__(
        self,
        observability_manager: ObservabilityManager,
        quota_awareness_engine: QuotaAwarenessEngine | None = None,
    ) -> None:
        """Initialize ReliabilityOptimizedStrategy.

        Args:
            observability_manager: ObservabilityManager for logging.
            quota_awareness_engine: Optional QuotaAwarenessEngine for quota state.
        """
        self._observability = observability_manager
        self._quota_engine = quota_awareness_engine

    def _calculate_success_rate(self, key: APIKey) -> float:
        """Calculate success rate for a key.

        Args:
            key: APIKey to calculate success rate for.

        Returns:
            Success rate as float between 0.0 and 1.0.
        """
        total_requests = key.usage_count + key.failure_count
        if total_requests > 0:
            # Success rate = successful requests / total requests
            success_rate = float(key.usage_count) / float(total_requests)
            return max(0.0, min(1.0, success_rate))
        else:
            # No usage history - default to high reliability (neutral)
            return 0.95

    def _get_key_state_score(self, key: APIKey) -> float:
        """Get score based on key state.

        Args:
            key: APIKey to score.

        Returns:
            Score between 0.0 and 1.0 based on key state.
        """
        state_scores = {
            KeyState.Available: 1.0,
            KeyState.Throttled: 0.7,
            KeyState.Recovering: 0.5,
            KeyState.Exhausted: 0.0,
            KeyState.Disabled: 0.0,
            KeyState.Invalid: 0.0,
        }
        return state_scores.get(key.state, 0.5)

    def _get_quota_state_score(self, quota_state: QuotaState | None) -> float:
        """Get score based on quota state.

        Args:
            quota_state: Optional QuotaState to score.

        Returns:
            Score between 0.0 and 1.0 based on quota state.
        """
        if quota_state is None:
            return 0.8  # Neutral score if quota state unknown

        state_scores = {
            CapacityState.Abundant: 1.0,
            CapacityState.Constrained: 0.7,
            CapacityState.Critical: 0.4,
            CapacityState.Exhausted: 0.0,
            CapacityState.Recovering: 0.6,
        }
        return state_scores.get(quota_state.capacity_state, 0.5)

    def _get_health_score(
        self, key: APIKey, providers: dict[str, ProviderAdapter] | None = None
    ) -> float:
        """Get score based on provider health.

        Args:
            key: APIKey to get health for.
            providers: Optional dict mapping provider_id to ProviderAdapter.

        Returns:
            Score between 0.0 and 1.0 based on provider health.
        """
        # For now, use key state as proxy for health
        # In future, could query provider health via adapter
        if providers and key.provider_id in providers:
            # Could call adapter.get_health() here if needed
            # For now, use key state
            return self._get_key_state_score(key)
        else:
            # No provider adapter, use key state
            return self._get_key_state_score(key)

    async def score_keys(
        self,
        eligible_keys: list[APIKey],
        request_intent: RequestIntent | None = None,
        providers: dict[str, ProviderAdapter] | None = None,
        quota_states: dict[str, QuotaState] | None = None,
    ) -> dict[str, float]:
        """Score keys by reliability (higher reliability = higher score).

        Combines success rate (70%), health (20%), and quota state (10%)
        into a composite reliability score. Normalizes scores to 0.0-1.0 range.

        Args:
            eligible_keys: List of eligible API keys to score.
            request_intent: Optional RequestIntent (not used for reliability).
            providers: Optional dict mapping provider_id to ProviderAdapter.
            quota_states: Optional dict mapping key_id to QuotaState.

        Returns:
            Dictionary mapping key_id to score (higher is better, 0.0-1.0).
        """
        if not eligible_keys:
            return {}

        scores: dict[str, float] = {}

        # Get quota states if not provided
        if quota_states is None and self._quota_engine:
            quota_states = {}
            for key in eligible_keys:
                try:
                    key_quota_state = await self._quota_engine.get_quota_state(key.id)
                    quota_states[key.id] = key_quota_state
                except Exception as e:
                    # Log but continue without quota state for this key
                    await self._observability.log(
                        level="WARNING",
                        message=f"Failed to get quota state for key {key.id}: {e}",
                        context={"key_id": key.id},
                    )

        # Score each key
        for key in eligible_keys:
            # Calculate success rate (70% weight)
            success_rate = self._calculate_success_rate(key)
            success_score = success_rate * 0.70

            # Get health score (20% weight)
            health_score = self._get_health_score(key, providers) * 0.20

            # Get quota state score (10% weight)
            quota_state: QuotaState | None = quota_states.get(key.id) if quota_states else None
            quota_score = self._get_quota_state_score(quota_state) * 0.10

            # Combine scores
            composite_score = success_score + health_score + quota_score

            # Penalize keys with recent failures (high failure_count relative to usage)
            if key.usage_count > 0:
                failure_ratio = key.failure_count / (key.usage_count + key.failure_count)
                if failure_ratio > 0.1:  # More than 10% failure rate
                    # Apply penalty: reduce score by failure_ratio
                    composite_score *= 1.0 - failure_ratio * 0.5  # Max 50% penalty

            scores[key.id] = max(0.0, min(1.0, composite_score))

        # Normalize scores to ensure they're in 0.0-1.0 range
        if scores:
            max_score = max(scores.values())
            min_score = min(scores.values())
            if max_score > min_score:
                # Normalize to 0.0-1.0 range
                for key_id in scores:
                    scores[key_id] = (scores[key_id] - min_score) / (max_score - min_score)
            elif max_score == min_score and max_score > 0:
                # All scores equal, keep as is
                pass
            else:
                # All scores are 0, set to equal low scores
                for key_id in scores:
                    scores[key_id] = 0.1

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

                # Keep keys with other states
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

    def select_key(
        self, scores: dict[str, float], eligible_keys: list[APIKey]
    ) -> tuple[str, float]:
        """Select key with highest reliability score.

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

        # Select key with highest score (most reliable)
        max_score = max(scores.values())
        keys_with_max_score = [key_id for key_id, score in scores.items() if score == max_score]

        # Handle ties: select first key (deterministic)
        selected_key_id = keys_with_max_score[0]

        return selected_key_id, max_score

    def generate_explanation(
        self,
        selected_key_id: str,
        success_rate: float,
        quota_state: QuotaState | None,
        eligible_count: int,
        filtered_count: int,
        failure_count: int = 0,
        usage_count: int = 0,
    ) -> str:
        """Generate human-readable explanation for routing decision.

        Args:
            selected_key_id: The selected API key ID.
            success_rate: Success rate of the selected key.
            quota_state: Optional quota state for selected key.
            eligible_count: Number of eligible keys considered.
            filtered_count: Number of keys filtered out by quota.
            failure_count: Number of failures for selected key.
            usage_count: Number of successful uses for selected key.

        Returns:
            Human-readable explanation string.
        """
        explanation_parts = [f"Selected key {selected_key_id}"]

        # Include success rate
        explanation_parts.append(f"with reliability score based on {success_rate:.1%} success rate")

        # Include usage statistics
        if usage_count > 0 or failure_count > 0:
            total = usage_count + failure_count
            explanation_parts.append(
                f"({usage_count} successes, {failure_count} failures out of {total} requests)"
            )

        # Include quota state
        if quota_state:
            explanation_parts.append(f"({quota_state.capacity_state.value} quota state)")

        explanation_parts.append(f"(highest reliability among {eligible_count} eligible keys)")

        if filtered_count > 0:
            explanation_parts.append(f"({filtered_count} key(s) excluded due to exhausted quota)")

        return " ".join(explanation_parts)
