# Comprehensive Testing Guide for ApiKeyRouter

This guide provides a complete overview of all tests you can perform to verify the functionality of your ApiKeyRouter implementation.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Unit Tests](#unit-tests)
3. [Integration Tests](#integration-tests)
4. [End-to-End Tests](#end-to-end-tests)
5. [Performance Benchmarks](#performance-benchmarks)
6. [Functional Verification Tests](#functional-verification-tests)
7. [Manual Testing Scenarios](#manual-testing-scenarios)
8. [Test Coverage Analysis](#test-coverage-analysis)

---

## Quick Start

### Run All Tests

```bash
# From packages/core directory
cd packages/core

# Run all tests with coverage
poetry run pytest --cov=apikeyrouter --cov-report=html --cov-report=term

# Run all tests (verbose)
poetry run pytest -v

# Run specific test category
poetry run pytest tests/unit/ -v          # Unit tests only
poetry run pytest tests/integration/ -v   # Integration tests only
poetry run pytest tests/benchmarks/ -v    # Performance benchmarks
```

### Check Test Coverage

```bash
# Generate HTML coverage report
poetry run pytest --cov=apikeyrouter --cov-report=html

# Open coverage report
# Windows: start htmlcov/index.html
# Mac/Linux: open htmlcov/index.html
```

---

## Unit Tests

**Location:** `tests/unit/`  
**Purpose:** Test individual components in isolation  
**Coverage Target:** 90%+ for domain components

### Available Unit Test Files

1. **Core Components:**
   ```bash
   poetry run pytest tests/unit/test_key_manager.py -v
   poetry run pytest tests/unit/test_routing_engine.py -v
   poetry run pytest tests/unit/test_quota_awareness_engine.py -v
   poetry run pytest tests/unit/test_cost_controller.py -v
   poetry run pytest tests/unit/test_router.py -v
   ```

2. **Routing Strategies:**
   ```bash
   poetry run pytest tests/unit/test_cost_optimized_strategy.py -v
   poetry run pytest tests/unit/test_reliability_optimized_strategy.py -v
   poetry run pytest tests/unit/test_fairness_strategy.py -v
   ```

3. **State Management:**
   ```bash
   poetry run pytest tests/unit/test_state_store.py -v
   poetry run pytest tests/unit/test_memory_store.py -v
   ```

4. **Models & Validation:**
   ```bash
   poetry run pytest tests/unit/test_api_key.py -v
   poetry run pytest tests/unit/test_quota_state.py -v
   poetry run pytest tests/unit/test_routing_decision.py -v
   poetry run pytest tests/unit/test_request_intent.py -v
   poetry run pytest tests/unit/test_system_response.py -v
   poetry run pytest tests/unit/test_validation.py -v
   ```

5. **Security:**
   ```bash
   poetry run pytest tests/unit/test_encryption.py -v
   poetry run pytest tests/unit/test_secure_storage.py -v
   ```

6. **Adapters:**
   ```bash
   poetry run pytest tests/unit/test_provider_adapter.py -v
   ```

### What Unit Tests Verify

- ✅ **KeyManager**: Key registration, state transitions, eligibility filtering
- ✅ **RoutingEngine**: Routing decisions, objective-based selection, strategy application
- ✅ **QuotaAwarenessEngine**: Capacity tracking, exhaustion prediction, quota resets
- ✅ **CostController**: Cost estimation, budget enforcement, reconciliation
- ✅ **PolicyEngine**: Policy evaluation, precedence, validation
- ✅ **StateStore**: CRUD operations, query interface, thread-safety
- ✅ **Models**: Data validation, serialization, edge cases

### Run Specific Test Scenarios

```bash
# Test key state transitions
poetry run pytest tests/unit/test_key_manager.py -v -k "state"

# Test routing objectives
poetry run pytest tests/unit/test_routing_engine.py -v -k "objective"

# Test quota calculations
poetry run pytest tests/unit/test_quota_awareness_engine.py -v -k "capacity"

# Test budget enforcement
poetry run pytest tests/unit/test_cost_controller.py -v -k "budget"
```

---

## Integration Tests

**Location:** `tests/integration/`  
**Purpose:** Test component interactions and real implementations  
**Coverage Target:** 80%+ for component interactions

### Available Integration Test Files

1. **Core Workflows:**
   ```bash
   poetry run pytest tests/integration/test_routing_flow.py -v
   poetry run pytest tests/integration/test_key_management.py -v
   poetry run pytest tests/integration/test_quota_awareness.py -v
   poetry run pytest tests/integration/test_cost_control.py -v
   poetry run pytest tests/integration/test_failure_handling.py -v
   ```

2. **Provider Adapters:**
   ```bash
   poetry run pytest tests/integration/test_openai_adapter.py -v
   poetry run pytest tests/integration/test_openai_adapter_cost.py -v
   poetry run pytest tests/integration/test_openai_adapter_health.py -v
   ```

3. **MongoDB State Store:**
   ```bash
   # Requires MongoDB running (or use testcontainers)
   poetry run pytest tests/integration/test_state_store_mongo.py -v
   poetry run pytest tests/integration/test_mongo_models.py -v
   poetry run pytest tests/integration/test_mongo_store_key_storage.py -v
   poetry run pytest tests/integration/test_mongo_store_quota_storage.py -v
   poetry run pytest tests/integration/test_mongo_store_audit_trail.py -v
   poetry run pytest tests/integration/test_mongo_store_query_interface.py -v
   ```

### What Integration Tests Verify

- ✅ **End-to-End Routing**: Full request flow from intent to response
- ✅ **Key Lifecycle**: Registration → Usage → State Updates → Revocation
- ✅ **Quota Tracking**: Capacity updates, exhaustion detection, resets
- ✅ **Cost Control**: Budget checks, enforcement, reconciliation
- ✅ **Failure Handling**: Error classification, retries, recovery
- ✅ **Adapter Integration**: Real HTTP calls (mocked), response normalization
- ✅ **State Persistence**: MongoDB storage, retrieval, queries

### Run Specific Integration Scenarios

```bash
# Test complete routing workflow
poetry run pytest tests/integration/test_routing_flow.py -v -k "workflow"

# Test automatic key switching
poetry run pytest tests/integration/test_failure_handling.py -v -k "switch"

# Test quota exhaustion handling
poetry run pytest tests/integration/test_quota_awareness.py -v -k "exhaustion"

# Test budget enforcement
poetry run pytest tests/integration/test_cost_control.py -v -k "enforcement"
```

---

## End-to-End Tests

**Location:** `tests/e2e/` (may need to be created)  
**Purpose:** Test full system with real or near-real scenarios  
**Coverage Target:** Critical user journeys

### Recommended E2E Test Scenarios

Create these test files to verify complete functionality:

#### 1. Request Routing Journey
**File:** `tests/e2e/test_request_routing.py`

```python
"""E2E: Complete request routing from registration to response."""
# Test scenarios:
# - Register multiple keys → Route request → Verify key selection
# - Route with different objectives (cost, reliability, fairness)
# - Verify routing decision explanation
# - Verify observability events emitted
```

#### 2. Automatic Key Switching
**File:** `tests/e2e/test_key_switching.py`

```python
"""E2E: Automatic key switching on failures."""
# Test scenarios:
# - Key fails → System switches to backup key
# - All keys fail → System returns appropriate error
# - Key recovers → System uses it again
# - Verify state transitions recorded
```

#### 3. Quota Exhaustion Handling
**File:** `tests/e2e/test_quota_exhaustion.py`

```python
"""E2E: Quota exhaustion detection and handling."""
# Test scenarios:
# - Key exhausted → System routes to available key
# - All keys exhausted → System rejects request
# - Quota resets → System uses key again
# - Verify exhaustion predictions
```

#### 4. Budget Enforcement
**File:** `tests/e2e/test_budget_enforcement.py`

```python
"""E2E: Budget enforcement in hard and soft modes."""
# Test scenarios:
# - Budget exceeded → Request rejected (hard mode)
# - Budget exceeded → Request allowed with warning (soft mode)
# - Budget reset → Requests allowed again
# - Verify cost reconciliation
```

#### 5. Failure Recovery
**File:** `tests/e2e/test_failure_recovery.py`

```python
"""E2E: Failure recovery and circuit breaker."""
# Test scenarios:
# - Key throttled → System marks as throttled
# - Key recovers → System automatically uses it
# - Circuit breaker opens/closes
# - Verify retry logic
```

### Run E2E Tests

```bash
# Run all E2E tests
poetry run pytest tests/e2e/ -v -m e2e

# Run specific E2E scenario
poetry run pytest tests/e2e/test_request_routing.py -v
```

---

## Performance Benchmarks

**Location:** `tests/benchmarks/`  
**Purpose:** Verify performance meets requirements  
**Targets:** <10ms routing, <5ms quota calc, <2ms cost estimation

### Available Benchmark Files

```bash
# Run all benchmarks
poetry run pytest tests/benchmarks/ -v --benchmark-only

# Run specific benchmarks
poetry run pytest tests/benchmarks/benchmark_routing.py -v --benchmark-only
poetry run pytest tests/benchmarks/benchmark_quota.py -v --benchmark-only
poetry run pytest tests/benchmarks/benchmark_key_lookup.py -v --benchmark-only

# Check performance thresholds
poetry run pytest tests/benchmarks/check_performance_thresholds.py -v
```

### What Benchmarks Verify

- ✅ **Routing Performance**: Key selection time (<10ms target)
- ✅ **Quota Calculation**: Capacity state calculation (<5ms target)
- ✅ **Cost Estimation**: Cost calculation (<2ms target)
- ✅ **Key Lookup**: State store retrieval (<1ms target)
- ✅ **State Updates**: State persistence (<1ms target)

### Performance Regression Detection

```bash
# Compare against baseline
poetry run pytest tests/benchmarks/ --benchmark-only --benchmark-json=benchmark.json

# Check if performance degraded >10%
python tests/benchmarks/check_performance_thresholds.py benchmark.json baseline.json
```

---

## Functional Verification Tests

These are manual or scripted tests to verify specific functionalities work as expected.

### 1. Key Registration & Management

```bash
# Run manual example (comprehensive demonstration)
python test_manual_example.py
```

**What to Verify:**
- ✅ Keys can be registered with different providers
- ✅ Keys can be retrieved by ID
- ✅ Keys can be revoked
- ✅ Key metadata is stored correctly
- ✅ Key state transitions work (Available → Throttled → Available)

### 2. Routing Functionality

**Test Cost-Optimized Routing:**
```python
# Create router with multiple keys having different costs
# Route requests with cost objective
# Verify cheapest key is selected
```

**Test Reliability-Optimized Routing:**
```python
# Create router with keys having different reliability scores
# Route requests with reliability objective
# Verify most reliable key is selected
```

**Test Fairness Routing:**
```python
# Create router with multiple keys
# Route many requests
# Verify keys are used fairly (balanced usage)
```

### 3. Quota Awareness

**Test Capacity Tracking:**
```python
# Register keys with quota limits
# Make requests that consume quota
# Verify remaining capacity decreases
# Verify capacity state updates (Abundant → Limited → Exhausted)
```

**Test Exhaustion Prediction:**
```python
# Set up keys with usage patterns
# Verify exhaustion predictions are calculated
# Verify predictions update as usage changes
```

### 4. Cost Control

**Test Budget Enforcement (Hard Mode):**
```python
# Set budget limit
# Make requests until budget exceeded
# Verify requests are rejected with BudgetExceededError
```

**Test Budget Enforcement (Soft Mode):**
```python
# Set budget limit with soft enforcement
# Make requests beyond budget
# Verify requests are allowed but warnings logged
```

**Test Cost Reconciliation:**
```python
# Make requests with cost estimates
# Verify actual costs are tracked
# Verify reconciliation calculates differences
```

### 5. Failure Handling

**Test Automatic Retry:**
```python
# Configure retry policy
# Simulate transient failures
# Verify system retries automatically
# Verify permanent failures are not retried
```

**Test Circuit Breaker:**
```python
# Simulate repeated failures on a key
# Verify circuit breaker opens
# Verify key is not used while circuit is open
# Verify circuit breaker closes after recovery period
```

### 6. State Persistence

**Test In-Memory Store:**
```python
# Use InMemoryStateStore
# Save and retrieve keys, quota states, routing decisions
# Verify data persists during router lifetime
```

**Test MongoDB Store (if configured):**
```python
# Use MongoStateStore
# Save data, restart router
# Verify data persists across restarts
# Verify queries work correctly
```

---

## Manual Testing Scenarios

### Scenario 1: Basic Request Routing

```python
import asyncio
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message

async def test_basic_routing():
    router = ApiKeyRouter()
    
    # Register provider
    from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter
    router.register_provider("openai", OpenAIAdapter())
    
    # Register keys
    key1 = await router.register_key("sk-test-key-1", "openai", {"cost_per_1k": 0.002})
    key2 = await router.register_key("sk-test-key-2", "openai", {"cost_per_1k": 0.003})
    
    # Create request
    intent = RequestIntent(
        provider_id="openai",
        model="gpt-4",
        messages=[Message(role="user", content="Hello")]
    )
    
    # Route request (will use mocked adapter in tests)
    response = await router.route(intent)
    
    print(f"Response success: {response.success}")
    print(f"Key used: {response.metadata.key_used}")
    
asyncio.run(test_basic_routing())
```

### Scenario 2: Multi-Objective Routing

```python
from apikeyrouter.domain.models.routing_decision import RoutingObjective, ObjectiveType

# Test cost optimization
objective = RoutingObjective(primary=ObjectiveType.COST)
response = await router.route(intent, objective=objective)
# Verify cheapest key selected

# Test reliability optimization
objective = RoutingObjective(primary=ObjectiveType.RELIABILITY)
response = await router.route(intent, objective=objective)
# Verify most reliable key selected

# Test fairness
objective = RoutingObjective(primary=ObjectiveType.FAIRNESS)
# Make multiple requests
# Verify keys used fairly
```

### Scenario 3: Quota Exhaustion

```python
# Set up key with limited quota
quota_state = QuotaState(
    key_id=key.id,
    remaining_capacity=CapacityEstimate(value=1000),
    capacity_state=CapacityState.Limited
)
await router.quota_awareness_engine.update_quota_state(quota_state)

# Make requests until quota exhausted
# Verify system switches to other keys
# Verify exhausted key is not selected
```

### Scenario 4: Budget Enforcement

```python
from apikeyrouter.domain.models.budget import Budget, BudgetScope, EnforcementMode

# Set budget
budget = Budget(
    scope=BudgetScope.GLOBAL,
    limit=Decimal("10.00"),
    enforcement_mode=EnforcementMode.HARD
)
router.cost_controller.set_budget(budget)

# Make requests
# Verify requests rejected when budget exceeded
```

---

## Test Coverage Analysis

### Check Current Coverage

```bash
# Generate coverage report
poetry run pytest --cov=apikeyrouter --cov-report=html --cov-report=term

# View coverage by module
poetry run pytest --cov=apikeyrouter --cov-report=term-missing
```

### Coverage Targets

- **Domain Components**: 90%+ (KeyManager, RoutingEngine, QuotaAwarenessEngine)
- **Infrastructure**: 80%+ (Adapters, StateStore implementations)
- **Models**: 95%+ (Data validation, serialization)

### Identify Gaps

```bash
# Find untested code
poetry run pytest --cov=apikeyrouter --cov-report=term-missing | grep -E "^\s+[0-9]+\s+[0-9]+\s+[0-9]+%"
```

---

## Test Execution Strategies

### 1. Development Workflow

```bash
# Run fast tests during development
poetry run pytest tests/unit/ -v --tb=short

# Run specific component tests
poetry run pytest tests/unit/test_key_manager.py -v

# Run with coverage for new code
poetry run pytest tests/unit/test_key_manager.py --cov=apikeyrouter.domain.components.key_manager --cov-report=term
```

### 2. Pre-Commit Checks

```bash
# Run linting
poetry run ruff check .

# Run type checking
poetry run mypy apikeyrouter

# Run unit tests
poetry run pytest tests/unit/ -v

# Run integration tests (if fast enough)
poetry run pytest tests/integration/ -v --maxfail=1
```

### 3. CI/CD Pipeline

```bash
# Full test suite
poetry run pytest --cov=apikeyrouter --cov-report=xml

# Performance benchmarks
poetry run pytest tests/benchmarks/ --benchmark-only --benchmark-json=benchmark.json

# Check performance regression
python tests/benchmarks/check_performance_thresholds.py benchmark.json baseline.json
```

### 4. Release Validation

```bash
# Run all tests
poetry run pytest -v

# Run with coverage (must meet thresholds)
poetry run pytest --cov=apikeyrouter --cov-report=term --cov-fail-under=85

# Run benchmarks (must not regress)
poetry run pytest tests/benchmarks/ --benchmark-only

# Run E2E tests
poetry run pytest tests/e2e/ -v -m e2e

# Manual verification
python test_manual_example.py
```

---

## Troubleshooting Tests

### Common Issues

1. **Import Errors**
   ```bash
   # Make sure you're in packages/core directory
   cd packages/core
   poetry install
   ```

2. **Async Test Failures**
   ```bash
   # Ensure pytest-asyncio is installed
   poetry add --group dev pytest-asyncio
   ```

3. **MongoDB Tests Failing**
   ```bash
   # Either start MongoDB or use testcontainers
   # Skip MongoDB tests if not needed
   poetry run pytest tests/integration/ -v -k "not mongo"
   ```

4. **Performance Test Failures**
   ```bash
   # Performance can vary by system
   # Check system load and Python version
   python --version  # Should be 3.11+
   ```

---

## Next Steps

1. ✅ **Run all existing tests** to verify current functionality
2. ✅ **Check test coverage** to identify gaps
3. ✅ **Create E2E tests** for critical user journeys
4. ✅ **Run performance benchmarks** to verify performance targets
5. ✅ **Execute manual test scenarios** to verify end-user functionality
6. ✅ **Set up CI/CD** to run tests automatically

---

## Additional Resources

- **Test Strategy Document**: `docs/architecture/test-strategy-and-standards.md`
- **Testing Guide**: `TESTING_GUIDE.md` (for InMemoryStateStore)
- **Manual Example**: `test_manual_example.py`
- **API Reference**: `API_REFERENCE.md`

