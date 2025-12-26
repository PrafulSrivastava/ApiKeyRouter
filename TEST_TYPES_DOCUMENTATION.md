# Complete Test Types Documentation

This document lists all types of tests available in the ApiKeyRouter project.

## Test Categories Overview

The project includes **643+ tests** organized into the following categories:

1. **Unit Tests** (Fast, isolated component tests)
2. **Integration Tests** (Component interaction tests)
3. **Benchmark Tests** (Performance and load tests)
4. **Comparison Tests** (Router vs Direct API calls)
5. **End-to-End Tests** (Full system tests)
6. **API/HTTP Interface Tests** (FastAPI endpoint tests - equivalent to UI tests for backend)
7. **Linting & Static Analysis Tests** (Code quality and type checking)
8. **Security Tests** (Security and validation tests)
9. **Manual Tests** (Interactive testing scripts)

---

## 1. Unit Tests (`packages/core/tests/unit/`)

**Purpose:** Test individual components in isolation with mocked dependencies.

**Count:** ~400+ tests

### Test Files:

#### Core Components
- **`test_key_manager.py`** - Key registration, lifecycle, state management
  - Key registration and validation
  - Key state transitions (Available → Throttled → Exhausted)
  - Key rotation and revocation
  - Key material encryption/decryption
  - Key eligibility filtering

- **`test_routing_engine.py`** - Routing decision logic
  - Objective-based routing (cost, reliability, fairness)
  - Multi-objective routing with weights
  - Key selection algorithms
  - Routing decision generation

- **`test_quota_awareness_engine.py`** - Quota tracking and management
  - Capacity updates and tracking
  - Quota state calculations
  - Exhaustion prediction
  - Time window management

- **`test_cost_controller.py`** - Cost estimation and budget enforcement
  - Cost estimation
  - Budget creation and management
  - Budget enforcement (hard/soft)
  - Cost reconciliation

- **`test_cost_controller_hard_enforcement.py`** - Hard budget enforcement
  - Request rejection when budget exceeded
  - Per-provider budget limits
  - Per-key budget limits

- **`test_router.py`** - Main ApiKeyRouter orchestrator
  - Provider registration
  - Request routing flow
  - Error handling
  - Response generation

#### Routing Strategies
- **`test_cost_optimized_strategy.py`** - Cost optimization algorithm
  - Cost-based key selection
  - Cost estimation accuracy
  - Budget-aware filtering

- **`test_reliability_optimized_strategy.py`** - Reliability optimization
  - Success rate tracking
  - Failure rate consideration
  - Reliability scoring

- **`test_fairness_strategy.py`** - Fairness/load balancing
  - Even distribution across keys
  - Usage tracking
  - Fairness scoring

#### State Management
- **`test_state_store.py`** - StateStore interface validation
  - Abstract interface tests
  - Interface contract validation

- **`test_memory_store.py`** - InMemoryStateStore implementation
  - Key storage and retrieval
  - Quota state management
  - Routing decision storage
  - State transitions
  - Query interface
  - Concurrent operations

#### Data Models
- **`test_api_key.py`** - APIKey model validation
- **`test_quota_state.py`** - QuotaState model validation
- **`test_routing_decision.py`** - RoutingDecision model validation
- **`test_request_intent.py`** - RequestIntent model validation
- **`test_system_response.py`** - SystemResponse model validation

#### Security & Validation
- **`test_encryption.py`** - Encryption service
  - Key material encryption
  - Encryption key management
  - Decryption validation

- **`test_secure_storage.py`** - Secure storage practices
  - Key material never logged
  - Encryption at rest
  - Secure key rotation
  - Audit trail for key access

- **`test_validation.py`** - Input validation
  - Key material validation (length, format, injection detection)
  - Provider ID validation
  - Metadata validation
  - Request intent validation
  - SQL/NoSQL injection detection
  - Command injection detection
  - Path traversal detection

#### Infrastructure
- **`test_provider_adapter.py`** - ProviderAdapter interface
- **`test_policy_integration.py`** - Policy engine integration

---

## 2. Integration Tests (`packages/core/tests/integration/`)

**Purpose:** Test component interactions and real-world scenarios.

**Count:** ~150+ tests

### Test Files:

