"""Manually runs key performance benchmarks without relying on pytest."""

import asyncio
import time
from typing import List, Coroutine

from apikeyrouter.domain.components.key_manager import KeyManager
from apikeyrouter.domain.components.quota_awareness_engine import QuotaAwarenessEngine
from apikeyrouter.domain.components.routing_engine import RoutingEngine
from apikeyrouter.domain.models.api_key import APIKey
from apikeyrouter.domain.models.routing_decision import ObjectiveType, RoutingObjective
from apikeyrouter.infrastructure.observability.logger import DefaultObservabilityManager
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore


async def setup_engine(num_keys: int, state: str = "available"):
    """Reusable setup logic to create a routing engine with keys."""
    state_store = InMemoryStateStore(max_decisions=20000, max_transitions=20000)
    observability = DefaultObservabilityManager(log_level="ERROR")
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

    keys = []
    for i in range(num_keys):
        key = await key_manager.register_key(
            key_material=f"sk-manual-bench-{i}",
            provider_id="openai",
            metadata={"index": i},
        )
        keys.append(key)

    if state == "throttled":
        # Throttle all but the last key
        for i in range(num_keys - 1):
            await key_manager.update_key_state(keys[i].id, "throttled")

    routing_engine = RoutingEngine(
        key_manager=key_manager,
        state_store=state_store,
        observability_manager=observability,
        quota_awareness_engine=quota_engine,
    )

    return routing_engine, keys


async def run_and_time_async(description: str, coro: Coroutine):
    """Helper to run and time an async function."""
    print(f"\n--- Running: {description} ---")
    start_time = time.monotonic()
    result = await coro
    end_time = time.monotonic()
    duration_ms = (end_time - start_time) * 1000
    print(f"Result: OK")
    print(f"Total Duration: {duration_ms:.2f} ms")
    return result


async def benchmark_concurrent_routing(engine: RoutingEngine, num_requests: int):
    """Benchmark many concurrent routing requests."""
    objective = RoutingObjective(primary=ObjectiveType.Fairness.value)
    tasks = [
        engine.route_request(
            {"provider_id": "openai", "request_id": f"req-{i}"}, objective
        )
        for i in range(num_requests)
    ]
    results = await asyncio.gather(*tasks)
    assert len(results) == num_requests
    assert all(r.selected_key_id for r in results)


async def benchmark_large_scale_routing(engine: RoutingEngine):
    """Benchmark routing with many keys."""
    objective = RoutingObjective(primary=ObjectiveType.Fairness.value)
    result = await engine.route_request(
        {"provider_id": "openai", "request_id": "large-scale-test"}, objective
    )
    assert result.selected_key_id is not None


async def benchmark_failover_routing(engine: RoutingEngine, good_key: APIKey):
    """Benchmark routing to find one good key among many bad ones."""
    objective = RoutingObjective(primary=ObjectiveType.Reliability.value)
    result = await engine.route_request(
        {"provider_id": "openai", "request_id": "failover-test"}, objective
    )
    assert result.selected_key_id == good_key.id


async def benchmark_aged_history_routing(engine: RoutingEngine, keys: List[APIKey]):
    """Benchmark fairness with a large history."""
    state_store = engine._state_store
    objective = RoutingObjective(primary=ObjectiveType.Fairness.value)

    # Pre-populate with history
    print("Pre-populating with 10,000 decisions...")
    for i in range(10000):
        key_id_for_log = keys[i % len(keys)].id
        await state_store.log_decision(
            f"req-hist-{i}", key_id_for_log, "routed", ObjectiveType.Fairness.value
        )
    
    await run_and_time_async(
        "Single route with 10k history",
        engine.route_request(
            {"provider_id": "openai", "request_id": "aged-test"}, objective
        ),
    )


async def main():
    """Main function to orchestrate the benchmarks."""
    print("====== Starting Manual Performance Benchmarks ======")

    # --- Concurrency Test ---
    concurrency_engine, _ = await setup_engine(num_keys=20)
    await run_and_time_async(
        "100 concurrent routing requests",
        benchmark_concurrent_routing(concurrency_engine, num_requests=100),
    )

    # --- Scale Test ---
    scale_engine, _ = await setup_engine(num_keys=1000)
    await run_and_time_async(
        "Single route with 1,000 keys",
        benchmark_large_scale_routing(scale_engine),
    )

    # --- Failover Test ---
    failover_engine, failover_keys = await setup_engine(num_keys=1000, state="throttled")
    the_one_good_key = failover_keys[-1]
    await run_and_time_async(
        "Failover routing (1 good key in 1000)",
        benchmark_failover_routing(failover_engine, the_one_good_key),
    )
    
    # --- Aged History Test ---
    aged_engine, aged_keys = await setup_engine(num_keys=1000)
    await benchmark_aged_history_routing(aged_engine, aged_keys)

    print("\n====== Benchmarks Complete ======")


if __name__ == "__main__":
    asyncio.run(main())
