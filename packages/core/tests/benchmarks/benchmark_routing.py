"""Performance benchmarks for routing decision time."""

import pytest

from apikeyrouter.domain.components.key_manager import KeyManager
from apikeyrouter.domain.components.quota_awareness_engine import QuotaAwarenessEngine
from apikeyrouter.domain.components.routing_engine import RoutingEngine
from apikeyrouter.domain.models.routing_decision import ObjectiveType, RoutingObjective
from apikeyrouter.infrastructure.observability.logger import DefaultObservabilityManager
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore


@pytest.fixture
async def routing_engine_with_keys():
    """Set up RoutingEngine with 10 keys for benchmarking."""
    state_store = InMemoryStateStore(max_decisions=1000, max_transitions=1000)
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

    # Register 10 keys
    keys = []
    for i in range(10):
        key = await key_manager.register_key(
            key_material=f"sk-test-key-{i}",
            provider_id="openai",
            metadata={"index": i},
        )
        keys.append(key)

    routing_engine = RoutingEngine(
        key_manager=key_manager,
        state_store=state_store,
        observability_manager=observability,
        quota_awareness_engine=quota_engine,
    )

    return routing_engine, keys


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_benchmark_routing_decision_time(
    benchmark, routing_engine_with_keys
):
    """Benchmark routing decision time with 10 keys.

    Target: p95 < 10ms
    """
    routing_engine, keys = routing_engine_with_keys

    request_intent = {
        "provider_id": "openai",
        "request_id": "test-request",
    }
    objective = RoutingObjective(primary=ObjectiveType.Fairness.value)

    # Benchmark the routing decision
    async def run_routing():
        return await routing_engine.route_request(request_intent, objective)

    result = await benchmark(run_routing)

    # Verify result is valid
    assert result is not None
    assert result.selected_key_id in [key.id for key in keys]


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_benchmark_routing_decision_cost_objective(
    benchmark, routing_engine_with_keys
):
    """Benchmark routing decision with cost objective."""
    routing_engine, keys = routing_engine_with_keys

    request_intent = {
        "provider_id": "openai",
        "request_id": "test-request",
    }
    objective = RoutingObjective(primary=ObjectiveType.Cost.value)

    async def run_routing():
        return await routing_engine.route_request(request_intent, objective)

    result = await benchmark(run_routing)

    assert result is not None
    assert result.selected_key_id in [key.id for key in keys]


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_benchmark_routing_decision_reliability_objective(
    benchmark, routing_engine_with_keys
):
    """Benchmark routing decision with reliability objective."""
    routing_engine, keys = routing_engine_with_keys

    request_intent = {
        "provider_id": "openai",
        "request_id": "test-request",
    }
    objective = RoutingObjective(primary=ObjectiveType.Reliability.value)

    async def run_routing():
        return await routing_engine.route_request(request_intent, objective)

    result = await benchmark(run_routing)

    assert result is not None
    assert result.selected_key_id in [key.id for key in keys]

