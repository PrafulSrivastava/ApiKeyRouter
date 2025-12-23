"""Domain models for API Key Router."""

from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.domain.models.budget import Budget, BudgetScope, EnforcementMode
from apikeyrouter.domain.models.budget_check_result import BudgetCheckResult
from apikeyrouter.domain.models.cost_estimate import CostEstimate
from apikeyrouter.domain.models.cost_reconciliation import CostReconciliation
from apikeyrouter.domain.models.health_state import HealthState, HealthStatus
from apikeyrouter.domain.models.quota_state import (
    CapacityEstimate,
    CapacityState,
    CapacityUnit,
    ExhaustionPrediction,
    QuotaState,
    TimeWindow,
    UncertaintyLevel,
    UsageRate,
)
from apikeyrouter.domain.models.request_intent import Message, RequestIntent
from apikeyrouter.domain.models.routing_decision import (
    AlternativeRoute,
    ObjectiveType,
    RoutingDecision,
    RoutingObjective,
)
from apikeyrouter.domain.models.state_transition import StateTransition
from apikeyrouter.domain.models.system_error import ErrorCategory, SystemError
from apikeyrouter.domain.models.system_response import (
    ResponseMetadata,
    SystemResponse,
    TokenUsage,
)

__all__ = [
    "APIKey",
    "KeyState",
    "StateTransition",
    "CapacityState",
    "CapacityUnit",
    "TimeWindow",
    "UncertaintyLevel",
    "CapacityEstimate",
    "QuotaState",
    "UsageRate",
    "ExhaustionPrediction",
    "ObjectiveType",
    "RoutingObjective",
    "RoutingDecision",
    "AlternativeRoute",
    "Message",
    "RequestIntent",
    "TokenUsage",
    "ResponseMetadata",
    "SystemResponse",
    "SystemError",
    "ErrorCategory",
    "CostEstimate",
    "CostReconciliation",
    "HealthState",
    "HealthStatus",
    "Budget",
    "BudgetScope",
    "EnforcementMode",
    "BudgetCheckResult",
]
