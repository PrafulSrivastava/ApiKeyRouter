# Testing Guide for InMemoryStateStore

This guide explains how to test the InMemoryStateStore implementation that has been developed.

## Quick Start

### 1. Run All Automated Tests

```bash
# From packages/core directory
python -m pytest tests/unit/test_state_store.py tests/unit/test_memory_store.py -v
```

This runs **63 tests** covering:
- StateStore abstract interface (15 tests)
- InMemoryStateStore implementation (48 tests)

### 2. Run Manual Test Script

```bash
# From packages/core directory
python test_manual_example.py
```

This demonstrates all features with interactive output.

## Test Coverage

### What's Tested

#### StateStore Interface (15 tests)
- ✅ Abstract class cannot be instantiated
- ✅ Incomplete implementations cannot be instantiated
- ✅ Complete implementations can be instantiated
- ✅ All methods are abstract
- ✅ Interface documentation exists
- ✅ Type hints are correct
- ✅ StateQuery model validation
- ✅ StateStoreError exception behavior

#### InMemoryStateStore Implementation (48 tests)

**Key Storage (11 tests)**
- ✅ Save and retrieve API keys
- ✅ Overwrite existing keys
- ✅ Thread-safety (concurrent saves)
- ✅ Concurrent reads (no locks needed)
- ✅ Performance <1ms per operation
- ✅ Error handling

**Quota State Storage (7 tests)**
- ✅ Save and retrieve quota states
- ✅ Overwrite existing quota states
- ✅ Thread-safety with concurrent operations
- ✅ Concurrent reads

**Routing Decision Storage (9 tests)**
- ✅ Save routing decisions
- ✅ max_decisions limit enforcement (FIFO)
- ✅ Unlimited mode (max_decisions=0)
- ✅ Query by key_id, provider_id, timestamp
- ✅ Thread-safety

**State Transition Storage (10 tests)**
- ✅ Save state transitions
- ✅ max_transitions limit enforcement (FIFO)
- ✅ Unlimited mode (max_transitions=0)
- ✅ Query by key_id, state, timestamp
- ✅ Thread-safety

**Query Interface (15 tests)**
- ✅ Filter by key_id
- ✅ Filter by provider_id
- ✅ Filter by state
- ✅ Filter by timestamp range
- ✅ Pagination (limit and offset)
- ✅ Multiple filter combination
- ✅ Performance <10ms for typical queries
- ✅ Empty results handling

## Running Specific Tests

### Run Tests by Category

```bash
# Test only key storage
python -m pytest tests/unit/test_memory_store.py::TestInMemoryStateStoreKeyStorage -v

# Test only query interface
python -m pytest tests/unit/test_memory_store.py::TestInMemoryStateStoreOtherMethods -v -k "query"

# Test only routing decisions
python -m pytest tests/unit/test_memory_store.py::TestInMemoryStateStoreOtherMethods -v -k "routing"

# Test only state transitions
python -m pytest tests/unit/test_memory_store.py::TestInMemoryStateStoreOtherMethods -v -k "transition"

# Test only quota states
python -m pytest tests/unit/test_memory_store.py::TestInMemoryStateStoreOtherMethods -v -k "quota"
```

### Run Performance Tests

```bash
python -m pytest tests/unit/test_memory_store.py -v -k "performance"
```

### Run Thread-Safety Tests

```bash
python -m pytest tests/unit/test_memory_store.py -v -k "thread_safety or concurrent"
```

## Manual Testing Examples

### Example 1: Basic Usage

```python
import asyncio
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore
from apikeyrouter.domain.models.api_key import APIKey

async def main():
    store = InMemoryStateStore()
    
    # Save a key
    key = APIKey(
        id="my_key",
        key_material="encrypted_key",
        provider_id="openai"
    )
    await store.save_key(key)
    
    # Retrieve the key
    retrieved = await store.get_key("my_key")
    print(f"Retrieved key: {retrieved.id}")

asyncio.run(main())
```

### Example 2: Query Operations

```python
from apikeyrouter.domain.interfaces.state_store import StateQuery

# Query all keys for a provider
query = StateQuery(
    entity_type="APIKey",
    provider_id="openai",
    state="available"
)
results = await store.query_state(query)
print(f"Found {len(results)} available OpenAI keys")

# Query with pagination
query = StateQuery(
    entity_type="RoutingDecision",
    limit=50,
    offset=0
)
decisions = await store.query_state(query)
```

