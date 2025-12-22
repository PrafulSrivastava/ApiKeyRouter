# Test Strategy and Standards

Comprehensive testing strategy covering unit tests, integration tests, end-to-end tests, and performance benchmarks. Testing ensures correctness, reliability, and validates the "lightweight library" claim through continuous benchmarking.

## Testing Philosophy

**Approach:** Test-driven development (TDD) for critical components, test-after for infrastructure

**Coverage Goals:**
- **Unit Tests:** 90%+ coverage for domain logic (KeyManager, RoutingEngine, QuotaAwarenessEngine)
- **Integration Tests:** 80%+ coverage for component interactions
- **End-to-End Tests:** Critical user journeys (request routing, failure handling, key switching)
- **Benchmarks:** All routing decisions, quota calculations, cost estimations benchmarked

**Test Pyramid:**
- **Unit Tests:** 70% (fast, isolated, comprehensive)
- **Integration Tests:** 20% (component interactions, adapters)
- **End-to-End Tests:** 10% (full system, critical paths)
- **Benchmarks:** Continuous (performance regression detection)

## Test Types and Organization

### Unit Tests

**Framework:** pytest 7.4.4

**File Convention:** `test_<module_name>.py` (mirrors source structure)

**Location:** `tests/unit/` (mirrors `apikeyrouter/domain/components/`)

**Mocking Library:** pytest-mock (built on unittest.mock)

**Coverage Requirement:** 90%+ for domain components

**AI Agent Requirements:**
- Generate tests for all public methods
- Cover edge cases and error conditions
- Follow AAA pattern (Arrange, Act, Assert)
- Mock all external dependencies (StateStore, ProviderAdapter, ObservabilityManager)

**Example Structure:**
```
tests/unit/
├── test_key_manager.py
├── test_quota_awareness_engine.py
├── test_routing_engine.py
├── test_failure_handler.py
├── test_cost_controller.py
└── test_policy_engine.py
```

**Test Example:**
```python
import pytest
from apikeyrouter.domain.components.key_manager import KeyManager
from apikeyrouter.domain.models import APIKey, KeyState

@pytest.mark.asyncio
async def test_update_key_state_transitions_to_throttled():
    # Arrange
    key_manager = KeyManager(state_store=mock_state_store)
    key = await key_manager.register_key("sk-test", "openai", {})
    
    # Act
    transition = await key_manager.update_key_state(
        key.id, KeyState.Throttled, reason="rate_limit"
    )
    
    # Assert
    assert transition.from_state == KeyState.Available
    assert transition.to_state == KeyState.Throttled
    assert transition.trigger == "rate_limit"
    updated_key = await key_manager.get_key(key.id)
    assert updated_key.state == KeyState.Throttled
```

### Integration Tests

**Scope:** Component interactions, adapter implementations, state store backends

**Location:** `tests/integration/`

**Test Infrastructure:**
- **Database:** Testcontainers MongoDB for integration tests (optional, can use in-memory)
- **HTTP Client:** httpx with respx for mocking provider APIs
- **State Store:** Test both in-memory and MongoDB implementations

**Test Categories:**
1. **Component Integration:** KeyManager + QuotaAwarenessEngine + RoutingEngine
2. **Adapter Integration:** Provider adapters with mocked HTTP responses
3. **State Store Integration:** MongoDB state store with real database
4. **End-to-End Component:** Full request flow through router

**Example Structure:**
```
tests/integration/
├── test_provider_adapters.py      # Adapter + HTTP mocking
├── test_state_store_mongo.py      # MongoDB integration
├── test_routing_flow.py           # Full routing flow
└── test_failure_handling.py       # Failure scenarios
```

**Test Example:**
```python
import pytest
from httpx import AsyncClient
from respx import MockRouter
from apikeyrouter.domain.infrastructure.adapters.openai_adapter import OpenAIAdapter

@pytest.mark.asyncio
async def test_openai_adapter_executes_request(respx_mock: MockRouter):
    # Arrange
    adapter = OpenAIAdapter()
    respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [...]})
    )
    
    # Act
    response = await adapter.execute_request(intent, key)
    
    # Assert
    assert response.content is not None
    assert respx_mock.calls.call_count == 1
```

### End-to-End Tests

**Framework:** pytest 7.4.4 with pytest-asyncio

**Scope:** Full system tests (library + proxy), critical user journeys

**Environment:** Test environment with real provider APIs (sandbox/test keys)

**Test Data:** Fixtures for test keys, providers, policies

**Critical Test Scenarios:**
1. **Request Routing:** Register keys → Route request → Verify key selection
2. **Automatic Key Switching:** Key fails → System switches to different key
3. **Quota Exhaustion:** Key exhausted → System routes to available key
4. **Budget Enforcement:** Budget exceeded → Request rejected
5. **Failure Recovery:** Key throttled → System recovers automatically

**Example Structure:**
```
tests/e2e/
├── test_request_routing.py
├── test_key_switching.py
├── test_quota_awareness.py
├── test_cost_control.py
└── test_failure_recovery.py
```

**Test Example:**
```python
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_automatic_key_switching_on_rate_limit():
    # Arrange
    router = ApiKeyRouter()
    router.register_provider("openai", OpenAIAdapter())
    key1 = await router.register_key("sk-key1", "openai")
    key2 = await router.register_key("sk-key2", "openai")
    
    # Mock: key1 rate limited, key2 succeeds
    mock_provider.side_effect = [
        RateLimitError(),  # key1 fails
        MockResponse(200)  # key2 succeeds
    ]
    
    # Act
    response = await router.route(request_intent)
    
    # Assert
    assert response.success
    assert response.metadata.key_used == key2.id
    # Verify key1 state updated
    key1_state = await router.get_key_state(key1.id)
    assert key1_state == KeyState.Throttled
```

