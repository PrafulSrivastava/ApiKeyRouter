"""Performance benchmarks for key lookup time."""

import pytest

from apikeyrouter.domain.components.key_manager import KeyManager
from apikeyrouter.infrastructure.observability.logger import DefaultObservabilityManager
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore


@pytest.fixture
async def state_store_with_keys():
    """Set up StateStore with 100 keys for benchmarking."""
    state_store = InMemoryStateStore(max_decisions=1000, max_transitions=1000)
    observability = DefaultObservabilityManager(log_level="WARNING")
    key_manager = KeyManager(
        state_store=state_store,
        observability_manager=observability,
        default_cooldown_seconds=60,
    )

    # Register 100 keys
    keys = []
    for i in range(100):
        key = await key_manager.register_key(
            key_material=f"sk-test-key-{i}",
            provider_id="openai",
            metadata={"index": i},
        )
        keys.append(key)

    return state_store, key_manager, keys


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_benchmark_key_lookup_time(benchmark, state_store_with_keys):
    """Benchmark StateStore.get_key() time with 100 keys.

    Target: p95 < 1ms
    """
    state_store, key_manager, keys = state_store_with_keys

    # Pick a random key to look up
    test_key = keys[50]  # Middle key

    # Benchmark get_key
    async def run_get_key():
        return await state_store.get_key(test_key.id)

    result = await benchmark(run_get_key)

    # Verify result is valid
    assert result is not None
    assert result.id == test_key.id


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_benchmark_key_manager_get_key_time(benchmark, state_store_with_keys):
    """Benchmark KeyManager.get_key() time with 100 keys."""
    state_store, key_manager, keys = state_store_with_keys

    # Pick a random key to look up
    test_key = keys[75]

    # Benchmark get_key through KeyManager
    async def run_get_key():
        return await key_manager.get_key(test_key.id)

    result = await benchmark(run_get_key)

    # Verify result is valid
    assert result is not None
    assert result.id == test_key.id


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_benchmark_get_eligible_keys_time(benchmark, state_store_with_keys):
    """Benchmark KeyManager.get_eligible_keys() time with 100 keys."""
    state_store, key_manager, keys = state_store_with_keys

    # Benchmark get_eligible_keys
    async def run_get_eligible():
        return await key_manager.get_eligible_keys("openai")

    result = await benchmark(run_get_eligible)

    # Verify result is valid
    assert result is not None
    assert len(result) == 100  # All keys should be eligible


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_benchmark_key_lookup_random_keys(benchmark, state_store_with_keys):
    """Benchmark key lookup with random key selection."""
    import random

    state_store, key_manager, keys = state_store_with_keys

    async def lookup_random_key():
        """Look up a random key."""
        random_key = random.choice(keys)
        return await state_store.get_key(random_key.id)

    result = await benchmark(lookup_random_key)

    # Verify result is valid
    assert result is not None
    assert result.id in [key.id for key in keys]