#### Core Workflows
- **`test_routing_flow.py`** - End-to-end routing workflows
  - Multi-key routing scenarios
  - Objective switching
  - Provider registration flow

- **`test_key_management.py`** - Key lifecycle integration
  - Key registration → usage → rotation → revocation
  - State transitions across components
  - Cooldown management

- **`test_quota_awareness.py`** - Quota management integration
  - Capacity updates and exhaustion
  - Quota-aware routing
  - Time window resets

- **`test_cost_control.py`** - Cost control integration
  - Budget enforcement in routing
  - Cost reconciliation
  - Multi-budget scenarios

- **`test_failure_handling.py`** - Failure and retry logic
  - Automatic failover
  - Retry with different keys
  - Error interpretation

#### Provider Adapters
- **`test_openai_adapter.py`** - OpenAI adapter integration
  - Request execution
  - Response parsing
  - Error handling

- **`test_openai_adapter_cost.py`** - OpenAI cost estimation
  - Token-based cost calculation
  - Model-specific pricing
  - Cost accuracy validation

- **`test_openai_adapter_health.py`** - OpenAI health checks
  - Connection validation
  - API availability checks

#### State Store Implementations
- **`test_state_store_mongo.py`** - MongoDB state store
  - Connection and configuration
  - Authentication handling
  - Error handling

- **`test_mongo_models.py`** - MongoDB Beanie models
  - Document field mappings
  - Index creation
  - Domain model conversion
  - Pydantic validation

- **`test_mongo_store_key_storage.py`** - MongoDB key storage
  - Key save/retrieve operations
  - Index usage
  - Concurrent operations

- **`test_mongo_store_quota_storage.py`** - MongoDB quota storage
  - Quota state persistence
  - Time window queries
  - Reset time tracking

- **`test_mongo_store_query_interface.py`** - MongoDB query interface
  - State queries by filters
  - Pagination
  - Timestamp range queries

- **`test_mongo_store_audit_trail.py`** - MongoDB audit trail
  - Routing decision storage
  - State transition logging
  - Time range queries
  - Append-only behavior

- **`test_state_store_redis.py`** - Redis state store (if implemented)
  - Redis connection
  - Key-value operations

---

## 3. Benchmark Tests (`packages/core/tests/benchmarks/`)

**Purpose:** Measure and validate performance characteristics.

**Count:** 10+ benchmark tests

### Test Files:

- **`benchmark_routing.py`** - Routing decision performance
  - `test_benchmark_routing_decision_time` - Routing decision latency
  - `test_benchmark_routing_decision_cost_objective` - Cost objective performance
  - `test_benchmark_routing_decision_reliability_objective` - Reliability objective performance

- **`benchmark_key_lookup.py`** - Key lookup performance
  - `test_benchmark_key_lookup_time` - Key lookup latency
  - `test_benchmark_key_manager_get_key_time` - KeyManager.get_key() performance
  - `test_benchmark_get_eligible_keys_time` - Eligible keys filtering performance
  - `test_benchmark_key_lookup_random_keys` - Random key lookup performance

- **`benchmark_quota.py`** - Quota operation performance
  - `test_benchmark_update_capacity_time` - Capacity update latency
  - `test_benchmark_get_quota_state_time` - Quota state retrieval performance
  - `test_benchmark_quota_calculation_with_multiple_updates` - Quota calculation with multiple updates

- **`check_performance_thresholds.py`** - Performance threshold validation
  - Validates benchmarks meet performance targets
  - Compares against baseline

### Performance Targets:
- Key lookup: p95 < 1ms
- Quota operations: p95 < 5ms
- Routing decisions: p95 < 10ms

---

## 4. Comparison Tests (`packages/core/tests/comparison/`)

**Purpose:** Compare ApiKeyRouter benefits vs direct API calls.

**Count:** 17+ tests

### Test Files:

- **`test_router_vs_direct.py`** - Direct comparison tests
  - `test_cost_optimization_router_vs_direct` - Cost savings demonstration
  - `test_reliability_automatic_failover` - Automatic failover benefits
  - `test_load_balancing_fairness` - Load balancing advantages
  - `test_budget_enforcement_prevents_overspend` - Budget protection
  - `test_quota_awareness_prevents_exhaustion` - Quota management benefits
  - `test_performance_overhead_minimal` - Performance overhead validation
  - `test_comprehensive_comparison` - Full feature comparison

