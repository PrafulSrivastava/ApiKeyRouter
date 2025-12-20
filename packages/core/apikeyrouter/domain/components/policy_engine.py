"""PolicyEngine component for evaluating declarative policies."""

from __future__ import annotations

from typing import Any

from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.interfaces.state_store import StateStore
from apikeyrouter.domain.models.policy import Policy, PolicyResult, PolicyScope, PolicyType


class PolicyEngine:
    """Evaluates declarative policies that drive routing decisions.

    Policies express intent, not procedure. They are evaluated against
    routing context to filter keys and apply constraints.
    """

    def __init__(
        self,
        state_store: StateStore,
        observability_manager: ObservabilityManager,
    ) -> None:
        """Initialize PolicyEngine.

        Args:
            state_store: StateStore for policy storage and retrieval.
            observability_manager: ObservabilityManager for logging.
        """
        self._state_store = state_store
        self._observability = observability_manager

    async def get_applicable_policies(
        self,
        scope: PolicyScope,
        policy_type: PolicyType,
        scope_id: str | None = None,
    ) -> list[Policy]:
        """Get policies that apply to a scope.

        Args:
            scope: PolicyScope to query (global, per_provider, etc.).
            policy_type: PolicyType to filter by.
            scope_id: Optional specific entity ID for scoped policies.

        Returns:
            List of applicable policies, ordered by priority (highest first).
        """
        # For now, return empty list (policies not yet stored in StateStore)
        # In future, this would query StateStore for policies matching scope/type
        # For integration purposes, we'll support policies passed directly
        return []

    async def evaluate_policy(
        self, policy: Policy, context: dict[str, Any]
    ) -> PolicyResult:
        """Evaluate policy against routing context.

        Args:
            policy: Policy to evaluate.
            context: Routing context containing keys, request_intent, etc.

        Returns:
            PolicyResult with filtered keys, constraints, and reason.
        """
        if not policy.enabled:
            return PolicyResult(
                allowed=True,
                reason=f"Policy {policy.id} is disabled",
            )

        # Evaluate routing policy rules
        if policy.type == PolicyType.Routing:
            result = self._evaluate_routing_policy(policy, context)
            return result

        # Evaluate cost control policy rules
        elif policy.type == PolicyType.CostControl:
            result = self._evaluate_cost_control_policy(policy, context)
            return result

        # Evaluate key selection policy rules
        elif policy.type == PolicyType.KeySelection:
            result = self._evaluate_key_selection_policy(policy, context)
            return result

        # Default: allow all
        return PolicyResult(
            allowed=True,
            reason=f"Policy {policy.id} type {policy.type.value} not yet fully implemented",
        )

    def _evaluate_routing_policy(
        self, policy: Policy, context: dict[str, Any]
    ) -> PolicyResult:
        """Evaluate routing policy rules.

        Args:
            policy: Routing policy to evaluate.
            context: Routing context.

        Returns:
            PolicyResult with filtered keys and constraints.
        """
        filtered_keys: list[str] = []
        constraints: dict[str, Any] = {}
        reasons: list[str] = []

        rules = policy.rules
        eligible_keys = context.get("eligible_keys", [])

        # Check max_cost constraint
        if "max_cost" in rules:
            max_cost = rules["max_cost"]
            constraints["max_cost"] = max_cost
            # Filter keys that would exceed max_cost (requires cost estimation)
            # For now, just add constraint
            reasons.append(f"max_cost constraint: ${max_cost}")

        # Check min_reliability constraint
        if "min_reliability" in rules:
            min_reliability = rules["min_reliability"]
            constraints["min_reliability"] = min_reliability
            # Filter keys below min_reliability
            for key in eligible_keys:
                # Calculate success rate
                total = key.usage_count + key.failure_count
                if total > 0:
                    success_rate = key.usage_count / total
                    if success_rate < min_reliability:
                        filtered_keys.append(key.id)
                        reasons.append(
                            f"Key {key.id} below min_reliability {min_reliability:.2%}"
                        )

        # Check allowed_providers constraint
        if "allowed_providers" in rules:
            allowed_providers = rules["allowed_providers"]
            if isinstance(allowed_providers, list):
                for key in eligible_keys:
                    if key.provider_id not in allowed_providers:
                        filtered_keys.append(key.id)
                        reasons.append(
                            f"Key {key.id} provider {key.provider_id} not in allowed list"
                        )

        # Check blocked_providers constraint
        if "blocked_providers" in rules:
            blocked_providers = rules["blocked_providers"]
            if isinstance(blocked_providers, list):
                for key in eligible_keys:
                    if key.provider_id in blocked_providers:
                        filtered_keys.append(key.id)
                        reasons.append(
                            f"Key {key.id} provider {key.provider_id} is blocked"
                        )

        reason = "; ".join(reasons) if reasons else f"Policy {policy.id} applied"
        return PolicyResult(
            allowed=True,
            filtered_keys=list(set(filtered_keys)),  # Remove duplicates
            constraints=constraints,
            reason=reason,
            applied_policies=[policy.id],
        )

    def _evaluate_cost_control_policy(
        self, policy: Policy, context: dict[str, Any]
    ) -> PolicyResult:
        """Evaluate cost control policy rules.

        Args:
            policy: Cost control policy to evaluate.
            context: Routing context.

        Returns:
            PolicyResult with constraints.
        """
        constraints: dict[str, Any] = {}
        reasons: list[str] = []

        rules = policy.rules

        # Check budget_limits
        if "budget_limit" in rules:
            budget_limit = rules["budget_limit"]
            constraints["budget_limit"] = budget_limit
            reasons.append(f"Budget limit: ${budget_limit}")

        # Check cost_thresholds
        if "max_cost_per_request" in rules:
            max_cost = rules["max_cost_per_request"]
            constraints["max_cost"] = max_cost
            reasons.append(f"Max cost per request: ${max_cost}")

        reason = "; ".join(reasons) if reasons else f"Policy {policy.id} applied"
        return PolicyResult(
            allowed=True,
            constraints=constraints,
            reason=reason,
            applied_policies=[policy.id],
        )

    def _evaluate_key_selection_policy(
        self, policy: Policy, context: dict[str, Any]
    ) -> PolicyResult:
        """Evaluate key selection policy rules.

        Args:
            policy: Key selection policy to evaluate.
            context: Routing context.

        Returns:
            PolicyResult with filtered keys.
        """
        filtered_keys: list[str] = []
        reasons: list[str] = []

        rules = policy.rules
        eligible_keys = context.get("eligible_keys", [])

        # Check key_filters
        if "key_filters" in rules:
            key_filters = rules["key_filters"]
            if isinstance(key_filters, dict):
                # Filter by key state
                if "allowed_states" in key_filters:
                    allowed_states = key_filters["allowed_states"]
                    for key in eligible_keys:
                        if key.state.value not in allowed_states:
                            filtered_keys.append(key.id)
                            reasons.append(
                                f"Key {key.id} state {key.state.value} not allowed"
                            )

                # Filter by key IDs
                if "blocked_keys" in key_filters:
                    blocked_keys = key_filters["blocked_keys"]
                    for key in eligible_keys:
                        if key.id in blocked_keys:
                            filtered_keys.append(key.id)
                            reasons.append(f"Key {key.id} is blocked")

        reason = "; ".join(reasons) if reasons else f"Policy {policy.id} applied"
        return PolicyResult(
            allowed=True,
            filtered_keys=list(set(filtered_keys)),  # Remove duplicates
            reason=reason,
            applied_policies=[policy.id],
        )

    async def resolve_policy_conflicts(
        self, policies: list[Policy]
    ) -> list[Policy]:
        """Resolve policy conflicts using precedence rules.

        Args:
            policies: List of policies that may conflict.

        Returns:
            List of policies ordered by precedence (highest first).
        """
        # Sort by priority (higher priority first)
        sorted_policies = sorted(policies, key=lambda p: p.priority, reverse=True)
        return sorted_policies



