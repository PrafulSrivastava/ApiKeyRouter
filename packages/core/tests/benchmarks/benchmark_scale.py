"""Performance benchmarks for large-scale routing scenarios."""

import pytest
from datetime import datetime

from apikeyrouter.domain.components.key_manager import KeyManager
from apikeyrouter.domain.components.quota_awareness_engine import QuotaAwarenessEngine
from apikeyrouter.domain.components.routing_engine import RoutingEngine
from apikeyrouter.domain.models.routing_decision import ObjectiveType, RoutingObjective, RoutingDecision
from apikeyrouter.infrastructure.observability.logger import DefaultObservabilityManager
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore


@pytest.fixture
async def routing_engine_with_1000_keys():
    """Set up RoutingEngine with 1,000 keys for scale benchmarking."""
    state_store = InMemoryStateStore(max_decisions=20000, max_transitions=20000)
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

    # Register 1,000 keys
    keys = []
    for i in range(1000):
        key = await key_manager.register_key(
            key_material=f"sk-scale-key-{i}",
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
async def test_benchmark_routing_with_1000_keys(
    benchmark, routing_engine_with_1000_keys
):
    """Benchmark routing decision time with 1,000 available keys.

    Target: p95 < 25ms
    """
    routing_engine, _ = routing_engine_with_1000_keys
    objective = RoutingObjective(primary=ObjectiveType.Fairness.value)

    async def run_routing():
        return await routing_engine.route_request(
            {"provider_id": "openai", "request_id": "scale-test"}, objective
        )

    result = await benchmark(run_routing)

    assert result.selected_key_id is not None


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_benchmark_aged_fairness_routing(
    benchmark, routing_engine_with_1000_keys
):
    """Benchmark fairness routing with a large decision history.

    Target: p95 < 30ms
    """
    routing_engine, keys = routing_engine_with_1000_keys
    state_store = routing_engine._state_store
    objective = RoutingObjective(primary=ObjectiveType.Fairness.value)

    # Pre-populate history with 10,000 decisions
    for i in range(10000):
        # Simulate decisions across different keys
        key_for_log = keys[i % len(keys)]
        decision = RoutingDecision(
            id=f"dec-{i}",
            request_id=f"req-hist-{i}",
            selected_key_id=key_for_log.id,
            selected_provider_id=key_for_log.provider_id,
            objective=objective,
            explanation="benchmark setup",
            confidence=1.0,
            decision_timestamp=datetime.utcnow(),
			status="routed"
        )
        await state_store.save_routing_decision(decision)

    async def run_routing():
        return await routing_engine.route_request(
            {"provider_id": "openai", "request_id": "aged-test"}, objective
        )

    result = await benchmark(run_routing)

    assert result.selected_key_id is not None