- **`test_comprehensive_scenarios.py`** - Real-world scenario tests
  - `test_scenario_1_multi_provider_failover` - Multi-provider failover
  - `test_scenario_2_cost_aware_model_selection` - Cost-aware model selection
  - `test_scenario_3_rate_limit_recovery` - Rate limit handling
  - `test_scenario_4_quota_exhaustion_prevention` - Quota exhaustion prevention
  - `test_scenario_5_multi_tenant_isolation` - Multi-tenant scenarios
  - `test_scenario_6_geographic_compliance_routing` - Geographic routing
  - `test_scenario_7_priority_based_routing` - Priority-based routing
  - `test_scenario_8_cost_attribution_by_feature` - Cost attribution
  - `test_scenario_9_dynamic_key_rotation` - Dynamic key rotation
  - `test_scenario_10_circuit_breaker_pattern` - Circuit breaker pattern

---

## 5. End-to-End Tests (`packages/proxy/tests/`)

**Purpose:** Test the complete proxy service with HTTP API.

**Count:** 2+ test files

### Test Files:

- **`test_graceful_shutdown.py`** - Service lifecycle
  - Graceful shutdown handling
  - Request completion during shutdown

### Load Tests (`packages/proxy/tests/load/`)

- **`locustfile.py`** - Locust load testing configuration
  - Concurrent user simulation
  - Request rate testing
  - Performance under load

- **`check_load_test_results.py`** - Load test result validation

---

## 6. API/HTTP Interface Tests (`packages/proxy/tests/`)

**Purpose:** Test FastAPI HTTP endpoints and API interface (equivalent to UI tests for backend services).

**Count:** 44+ tests in `test_api_security.py`

### Test Files:

- **`test_api_security.py`** - FastAPI endpoint and middleware tests
  - **Authentication Tests** (`TestAuthentication` class)
    - Management API key retrieval
    - Bearer token validation
    - Missing/invalid authorization headers
    - Authentication middleware behavior
  
  - **CORS Tests** (`TestCORS` class)
    - CORS origin validation
    - CORS header injection
    - Preflight request handling
  
  - **Rate Limiting Tests** (`TestRateLimiting` class)
    - Rate limit enforcement
    - Rate limit headers
    - Rate limit reset behavior
  
  - **Security Headers Tests** (`TestSecurityHeaders` class)
    - Security header injection
    - HSTS configuration
    - XSS protection headers
  
  - **Authorization Rules Tests** (`TestAuthorizationRules` class)
    - Management API endpoint protection
    - Public endpoint access
    - HTTP method validation

### Test Approach:

- Uses **FastAPI `TestClient`** for HTTP endpoint testing
- Tests actual HTTP requests/responses (not just unit tests)
- Validates middleware behavior (auth, CORS, rate limiting, security headers)
- Tests both success and failure scenarios
- Validates HTTP status codes, headers, and response bodies

### Example Test Structure:

```python
def test_require_management_auth_valid(self):
    """Test require_management_auth dependency with valid Bearer token."""
    request = MagicMock()
    request.headers = {"Authorization": f"Bearer {self.test_api_key}"}
    # ... test logic
```

### Running API Tests:

```bash
# Run all API security tests
poetry run pytest packages/proxy/tests/test_api_security.py -v

# Run specific test class
poetry run pytest packages/proxy/tests/test_api_security.py::TestAuthentication -v

# Run with coverage
poetry run pytest packages/proxy/tests/test_api_security.py --cov=apikeyrouter_proxy
```

---

## 7. Linting & Static Analysis Tests

**Purpose:** Validate code quality, style, type safety, and security through static analysis.

**Tools Used:**
- **`ruff`** - Fast Python linter and formatter
- **`mypy`** - Static type checker
- **`bandit`** - Security vulnerability scanner

### Configuration:

#### Ruff Configuration (`pyproject.toml`)
```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
    "N",   # pep8-naming
    "SIM", # flake8-simplify
]
```

#### MyPy Configuration (`pyproject.toml`)
```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
strict_optional = true
# ... strict type checking settings
```

### CI/CD Integration:

Linting and static analysis run automatically in GitHub Actions (`.github/workflows/ci.yml`):

