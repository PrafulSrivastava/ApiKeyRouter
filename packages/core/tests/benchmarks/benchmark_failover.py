"""Performance benchmarks for failover and resilience scenarios."""

import pytest

from apikeyrouter.domain.components.key_manager import KeyManager
from apikeyrouter.domain.components.quota_awareness_engine import QuotaAwarenessEngine
from apikeyrouter.domain.components.routing_engine import RoutingEngine
from apikeyrouter.domain.models.api_key import KeyState
from apikeyrouter.domain.models.routing_decision import (
    ObjectiveType,
    RoutingObjective,
)
from apikeyrouter.infrastructure.observability.logger import (
    DefaultObservabilityManager,
)
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore


@pytest.fixture
async def routing_engine_for_failover():
    """Set up RoutingEngine with 1000 keys for failover benchmarking."""
    state_store = InMemoryStateStore(max_decisions=10000, max_transitions=10000)
    observability = DefaultObservabilityManager(log_level="WARNING")
    key_manager = KeyManager(
        state_store=state_store,
        observability_manager=observability,
        default_cooldown_seconds=60,
    )
    quota_engine = QuotaAwarenessEngine(
        state_store=state_store,
        observability_manager=observability,
        key_manager=key_manager,
        default_cooldown_seconds=60,
    )

    # Register 1000 keys
    keys = []
    for i in range(1000):
        key = await key_manager.register_key(
            key_material=f"sk-failover-key-{i}",
            provider_id="openai",
            metadata={"index": i},
        )
        keys.append(key)

    # Set 999 of 1000 keys to Throttled
    for i in range(999):
        await key_manager.update_key_state(
            keys[i].id, KeyState.Throttled, reason="benchmark_setup"
        )

    # The last key remains Available
    the_one_good_key = keys[999]

    routing_engine = RoutingEngine(
        key_manager=key_manager,
        state_store=state_store,
        observability_manager=observability,
        quota_awareness_engine=quota_engine,
    )

    return routing_engine, the_one_good_key


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_benchmark_needle_in_haystack_routing(
    benchmark, routing_engine_for_failover
):
    """Benchmark routing to find 1 available key among 999 throttled keys.

    Target: p95 < 20ms
    """
    routing_engine, the_one_good_key = routing_engine_for_failover
    objective = RoutingObjective(primary=ObjectiveType.Reliability.value)

    async def run_routing():
        return await routing_engine.route_request(
            {"provider_id": "openai", "request_id": "failover-test"}, objective
        )

    result = await benchmark(run_routing)

    # Verify the one good key was selected
    assert result.selected_key_id == the_one_good_key.id