### Performance Benchmarks

**Framework:** pytest-benchmark 4.0.0

**Location:** `tests/benchmarks/`

**Benchmark Categories:**
1. **Routing Performance:** Time to select key (target: <10ms)
2. **Quota Calculation:** Time to calculate quota state (target: <5ms)
3. **Cost Estimation:** Time to estimate cost (target: <2ms)
4. **State Updates:** Time to update key/quota state (target: <1ms)
5. **End-to-End Latency:** Full request routing overhead (target: <50ms vs direct API call)

**Benchmark Requirements:**
- All benchmarks run in CI on every commit
- Performance regression detection (fail if >10% slower)
- Compare against baseline (competitor performance)
- Track performance trends over time

**Benchmark Example:**
```python
import pytest
from apikeyrouter.domain.components.routing_engine import RoutingEngine

def test_routing_decision_performance(benchmark):
    # Arrange
    routing_engine = RoutingEngine(...)
    eligible_keys = [key1, key2, key3]
    objective = RoutingObjective(primary="cost")
    
    # Act & Assert
    result = benchmark(
        routing_engine.select_best_key,
        eligible_keys,
        objective
    )
    
    # Performance assertion
    assert result is not None
    # Benchmark framework reports timing automatically
```

**CI Integration:**
```yaml
# .github/workflows/benchmark.yml
- name: Run Benchmarks
  run: |
    pytest tests/benchmarks/ --benchmark-only --benchmark-json=benchmark.json
    
- name: Compare with Baseline
  run: |
    python scripts/compare_benchmarks.py benchmark.json baseline.json
```

**Load Testing:**
- **Tool:** locust 2.24.1
- **Scope:** Proxy service throughput and latency
- **Targets:** 1000+ requests/second, <100ms p95 latency
- **Scenarios:** 
  - Normal load (baseline)
  - High load (stress test)
  - Failure scenarios (degraded performance)

## Test Data Management

**Strategy:** Fixtures + factories for test data generation

**Fixtures:** `tests/fixtures/test_data.py`

**Factories:** Pydantic model factories for easy test data creation

**Cleanup:** Automatic cleanup after each test (pytest fixtures)

**Test Data Examples:**
```python
# tests/fixtures/test_data.py
@pytest.fixture
def sample_api_key():
    return APIKey(
        id="test_key_1",
        provider_id="openai",
        state=KeyState.Available,
        created_at=datetime.now()
    )

@pytest.fixture
def sample_quota_state(sample_api_key):
    return QuotaState(
        key_id=sample_api_key.id,
        capacity_state=CapacityState.Abundant,
        remaining_capacity=CapacityEstimate(value=10000, confidence=1.0)
    )
```

**Mock Data:**
- **Provider Responses:** Mock HTTP responses for all provider APIs
- **State Store:** In-memory state store for fast tests
- **External Services:** Mock MongoDB, Redis (use real for integration tests)

## Continuous Testing

**CI Integration:** GitHub Actions

**Test Stages:**
1. **Linting:** ruff check (fast, fails fast)
2. **Type Checking:** mypy (catches type errors)
3. **Unit Tests:** pytest tests/unit/ (fast, comprehensive)
4. **Integration Tests:** pytest tests/integration/ (slower, requires setup)
5. **Benchmarks:** pytest tests/benchmarks/ (performance validation)
6. **E2E Tests:** pytest tests/e2e/ (slow, requires test environment)

**Performance Tests:**
- **Benchmark Regression:** Fail if performance degrades >10%
- **Load Testing:** Run on schedule (nightly), not on every commit
- **Performance Trends:** Track metrics over time (Grafana dashboard)

**Security Tests:**
- **Dependency Scanning:** Dependabot for vulnerability scanning
- **Secret Scanning:** GitHub secret scanning
- **Code Analysis:** Bandit for security issues (optional)

## Test Coverage Requirements

**Minimum Coverage:**
- **Domain Components:** 90%+ (KeyManager, RoutingEngine, QuotaAwarenessEngine)
- **Infrastructure:** 80%+ (Adapters, StateStore implementations)
- **API Layer:** 70%+ (FastAPI routes, middleware)

**Coverage Tools:**
- **pytest-cov:** Coverage measurement
- **Coverage.py:** Coverage reporting
- **Codecov:** Coverage tracking and reporting

**Coverage Exclusions:**
- Type checking code (`if TYPE_CHECKING:` blocks)
- Debug/development code
- Exception handling boilerplate

## Test Organization Best Practices

**Test Naming:**
- `test_<functionality>_<scenario>_<expected_outcome>`
- Example: `test_update_key_state_transitions_to_throttled_when_rate_limited`

**Test Structure:**
- One test class per component
- One test method per scenario
- Use fixtures for setup/teardown

**Test Isolation:**
- Each test is independent (no shared state)
- Use fixtures for test data (not global variables)
- Clean up after each test (automatic via fixtures)

**Test Speed:**
- Unit tests: <100ms each
- Integration tests: <1s each
- E2E tests: <5s each
- Total test suite: <5 minutes

---

**Select 1-9 or just type your question/feedback:**

1. Proceed to next section (Security)
2. Challenge assumptions
3. Explore alternatives
4. Deep dive analysis
5. Risk assessment
6. Stakeholder perspective
7. Scenario planning
8. Constraint analysis
9. Expert consultation

Or type your feedback/questions about the Test Strategy and Standards section.
