"""Performance benchmarks for quota calculation time."""

import pytest

from apikeyrouter.domain.components.key_manager import KeyManager
from apikeyrouter.domain.components.quota_awareness_engine import QuotaAwarenessEngine
from apikeyrouter.infrastructure.observability.logger import DefaultObservabilityManager
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore


@pytest.fixture
async def quota_engine_with_key():
    """Set up QuotaAwarenessEngine with a key for benchmarking."""
    state_store = InMemoryStateStore(max_decisions=1000, max_transitions=1000)
    observability = DefaultObservabilityManager(log_level="WARNING")
    key_manager = KeyManager(
        state_store=state_store,
        observability_manager=observability,
        default_cooldown_seconds=60,
    )

    # Register a key
    key = await key_manager.register_key(
        key_material="sk-test-key-1",
        provider_id="openai",
    )

    quota_engine = QuotaAwarenessEngine(
        state_store=state_store,
        observability_manager=observability,
        key_manager=key_manager,
        default_cooldown_seconds=60,
    )

    return quota_engine, key


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_benchmark_update_capacity_time(
    benchmark, quota_engine_with_key
):
    """Benchmark QuotaAwarenessEngine.update_capacity() time.

    Target: p95 < 5ms
    """
    quota_engine, key = quota_engine_with_key

    # Benchmark update_capacity
    async def run_update():
        return await quota_engine.update_capacity(key.id, 15)  # Consume 15 tokens

    result = await benchmark(run_update)

    # Verify result is valid
    assert result is not None
    assert result.key_id == key.id


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_benchmark_get_quota_state_time(
    benchmark, quota_engine_with_key
):
    """Benchmark QuotaAwarenessEngine.get_quota_state() time.

    Target: p95 < 5ms
    """
    quota_engine, key = quota_engine_with_key

    # Benchmark get_quota_state
    async def run_get_quota():
        return await quota_engine.get_quota_state(key.id)

    result = await benchmark(run_get_quota)

    # Verify result is valid
    assert result is not None
    assert result.key_id == key.id


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_benchmark_quota_calculation_with_multiple_updates(
    benchmark, quota_engine_with_key
):
    """Benchmark quota calculation with multiple sequential updates."""
    quota_engine, key = quota_engine_with_key

    async def update_multiple_times():
        """Update capacity multiple times."""
        for _ in range(10):
            await quota_engine.update_capacity(key.id, 10)

    _result = await benchmark(update_multiple_times)

    # Verify quota state is updated
    quota_state = await quota_engine.get_quota_state(key.id)
    assert quota_state.used_capacity > 0

