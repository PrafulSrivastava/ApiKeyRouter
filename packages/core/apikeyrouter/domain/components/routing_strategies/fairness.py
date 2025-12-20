"""Fairness-based routing strategy implementation."""

from __future__ import annotations

from apikeyrouter.domain.components.quota_awareness_engine import QuotaAwarenessEngine
from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.api_key import APIKey
from apikeyrouter.domain.models.quota_state import CapacityState, QuotaState
from apikeyrouter.domain.models.request_intent import RequestIntent


class FairnessStrategy:
    """Routing strategy that optimizes for load distribution fairness.

    Scores keys by inverse usage (less used = higher score) to balance
    load across all eligible keys and prevent key starvation.
    """

    def __init__(
        self,
        observability_manager: ObservabilityManager,
        quota_awareness_engine: QuotaAwarenessEngine | None = None,
    ) -> None:
        """Initialize FairnessStrategy.

        Args:
            observability_manager: ObservabilityManager for logging.
            quota_awareness_engine: Optional QuotaAwarenessEngine for quota state.
        """
        self._observability = observability_manager
        self._quota_engine = quota_awareness_engine

    def _calculate_relative_usage(
        self, keys: list[APIKey]
    ) -> dict[str, float]:
        """Calculate relative usage for each key.

        Args:
            keys: List of API keys to calculate usage for.

        Returns:
            Dictionary mapping key_id to relative usage (0.0 to 1.0).
        """
        if not keys:
            return {}

        # Get total usage across all keys
        total_usage = sum(key.usage_count for key in keys)

        if total_usage == 0:
            # No usage yet, all keys have equal relative usage
            return {key.id: 0.0 for key in keys}

        # Calculate relative usage for each key
        relative_usage: dict[str, float] = {}
        for key in keys:
            relative_usage[key.id] = key.usage_count / total_usage

        return relative_usage

    async def score_keys(
        self,
        eligible_keys: list[APIKey],
        request_intent: RequestIntent | None = None,
        providers: dict[str, ProviderAdapter] | None = None,
        quota_states: dict[str, QuotaState] | None = None,
    ) -> dict[str, float]:
        """Score keys by inverse usage (less used = higher score).

        Calculates inverse usage score to balance load across keys.
        Normalizes scores to 0.0-1.0 range.

        Args:
            eligible_keys: List of eligible API keys to score.
            request_intent: Optional RequestIntent (not used for fairness).
            providers: Optional dict mapping provider_id to ProviderAdapter (not used).
            quota_states: Optional dict mapping key_id to QuotaState (not used directly).

        Returns:
            Dictionary mapping key_id to score (higher is better, 0.0-1.0).
        """
        if not eligible_keys:
            return {}

        scores: dict[str, float] = {}

        # Calculate inverse usage scores
        # Formula: 1.0 / (usage_count + 1) to avoid division by zero
        # Less used keys get higher scores
        usage_counts = [key.usage_count for key in eligible_keys]
        max_usage = max(usage_counts) if usage_counts else 0
        min_usage = min(usage_counts) if usage_counts else 0

        if max_usage == min_usage:
            # All keys have equal usage, return equal scores
            # This enables round-robin behavior
            return {key.id: 1.0 for key in eligible_keys}

        # Score = 1.0 - normalized_usage (so less used = higher score)
        for key in eligible_keys:
            if max_usage > min_usage:
                normalized_usage = (key.usage_count - min_usage) / (
                    max_usage - min_usage
                )
                # Invert: less usage = higher score
                scores[key.id] = 1.0 - normalized_usage
            else:
                # All usage equal, equal scores
                scores[key.id] = 1.0

        # Ensure scores are in valid range
        for key_id in scores:
            scores[key_id] = max(0.0, min(1.0, scores[key_id]))

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

                # Keep keys with other states (including Critical/Constrained)
                # Fairness strategy should still consider them to prevent starvation
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
        self,
        scores: dict[str, float],
        eligible_keys: list[APIKey],
        last_selected_key_id: str | None = None,
    ) -> tuple[str, float]:
        """Select key with highest score (least used), with round-robin fallback.

        If multiple keys have the same highest score (equal usage), uses
        round-robin to prevent starvation and ensure fair distribution.

        Args:
            scores: Dictionary mapping key_id to score.
            eligible_keys: List of eligible API keys.
            last_selected_key_id: Optional ID of last selected key for round-robin.

        Returns:
            Tuple of (selected_key_id, score).

        Raises:
            ValueError: If no scores available or no eligible keys.
        """
        if not scores:
            raise ValueError("No scores available for key selection")

        if not eligible_keys:
            raise ValueError("No eligible keys available for selection")

        # Select key with highest score (least used)
        max_score = max(scores.values())
        keys_with_max_score = [
            key_id for key_id, score in scores.items() if score == max_score
        ]

        # Handle ties: use round-robin if multiple keys have same score
        if len(keys_with_max_score) > 1:
            # Round-robin: find next key after last_selected_key_id
            if last_selected_key_id and last_selected_key_id in keys_with_max_score:
                # Find index of last selected key
                try:
                    last_index = keys_with_max_score.index(last_selected_key_id)
                    next_index = (last_index + 1) % len(keys_with_max_score)
                    selected_key_id = keys_with_max_score[next_index]
                except ValueError:
                    # Last selected key not in tied keys, select first
                    selected_key_id = keys_with_max_score[0]
            else:
                # No last selected key or not in tied keys, select first
                selected_key_id = keys_with_max_score[0]
        else:
            # Single key with max score
            selected_key_id = keys_with_max_score[0]

        return selected_key_id, max_score

    def generate_explanation(
        self,
        selected_key_id: str,
        usage_count: int,
        relative_usage: float | None = None,
        quota_state: QuotaState | None = None,
        eligible_count: int = 0,
        filtered_count: int = 0,
        total_usage: int = 0,
    ) -> str:
        """Generate human-readable explanation for routing decision.

        Args:
            selected_key_id: The selected API key ID.
            usage_count: Usage count of the selected key.
            relative_usage: Optional relative usage (0.0 to 1.0).
            quota_state: Optional quota state for selected key.
            eligible_count: Number of eligible keys considered.
            filtered_count: Number of keys filtered out by quota.
            total_usage: Total usage across all keys.

        Returns:
            Human-readable explanation string.
        """
        explanation_parts = [f"Selected key {selected_key_id}"]

        # Include usage information
        explanation_parts.append(f"with {usage_count} total requests")

        if relative_usage is not None and total_usage > 0:
            explanation_parts.append(
                f"({relative_usage:.1%} of total usage across {eligible_count} keys)"
            )

        # Include quota state
        if quota_state:
            explanation_parts.append(f"({quota_state.capacity_state.value} quota state)")

        explanation_parts.append(
            f"(least used among {eligible_count} eligible keys for fair load distribution)"
        )

        if filtered_count > 0:
            explanation_parts.append(
                f"({filtered_count} key(s) excluded due to exhausted quota)"
            )

        return " ".join(explanation_parts)



