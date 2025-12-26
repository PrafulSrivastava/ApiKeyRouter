"""Performance benchmarks for concurrent routing scenarios."""

import asyncio

import pytest

from apikeyrouter.domain.components.key_manager import KeyManager
from apikeyrouter.domain.components.quota_awareness_engine import QuotaAwarenessEngine
from apikeyrouter.domain.components.routing_engine import RoutingEngine
from apikeyrouter.domain.models.routing_decision import ObjectiveType, RoutingObjective
from apikeyrouter.infrastructure.observability.logger import DefaultObservabilityManager
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore


@pytest.fixture
async def routing_engine_for_concurrency():
    """Set up RoutingEngine with 20 keys for concurrency benchmarking."""
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

    # Register 20 keys
    keys = []
    for i in range(20):
        key = await key_manager.register_key(
            key_material=f"sk-concurrency-key-{i}",
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

    return routing_engine, keys, quota_engine


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_benchmark_concurrent_routing(benchmark, routing_engine_for_concurrency):
    """Benchmark concurrent routing decision time for 100 simultaneous requests.

    Target: p95 < 50ms
    """
    routing_engine, _, _ = routing_engine_for_concurrency
    num_requests = 100

    async def run_concurrent_routing():
        objective = RoutingObjective(primary=ObjectiveType.Fairness.value)
        tasks = [
            routing_engine.route_request(
                {"provider_id": "openai", "request_id": f"req-{i}"}, objective
            )
            for i in range(num_requests)
        ]
        results = await asyncio.gather(*tasks)
        return results

    results = await benchmark(run_concurrent_routing)

    assert len(results) == num_requests
    for result in results:
        assert result.selected_key_id is not None


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_benchmark_concurrent_quota_updates(
    benchmark, routing_engine_for_concurrency
):
    """Benchmark 100 concurrent quota updates on the same key.

    Target: p95 < 30ms
    """
    _, keys, quota_engine = routing_engine_for_concurrency
    target_key = keys[0]
    num_updates = 100

    async def run_concurrent_updates():
        tasks = [
            quota_engine.update_capacity(target_key.id, 10) for _ in range(num_updates)
        ]
        await asyncio.gather(*tasks)

    await benchmark(run_concurrent_updates)

    # Verify state
    quota_state = await quota_engine.get_quota_state(target_key.id)
    assert quota_state.used_capacity >= num_updates * 10