```yaml
- name: Run linting
  run: |
    poetry run ruff check packages/${{ matrix.package }}
    poetry run mypy packages/core/apikeyrouter --ignore-missing-imports
```

### Running Linting Tests Locally:

#### Ruff (Linting & Formatting)
```bash
# Check for linting errors
poetry run ruff check packages/core
poetry run ruff check packages/proxy

# Auto-fix linting errors
poetry run ruff check --fix packages/core
poetry run ruff check --fix packages/proxy

# Format code
poetry run ruff format packages/core
poetry run ruff format packages/proxy
```

#### MyPy (Type Checking)
```bash
# Type check core package
poetry run mypy packages/core/apikeyrouter --ignore-missing-imports

# Type check proxy package
poetry run mypy packages/proxy/apikeyrouter_proxy --ignore-missing-imports

# Type check with strict mode
poetry run mypy packages/core/apikeyrouter --strict --ignore-missing-imports
```

#### Bandit (Security Scanning)
```bash
# Security scan (runs in CI/CD)
poetry run bandit -r packages/core/apikeyrouter -f json -o bandit-report-core.json
poetry run bandit -r packages/proxy/apikeyrouter_proxy -f json -o bandit-report-proxy.json

# Security scan with high severity check
poetry run bandit -r packages/core/apikeyrouter -ll
```

### What Gets Checked:

#### Ruff Checks:
- ✅ Code style (PEP 8 compliance)
- ✅ Import organization (isort)
- ✅ Unused imports/variables
- ✅ Code simplification opportunities
- ✅ Python version compatibility (pyupgrade)
- ✅ Bug patterns (flake8-bugbear)
- ✅ Naming conventions (pep8-naming)

#### MyPy Checks:
- ✅ Type annotations correctness
- ✅ Missing type hints
- ✅ Type compatibility
- ✅ Return type validation
- ✅ Optional type handling
- ✅ Generic type usage

#### Bandit Checks:
- ✅ Security vulnerabilities
- ✅ Hardcoded secrets
- ✅ SQL injection risks
- ✅ Command injection risks
- ✅ Insecure random number generation
- ✅ Insecure SSL/TLS usage

### Linting Test Results:

Linting failures are treated as test failures in CI/CD:
- **Ruff errors** → Build fails
- **MyPy errors** → Build fails (with `--ignore-missing-imports` for third-party libs)
- **Bandit high severity** → Build fails

### Pre-commit Integration (Recommended):

You can set up pre-commit hooks to run linting before commits:

```bash
# Install pre-commit
poetry add --group dev pre-commit

# Create .pre-commit-config.yaml
# Run linting before each commit
pre-commit install
```

---

## 8. Security Tests

**Purpose:** Test security features and validation.

### Test Files:

#### Security & Validation
- **`test_encryption.py`** - Encryption service
  - Key material encryption
  - Encryption key management
  - Decryption validation

- **`test_secure_storage.py`** - Secure storage practices
  - Key material never logged
  - Encryption at rest
  - Secure key rotation
  - Audit trail for key access

- **`test_validation.py`** - Input validation
  - Key material validation (length, format, injection detection)
  - Provider ID validation
  - Metadata validation
  - Request intent validation
  - SQL/NoSQL injection detection
  - Command injection detection
  - Path traversal detection

---

## 9. Manual Tests

**Purpose:** Interactive testing and demonstration scripts.

### Test Files:

- **`packages/core/test_manual_example.py`** - Comprehensive manual test script
  - Full feature demonstration
  - Interactive testing
  - Example usage patterns
  - Validation of all features

---

## Test Markers and Categories

Tests can be run by category using pytest markers:

```bash
# Unit tests only
poetry run pytest -m unit

# Integration tests only
poetry run pytest -m integration

# Benchmark tests only
poetry run pytest -m benchmark --benchmark-only

# All tests except benchmarks
poetry run pytest -m "not benchmark"
```

---

## Test Statistics

### By Category:
- **Unit Tests:** ~400+ tests
- **Integration Tests:** ~150+ tests
- **Benchmark Tests:** 10+ tests
- **Comparison Tests:** 17+ tests
- **E2E Tests:** 2+ test files
- **API/HTTP Interface Tests:** 44+ tests
- **Linting & Static Analysis:** Automated in CI/CD (ruff, mypy, bandit)
- **Manual Tests:** 1 comprehensive script

