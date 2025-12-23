"""Routing strategies for different optimization objectives."""

from apikeyrouter.domain.components.routing_strategies.cost_optimized import (
    CostOptimizedStrategy,
)
from apikeyrouter.domain.components.routing_strategies.fairness import (
    FairnessStrategy,
)
from apikeyrouter.domain.components.routing_strategies.reliability_optimized import (
    ReliabilityOptimizedStrategy,
)

__all__ = [
    "CostOptimizedStrategy",
    "ReliabilityOptimizedStrategy",
    "FairnessStrategy",
]
