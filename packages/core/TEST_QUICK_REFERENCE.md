# Test Quick Reference Card

Quick commands for testing ApiKeyRouter functionality.

## 🚀 Quick Start

```bash
cd packages/core

# Run all tests
poetry run pytest -v

# Run with coverage
poetry run pytest --cov=apikeyrouter --cov-report=html --cov-report=term
```

## 📋 Test Categories

### Unit Tests (Fast, Isolated)

```bash
# All unit tests
poetry run pytest tests/unit/ -v

# Core components
poetry run pytest tests/unit/test_key_manager.py -v
poetry run pytest tests/unit/test_routing_engine.py -v
poetry run pytest tests/unit/test_quota_awareness_engine.py -v
poetry run pytest tests/unit/test_cost_controller.py -v
poetry run pytest tests/unit/test_router.py -v

# Routing strategies
poetry run pytest tests/unit/test_cost_optimized_strategy.py -v
poetry run pytest tests/unit/test_reliability_optimized_strategy.py -v
poetry run pytest tests/unit/test_fairness_strategy.py -v

# State management
poetry run pytest tests/unit/test_state_store.py -v
poetry run pytest tests/unit/test_memory_store.py -v
```

### Integration Tests (Component Interactions)

```bash
# All integration tests
poetry run pytest tests/integration/ -v

# Core workflows
poetry run pytest tests/integration/test_routing_flow.py -v
poetry run pytest tests/integration/test_key_management.py -v
poetry run pytest tests/integration/test_quota_awareness.py -v
poetry run pytest tests/integration/test_cost_control.py -v
poetry run pytest tests/integration/test_failure_handling.py -v

# Provider adapters
poetry run pytest tests/integration/test_openai_adapter.py -v
poetry run pytest tests/integration/test_openai_adapter_cost.py -v
poetry run pytest tests/integration/test_openai_adapter_health.py -v

# MongoDB (requires MongoDB running)
poetry run pytest tests/integration/test_state_store_mongo.py -v
```

### Performance Benchmarks

```bash
# All benchmarks
poetry run pytest tests/benchmarks/ -v --benchmark-only

# Specific benchmarks
poetry run pytest tests/benchmarks/benchmark_routing.py -v --benchmark-only
poetry run pytest tests/benchmarks/benchmark_quota.py -v --benchmark-only
poetry run pytest tests/benchmarks/benchmark_key_lookup.py -v --benchmark-only

# Check performance thresholds
poetry run pytest tests/benchmarks/check_performance_thresholds.py -v
```

## 🎯 Test Specific Functionality

### Key Management
```bash
poetry run pytest tests/unit/test_key_manager.py -v -k "register"
poetry run pytest tests/unit/test_key_manager.py -v -k "state"
poetry run pytest tests/integration/test_key_management.py -v
```

### Routing
```bash
poetry run pytest tests/unit/test_routing_engine.py -v -k "objective"
poetry run pytest tests/integration/test_routing_flow.py -v
```

### Quota Awareness
```bash
poetry run pytest tests/unit/test_quota_awareness_engine.py -v -k "capacity"
poetry run pytest tests/integration/test_quota_awareness.py -v -k "exhaustion"
```

### Cost Control
```bash
poetry run pytest tests/unit/test_cost_controller.py -v -k "budget"
poetry run pytest tests/integration/test_cost_control.py -v
```

### Failure Handling
```bash
poetry run pytest tests/integration/test_failure_handling.py -v
```

## 📊 Coverage Reports

```bash
# Generate HTML coverage report
poetry run pytest --cov=apikeyrouter --cov-report=html
# Then open: htmlcov/index.html

# Terminal coverage report
poetry run pytest --cov=apikeyrouter --cov-report=term

# Coverage with missing lines
poetry run pytest --cov=apikeyrouter --cov-report=term-missing
```

## 🧪 Manual Testing

```bash
# Run comprehensive manual example
python test_manual_example.py
```

## 🔍 Debugging Tests

```bash
# Run with verbose output
poetry run pytest -vv

# Run with print statements visible
poetry run pytest -s

# Run single test
poetry run pytest tests/unit/test_key_manager.py::test_register_key -v

# Run with debugger on failure
poetry run pytest --pdb
```

## ⚡ Fast Test Runs

```bash
# Run only unit tests (fastest)
poetry run pytest tests/unit/ -v

# Run tests in parallel (if pytest-xdist installed)
poetry run pytest -n auto

# Run tests matching pattern
poetry run pytest -k "test_register" -v
```

## 🚨 Pre-Commit Checks

```bash
# Linting
poetry run ruff check .

# Type checking
poetry run mypy apikeyrouter

# Quick test run
poetry run pytest tests/unit/ -v --maxfail=3
```

## 📈 Performance Testing

```bash
# Run all benchmarks
poetry run pytest tests/benchmarks/ --benchmark-only

# Compare with baseline
poetry run pytest tests/benchmarks/ --benchmark-only --benchmark-json=benchmark.json
python tests/benchmarks/check_performance_thresholds.py benchmark.json baseline.json
```

## 🎓 Learning Tests

```bash
# Run tests and see what they test
poetry run pytest tests/unit/test_key_manager.py -v --tb=short

# Run with detailed output
poetry run pytest tests/unit/test_key_manager.py -vv --tb=long
```

## 📝 Test File Locations

```
packages/core/
├── tests/
│   ├── unit/              # Unit tests (fast, isolated)
│   ├── integration/       # Integration tests (component interactions)
│   ├── benchmarks/        # Performance benchmarks
│   ├── fixtures/          # Test data fixtures
│   └── conftest.py        # Pytest configuration
├── test_manual_example.py # Comprehensive manual example
└── TESTING_GUIDE.md       # Detailed testing guide
```

## 🔗 Related Documentation

- **Comprehensive Guide**: `COMPREHENSIVE_TESTING_GUIDE.md`
- **Test Strategy**: `docs/architecture/test-strategy-and-standards.md`
- **StateStore Guide**: `TESTING_GUIDE.md`
- **API Reference**: `API_REFERENCE.md`