### Example 3: Limit Configuration

```python
# Create store with limits
store = InMemoryStateStore(
    max_decisions=100,      # Keep only last 100 routing decisions
    max_transitions=1000    # Keep only last 1000 state transitions
)

# Unlimited storage
store_unlimited = InMemoryStateStore(
    max_decisions=0,        # No limit on decisions
    max_transitions=0       # No limit on transitions
)
```

## Performance Testing

### Expected Performance

- **save_key**: <1ms
- **get_key**: <1ms
- **query_state**: <10ms for typical queries (100-1000 items)

### Run Performance Benchmarks

```bash
python -m pytest tests/unit/test_memory_store.py -v -k "performance" --benchmark-only
```

Or use the manual test script:

```bash
python test_manual_example.py
```

## Integration Testing

### Test with Real Components

```python
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore
from apikeyrouter.domain.components.key_manager import KeyManager

# Use InMemoryStateStore with KeyManager
store = InMemoryStateStore()
key_manager = KeyManager(state_store=store, ...)

# Test key registration
await key_manager.register_key(...)
```

## Test Output Interpretation

### Successful Test Run

```
============================= 63 passed in 1.44s ==============================
```

All tests passed! ✅

### Failed Test

```
FAILED tests/unit/test_memory_store.py::TestInMemoryStateStoreKeyStorage::test_save_key
AssertionError: assert 'key1' in store._keys
```

Check the error message and fix the issue.

## Coverage Report

To see test coverage:

```bash
python -m pytest tests/unit/test_memory_store.py --cov=apikeyrouter.infrastructure.state_store --cov-report=html
```

Then open `htmlcov/index.html` in your browser.

## Common Test Scenarios

### Scenario 1: Store and Query Keys

```python
# Create store
store = InMemoryStateStore()

# Add multiple keys
for i in range(10):
    key = APIKey(id=f"key_{i}", key_material="encrypted", provider_id="openai")
    await store.save_key(key)

# Query by provider
query = StateQuery(entity_type="APIKey", provider_id="openai")
results = await store.query_state(query)
assert len(results) == 10
```

### Scenario 2: Track Quota State

```python
# Save quota state
quota = QuotaState(
    id="quota1",
    key_id="key1",
    remaining_capacity=CapacityEstimate(value=5000),
    reset_at=datetime.utcnow() + timedelta(days=1)
)
await store.save_quota_state(quota)

# Retrieve quota state
quota = await store.get_quota_state("key1")
print(f"Remaining capacity: {quota.remaining_capacity.value}")
```

### Scenario 3: Audit Trail

```python
# Save routing decision
decision = RoutingDecision(...)
await store.save_routing_decision(decision)

# Save state transition
transition = StateTransition(...)
await store.save_state_transition(transition)

# Query audit trail
query = StateQuery(
    entity_type="RoutingDecision",
    timestamp_from=datetime(2024, 1, 1),
    timestamp_to=datetime(2024, 1, 31)
)
audit_log = await store.query_state(query)
```

## Troubleshooting

### Issue: Tests fail with import errors

**Solution**: Make sure you're in the `packages/core` directory and have installed dependencies:
```bash
cd packages/core
poetry install  # or pip install -e .
```

### Issue: Performance tests fail

**Solution**: Performance can vary by system. The tests use reasonable thresholds. If consistently failing, check:
- System load
- Python version (should be 3.11+)
- Other processes using CPU

### Issue: Concurrent test failures

**Solution**: These tests verify thread-safety. If they fail, there may be a race condition. Check:
- Lock usage in save operations
- Dictionary read safety

## Next Steps

1. ✅ Run all tests: `python -m pytest tests/unit/test_memory_store.py -v`
2. ✅ Run manual test: `python test_manual_example.py`
3. ✅ Review test coverage
4. ✅ Integrate with other components
5. ✅ Test in your application

## Additional Resources

- **Source Code**: `packages/core/apikeyrouter/infrastructure/state_store/memory_store.py`
- **Test Code**: `packages/core/tests/unit/test_memory_store.py`
- **Interface Definition**: `packages/core/apikeyrouter/domain/interfaces/state_store.py`
- **Documentation**: See docstrings in source files