### By Component:
- **Key Management:** ~130 tests
- **Routing Engine:** ~150 tests
- **Quota Awareness:** ~250 tests
- **Cost Control:** ~100 tests
- **State Store:** ~100 tests
- **Validation:** ~50 tests
- **Security:** ~30 tests
- **Provider Adapters:** ~40 tests

### By Test Type:
- **Async Tests:** 95%+ (all tests use async/await)
- **Mocked Tests:** Unit tests use mocks
- **Real Integration:** Integration tests use real components
- **Performance:** Benchmark tests measure actual performance

---

## Running Tests

### Run All Tests
```bash
poetry run pytest
```

### Run by Category
```bash
# Unit tests
poetry run pytest packages/core/tests/unit/

# Integration tests
poetry run pytest packages/core/tests/integration/

# Benchmarks
poetry run pytest packages/core/tests/benchmarks/ --benchmark-only

# Comparison tests
poetry run pytest packages/core/tests/comparison/

# Proxy tests (includes API/HTTP interface tests)
poetry run pytest packages/proxy/tests/

# API/HTTP interface tests specifically
poetry run pytest packages/proxy/tests/test_api_security.py -v
```

### Run Linting & Static Analysis
```bash
# Ruff linting
poetry run ruff check packages/core
poetry run ruff check packages/proxy

# Ruff formatting
poetry run ruff format packages/core
poetry run ruff format packages/proxy

# MyPy type checking
poetry run mypy packages/core/apikeyrouter --ignore-missing-imports
poetry run mypy packages/proxy/apikeyrouter_proxy --ignore-missing-imports

# Bandit security scanning
poetry run bandit -r packages/core/apikeyrouter -ll
poetry run bandit -r packages/proxy/apikeyrouter_proxy -ll
```

### Run Specific Test File
```bash
poetry run pytest packages/core/tests/unit/test_key_manager.py -v
```

### Run with Coverage
```bash
poetry run pytest --cov=packages/core/apikeyrouter --cov-report=html
```

---

## Test Coverage Goals

- **Unit Tests:** 90%+ coverage
- **Integration Tests:** Critical paths covered
- **Benchmark Tests:** All performance-critical operations
- **Security Tests:** All security features validated

---

## Test Dependencies

### Required:
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `pytest-cov` - Coverage reporting
- `pytest-benchmark` - Performance benchmarks
- `ruff` - Linting and formatting
- `mypy` - Type checking

### Optional (for specific tests):
- `motor` - MongoDB integration tests
- `redis` - Redis integration tests
- `httpx` - HTTP client for adapter tests
- `locust` - Load testing
- `bandit` - Security scanning (runs in CI/CD)
- `fastapi` - FastAPI TestClient for API tests

---

## Test Organization

```
packages/core/tests/
├── unit/              # Fast, isolated component tests
├── integration/       # Component interaction tests
├── benchmarks/        # Performance tests
├── comparison/        # Router vs Direct comparison
├── fixtures/          # Test data fixtures
└── conftest.py        # Pytest configuration

packages/proxy/tests/
├── test_api_security.py
├── test_graceful_shutdown.py
├── e2e/               # End-to-end tests
└── load/              # Load testing
```

---

## Summary

The ApiKeyRouter project has a **comprehensive test suite** with:

✅ **643+ automated tests** covering all functionality
✅ **Unit tests** for isolated component validation
✅ **Integration tests** for component interactions
✅ **Benchmark tests** for performance validation
✅ **Comparison tests** demonstrating benefits
✅ **API/HTTP interface tests** for FastAPI endpoints (equivalent to UI tests)
✅ **Linting & static analysis** for code quality (ruff, mypy, bandit)
✅ **Security tests** for validation and encryption
✅ **E2E tests** for complete system validation
✅ **Manual tests** for interactive demonstration

All tests use **async/await** patterns and follow **pytest best practices** with proper fixtures, markers, and organization.

### Code Quality Assurance:

- **Ruff**: Enforces code style, finds bugs, organizes imports
- **MyPy**: Validates type annotations and catches type errors
- **Bandit**: Scans for security vulnerabilities
- **All run automatically in CI/CD** before code is merged

